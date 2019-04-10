#
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#
import os

from ._cas import CASRemoteSpec
from .storage._casbaseddirectory import CasBasedDirectory
from ._basecache import BaseCache
from ._exceptions import CASError, CASCacheError, SourceCacheError
from . import utils


# Holds configuration for a remote used for the source cache.
#
# Args:
#     url (str): Location of the remote source cache
#     push (bool): Whether we should attempt to push sources to this cache,
#                  in addition to pulling from it.
#     instance-name (str): Name if any, of instance of server
#
class SourceCacheSpec(CASRemoteSpec):
    pass


# Class that keeps config of remotes and deals with caching of sources.
#
# Args:
#    context (Context): The Buildstream context
#
class SourceCache(BaseCache):

    spec_class = SourceCacheSpec
    spec_name = "source_cache_specs"
    spec_error = SourceCacheError
    config_node_name = "source-caches"

    def __init__(self, context):
        super().__init__(context)

        self._required_sources = set()

        self.casquota.add_remove_callbacks(self.unrequired_sources, self.cas.remove)
        self.casquota.add_list_refs_callback(self.list_sources)

    def __getstate__(self):
        state = self.__dict__.copy()
        return state

    # mark_required_sources()
    #
    # Mark sources that are required by the current run.
    #
    # Sources that are in this list will not be removed during the current
    # pipeline.
    #
    # Args:
    #     sources (iterable): An iterable over sources that are required
    #
    def mark_required_sources(self, sources):
        sources = list(sources)  # in case it's a generator

        self._required_sources.update(sources)

        # update mtimes just in case
        for source in sources:
            ref = source._get_source_name()
            try:
                self.cas.update_mtime(ref)
            except CASCacheError:
                pass

    # required_sources()
    #
    # Yields the keys of all sources marked as required by the current build
    # plan
    #
    # Returns:
    #     iterable (str): iterable over the required source refs
    #
    def required_sources(self):
        for source in self._required_sources:
            yield source._get_source_name()

    # unrequired_sources()
    #
    # Yields the refs of all sources not required by the current build plan
    #
    # Returns:
    #     iter (str): iterable over unrequired source keys
    #
    def unrequired_sources(self):
        required_source_names = set(map(
            lambda x: x._get_source_name(), self._required_sources))
        for (mtime, source) in self._list_refs_mtimes(
                os.path.join(self.cas.casdir, 'refs', 'heads'),
                glob_expr="@sources/*"):
            if source not in required_source_names:
                yield (mtime, source)

    # list_sources()
    #
    # Get list of all sources in the `cas/refs/heads/@sources/` folder
    #
    # Returns:
    #     ([str]): iterable over all source refs
    #
    def list_sources(self):
        return [ref for _, ref in self._list_refs_mtimes(
            os.path.join(self.cas.casdir, 'refs', 'heads'),
            glob_expr="@sources/*")]

    # contains()
    #
    # Given a source, gets the ref name and checks whether the local CAS
    # contains it.
    #
    # Args:
    #    source (Source): Source to check
    #
    # Returns:
    #    (bool): whether the CAS contains this source or not
    #
    def contains(self, source):
        ref = source._get_source_name()
        return self.cas.contains(ref)

    # commit()
    #
    # Given a source along with previous sources, it stages and commits these
    # to the local CAS. This is done due to some types of sources being
    # dependent on previous sources, such as the patch source.
    #
    # Args:
    #    source: last source
    #    previous_sources: rest of the sources.
    def commit(self, source, previous_sources):
        ref = source._get_source_name()

        # Use tmpdir for now
        vdir = CasBasedDirectory(self.cas)
        for previous_source in previous_sources:
            vdir.import_files(self.export(previous_source))

        with utils._tempdir(dir=self.context.tmpdir, prefix='staging-temp') as tmpdir:
            if not vdir.is_empty():
                vdir.export_files(tmpdir)
            source._stage(tmpdir)
            vdir.import_files(tmpdir, can_link=True)

        self.cas.set_ref(ref, vdir._get_digest())

    # export()
    #
    # Exports a source in the CAS to a virtual directory
    #
    # Args:
    #    source (Source): source we want to export
    #
    # Returns:
    #    CASBasedDirectory
    def export(self, source):
        ref = source._get_source_name()

        try:
            digest = self.cas.resolve_ref(ref)
        except CASCacheError as e:
            raise SourceCacheError("Error exporting source: {}".format(e))

        return CasBasedDirectory(self.cas, digest=digest)

    # pull()
    #
    # Attempts to pull sources from configure remote source caches.
    #
    # Args:
    #    source (Source): The source we want to fetch
    #    progress (callable|None): The progress callback
    #
    # Returns:
    #    (bool): True if pull successful, False if not
    def pull(self, source):
        ref = source._get_source_name()

        project = source._get_project()

        display_key = source._get_brief_display_key()

        for remote in self._remotes[project]:
            try:
                source.status("Pulling source {} <- {}".format(display_key, remote.spec.url))

                if self.cas.pull(ref, remote):
                    source.info("Pulled source {} <- {}".format(display_key, remote.spec.url))
                    # no need to pull from additional remotes
                    return True
                else:
                    source.info("Remote ({}) does not have source {} cached".format(
                        remote.spec.url, display_key))
            except CASError as e:
                raise SourceCacheError("Failed to pull source {}: {}".format(
                    display_key, e)) from e
        return False

    # push()
    #
    # Push a source to configured remote source caches
    #
    # Args:
    #    source (Source): source to push
    #
    # Returns:
    #    (Bool): whether it pushed to a remote source cache
    #
    def push(self, source):
        ref = source._get_source_name()
        project = source._get_project()

        # find configured push remotes for this source
        if self._has_push_remotes:
            push_remotes = [r for r in self._remotes[project] if r.spec.push]
        else:
            push_remotes = []

        pushed = False

        display_key = source._get_brief_display_key()
        for remote in push_remotes:
            remote.init()
            source.status("Pushing source {} -> {}".format(display_key, remote.spec.url))
            if self.cas.push([ref], remote):
                source.info("Pushed source {} -> {}".format(display_key, remote.spec.url))
                pushed = True
            else:
                source.info("Remote ({}) already has source {} cached"
                            .format(remote.spec.url, display_key))

        return pushed
