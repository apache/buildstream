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
import grpc

from ._cas import CASRemote, CASRemoteSpec
from .storage._casbaseddirectory import CasBasedDirectory
from ._basecache import BaseCache
from ._exceptions import CASError, CASRemoteError, SourceCacheError
from . import utils
from ._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc, \
    source_pb2, source_pb2_grpc


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


class SourceRemote(CASRemote):
    def __init__(self, *args):
        super().__init__(*args)
        self.capabilities_service = None
        self.source_service = None

    def init(self):
        if not self._initialized:
            super().init()

            self.capabilities_service = buildstream_pb2_grpc.CapabilitiesStub(self.channel)

            # check that the service supports sources
            try:
                request = buildstream_pb2.GetCapabilitiesRequest()
                if self.instance_name:
                    request.instance_name = self.instance_name

                response = self.capabilities_service.GetCapabilities(request)
            except grpc.RpcError as e:
                # Check if this remote has the artifact service
                if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                    raise SourceCacheError(
                        "Configured remote does not have the BuildStream "
                        "capabilities service. Please check remote configuration.")
                # Else raise exception with details
                raise SourceCacheError(
                    "Remote initialisation failed: {}".format(e.details()))

            if not response.source_capabilities:
                raise SourceCacheError(
                    "Configured remote does not support source service")

            # set up source service
            self.source_service = source_pb2_grpc.SourceServiceStub(self.channel)


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
    remote_class = SourceRemote

    def __init__(self, context):
        super().__init__(context)

        self._required_sources = set()
        self.sourcerefdir = os.path.join(context.cachedir, 'source_protos')
        os.makedirs(self.sourcerefdir, exist_ok=True)

        self.casquota.add_remove_callbacks(self.unrequired_sources, self._remove_source)
        self.casquota.add_list_refs_callback(self.list_sources)

        self.cas.add_reachable_directories_callback(self._reachable_directories)

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
                self._update_mtime(ref)
            except SourceCacheError:
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
        for (mtime, source) in self._list_refs_mtimes(self.sourcerefdir):
            if source not in required_source_names:
                yield (mtime, source)

    # list_sources()
    #
    # Get list of all sources in the `sources_protos/` folder
    #
    # Returns:
    #     ([str]): iterable over all source refs
    #
    def list_sources(self):
        return [ref for _, ref in self._list_refs_mtimes(self.sourcerefdir)]

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
        path = self._source_path(ref)

        if not os.path.exists(path):
            return False

        # check files
        source_proto = self._get_source(ref)
        return self.cas.contains_directory(source_proto.files, with_files=True)

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

        if not source.BST_STAGE_VIRTUAL_DIRECTORY:
            with utils._tempdir(dir=self.context.tmpdir, prefix='staging-temp') as tmpdir:
                if not vdir.is_empty():
                    vdir.export_files(tmpdir)
                source._stage(tmpdir)
                vdir.import_files(tmpdir, can_link=True)
        else:
            source._stage(vdir)

        self._store_source(ref, vdir._get_digest())

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
        source = self._get_source(ref)
        return CasBasedDirectory(self.cas, digest=source.files)

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

                # fetch source proto
                response = self._pull_source(ref, remote)
                if response is None:
                    source.info("Remote source service ({}) does not have source {} cached".format(
                        remote.spec.url, display_key))
                    continue

                # Fetch source blobs
                self.cas._fetch_directory(remote, response.files)
                required_blobs = self.cas.required_blobs_for_directory(response.files)
                missing_blobs = self.cas.local_missing_blobs(required_blobs)
                missing_blobs = self.cas.fetch_blobs(remote, missing_blobs)

                if missing_blobs:
                    source.info("Remote cas ({}) does not have source {} cached".format(
                        remote.spec.url, display_key))
                    continue

                source.info("Pulled source {} <- {}".format(display_key, remote.spec.url))
                return True

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

            # check whether cache has files already
            if self._pull_source(ref, remote) is not None:
                source.info("Remote ({}) already has source {} cached"
                            .format(remote.spec.url, display_key))
                continue

            # push files to storage
            source_proto = self._get_source(ref)
            try:
                self.cas._send_directory(remote, source_proto.files)
            except CASRemoteError:
                source.info("Failed to push source files {} -> {}".format(display_key, remote.spec.url))
                continue

            if not self._push_source(ref, remote):
                source.info("Failed to push source metadata {} -> {}".format(display_key, remote.spec.url))
                continue

            source.info("Pushed source {} -> {}".format(display_key, remote.spec.url))
            pushed = True

        return pushed

    def _remove_source(self, ref, *, defer_prune=False):
        return self.cas.remove(ref, basedir=self.sourcerefdir, defer_prune=defer_prune)

    def _store_source(self, ref, digest):
        source_proto = source_pb2.Source()
        source_proto.files.CopyFrom(digest)

        self._store_proto(source_proto, ref)

    def _store_proto(self, proto, ref):
        path = self._source_path(ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with utils.save_file_atomic(path, 'w+b') as f:
            f.write(proto.SerializeToString())

    def _get_source(self, ref):
        path = self._source_path(ref)
        source_proto = source_pb2.Source()
        try:
            with open(path, 'r+b') as f:
                source_proto.ParseFromString(f.read())
                return source_proto
        except FileNotFoundError as e:
            raise SourceCacheError("Attempted to access unavailable source: {}"
                                   .format(e)) from e

    def _source_path(self, ref):
        return os.path.join(self.sourcerefdir, ref)

    def _reachable_directories(self):
        for root, _, files in os.walk(self.sourcerefdir):
            for source_file in files:
                source = source_pb2.Source()
                with open(os.path.join(root, source_file), 'r+b') as f:
                    source.ParseFromString(f.read())

                yield source.files

    def _update_mtime(self, ref):
        try:
            os.utime(self._source_path(ref))
        except FileNotFoundError as e:
            raise SourceCacheError("Couldn't find source: {}".format(ref)) from e

    def _pull_source(self, source_ref, remote):
        try:
            remote.init()

            request = source_pb2.GetSourceRequest()
            request.cache_key = source_ref

            response = remote.source_service.GetSource(request)

            self._store_proto(response, source_ref)

            return response

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise SourceCacheError("Failed to pull source: {}".format(e.details()))
            return None

    def _push_source(self, source_ref, remote):
        try:
            remote.init()

            source_proto = self._get_source(source_ref)

            request = source_pb2.UpdateSourceRequest()
            request.cache_key = source_ref
            request.source.CopyFrom(source_proto)

            return remote.source_service.UpdateSource(request)

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise SourceCacheError("Failed to push source: {}".format(e.details()))
            return None
