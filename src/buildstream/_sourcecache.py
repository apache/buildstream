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

from ._remote import BaseRemote
from ._cas.casremote import BlobNotFound
from .storage._casbaseddirectory import CasBasedDirectory
from ._basecache import BaseCache
from ._exceptions import CASError, CASRemoteError, SourceCacheError, RemoteError
from . import utils
from ._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc, source_pb2, source_pb2_grpc


class SourceRemote(BaseRemote):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_service = None

    def close(self):
        self.source_service = None
        super().close()

    def _configure_protocols(self):
        # set up source service
        self.source_service = source_pb2_grpc.SourceServiceStub(self.channel)

    # _check():
    #
    # Check if this remote provides everything required for the
    # particular kind of remote. This is expected to be called as part
    # of check()
    #
    # Raises:
    #     RemoteError: If the upstream has a problem
    #
    def _check(self):
        capabilities_service = buildstream_pb2_grpc.CapabilitiesStub(self.channel)

        # check that the service supports sources
        try:
            request = buildstream_pb2.GetCapabilitiesRequest()
            if self.instance_name:
                request.instance_name = self.instance_name
            response = capabilities_service.GetCapabilities(request)
        except grpc.RpcError as e:
            # Check if this remote has the artifact service
            if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                raise RemoteError(
                    "Configured remote does not have the BuildStream "
                    "capabilities service. Please check remote configuration."
                )
            raise RemoteError("Remote initialisation failed: {}".format(e.details()))

        if not response.source_capabilities:
            raise RemoteError("Configured remote does not support source service")

        if self.spec.push and not response.source_capabilities.allow_updates:
            raise RemoteError("Source server does not allow push")

    # get_source():
    #
    # Get a source proto for a given source_ref from the remote.
    #
    # Args:
    #    source_ref (str): The source ref of the source to pull.
    #
    # Returns:
    #    (Source): The source proto
    #
    # Raises:
    #    grpc.RpcError: If something goes wrong during the request.
    #
    def get_source(self, source_ref):
        request = source_pb2.GetSourceRequest()
        request.cache_key = source_ref
        return self.source_service.GetSource(request)

    # update_source():
    #
    # Update the source on the remote.
    #
    # Args:
    #    source_ref (str): The source ref of the source to update.
    #    source (Source): The proto to update with.
    #
    # Returns:
    #    (bool): Whether the update was successful.
    #
    # Raises:
    #    grpc.RpcError: If something goes wrong during the request.
    #
    def update_source(self, source_ref, source):
        request = source_pb2.UpdateSourceRequest()
        request.cache_key = source_ref
        request.source.CopyFrom(source)
        return self.source_service.UpdateSource(request)


# Class that keeps config of remotes and deals with caching of sources.
#
# Args:
#    context (Context): The Buildstream context
#
class SourceCache(BaseCache):

    spec_name = "source_cache_specs"
    spec_error = SourceCacheError
    config_node_name = "source-caches"
    index_remote_class = SourceRemote

    def __init__(self, context):
        super().__init__(context)

        self._basedir = os.path.join(context.cachedir, "source_protos")
        os.makedirs(self._basedir, exist_ok=True)

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
            with utils._tempdir(dir=self.context.tmpdir, prefix="staging-temp") as tmpdir:
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

        index_remotes = self._index_remotes[project]
        storage_remotes = self._storage_remotes[project]

        # First fetch the source proto so we know what to pull
        source_proto = None
        for remote in index_remotes:
            try:
                remote.init()
                source.status("Pulling source {} <- {}".format(display_key, remote))

                source_proto = self._pull_source(ref, remote)
                if source_proto is None:
                    source.info(
                        "Remote source service ({}) does not have source {} cached".format(remote, display_key)
                    )
                    continue
            except CASError as e:
                raise SourceCacheError("Failed to pull source {}: {}".format(display_key, e)) from e

        if not source_proto:
            return False

        for remote in storage_remotes:
            try:
                remote.init()
                source.status("Pulling data for source {} <- {}".format(display_key, remote))

                # Fetch source blobs
                self.cas._fetch_directory(remote, source_proto.files)
                required_blobs = self.cas.required_blobs_for_directory(source_proto.files)
                missing_blobs = self.cas.local_missing_blobs(required_blobs)
                missing_blobs = self.cas.fetch_blobs(remote, missing_blobs)

                if missing_blobs:
                    source.info("Remote cas ({}) does not have source {} cached".format(remote, display_key))
                    continue

                source.info("Pulled source {} <- {}".format(display_key, remote))
                return True
            except BlobNotFound as e:
                # Not all blobs are available on this remote
                source.info("Remote cas ({}) does not have blob {} cached".format(remote, e.blob))
                continue
            except CASError as e:
                raise SourceCacheError("Failed to pull source {}: {}".format(display_key, e)) from e

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

        index_remotes = []
        storage_remotes = []

        # find configured push remotes for this source
        if self._has_push_remotes:
            index_remotes = [r for r in self._index_remotes[project] if r.push]
            storage_remotes = [r for r in self._storage_remotes[project] if r.push]

        pushed_storage = False
        pushed_index = False

        display_key = source._get_brief_display_key()
        for remote in storage_remotes:
            remote.init()
            source.status("Pushing data for source {} -> {}".format(display_key, remote))

            source_proto = self._get_source(ref)
            try:
                self.cas._send_directory(remote, source_proto.files)
                pushed_storage = True
            except CASRemoteError:
                source.info("Failed to push source files {} -> {}".format(display_key, remote))
                continue

        for remote in index_remotes:
            remote.init()
            source.status("Pushing source {} -> {}".format(display_key, remote))

            # check whether cache has files already
            if self._pull_source(ref, remote) is not None:
                source.info("Remote ({}) already has source {} cached".format(remote, display_key))
                continue

            if not self._push_source(ref, remote):
                source.info("Failed to push source metadata {} -> {}".format(display_key, remote))
                continue

            source.info("Pushed source {} -> {}".format(display_key, remote))
            pushed_index = True

        return pushed_index and pushed_storage

    def _store_source(self, ref, digest):
        source_proto = source_pb2.Source()
        source_proto.files.CopyFrom(digest)

        self._store_proto(source_proto, ref)

    def _store_proto(self, proto, ref):
        path = self._source_path(ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with utils.save_file_atomic(path, "w+b") as f:
            f.write(proto.SerializeToString())

    def _get_source(self, ref):
        path = self._source_path(ref)
        source_proto = source_pb2.Source()
        try:
            with open(path, "r+b") as f:
                source_proto.ParseFromString(f.read())
                return source_proto
        except FileNotFoundError as e:
            raise SourceCacheError("Attempted to access unavailable source: {}".format(e)) from e

    def _source_path(self, ref):
        return os.path.join(self._basedir, ref)

    def _pull_source(self, source_ref, remote):
        try:
            remote.init()
            response = remote.get_source(source_ref)
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
            return remote.update_source(source_ref, source_proto)

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise SourceCacheError("Failed to push source: {}".format(e.details()))
            return None
