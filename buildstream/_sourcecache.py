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
from ._cas import CASRemoteSpec
from .storage._casbaseddirectory import CasBasedDirectory
from ._basecache import BaseCache
from ._exceptions import CASCacheError, SourceCacheError
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

        self.casquota.add_ref_callbacks(self.required_sources())
        self.casquota.add_remove_callbacks((lambda x: x.startswith('@sources/'), self.cas.remove))

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
    # Yields the keys of all sources marked as required
    #
    # Returns:
    #     iterable (str): iterable over the source keys
    #
    def required_sources(self):
        for source in self._required_sources:
            yield source._key

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
        with utils._tempdir(dir=self.context.tmpdir, prefix='staging-temp') as tmpdir:
            for previous_source in previous_sources:
                previous_source._stage(tmpdir)
            source._stage(tmpdir)

            self.cas.commit([ref], tmpdir)

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
