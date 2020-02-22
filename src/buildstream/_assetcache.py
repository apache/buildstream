#
#  Copyright (C) 2020 Bloomberg Finance LP
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
import os
import grpc

from ._remote import BaseRemote
from ._cas.casremote import BlobNotFound
from .storage._casbaseddirectory import CasBasedDirectory
from ._basecache import BaseCache
from ._exceptions import CASError, CASRemoteError, SourceCacheError, RemoteError, AssetCacheError
from . import utils
from ._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc, source_pb2, source_pb2_grpc
from ._protos.build.bazel.remote.asset.v1 import remote_asset_pb2, remote_asset_pb2_grpc


class AssetRemote(BaseRemote):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetch_service = None
        self.push_service = None

    def close(self):
        self.fetch_service = None
        self.push_service = None
        super().close()

    def _configure_protocols(self):
        # set up source service
        self.fetch_service = remote_asset_pb2_grpc.FetchStub(self.channel)
        self.push_service = remote_asset_pb2_grpc.PushStub(self.channel)

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
        pass
        # capabilities_service = buildstream_pb2_grpc.CapabilitiesStub(self.channel)

        # # check that the service supports sources
        # try:
        #     request = buildstream_pb2.GetCapabilitiesRequest()
        #     if self.instance_name:
        #         request.instance_name = self.instance_name
        #     response = capabilities_service.GetCapabilities(request)
        # except grpc.RpcError as e:
        #     # Check if this remote has the artifact service
        #     if e.code() == grpc.StatusCode.UNIMPLEMENTED:
        #         raise RemoteError(
        #             "Configured remote does not have the BuildStream "
        #             "capabilities service. Please check remote configuration."
        #         )
        #     raise RemoteError("Remote initialisation failed: {}".format(e.details()))

        # if not response.source_capabilities:
        #     raise RemoteError("Configured remote does not support source service")

        # if self.spec.push and not response.source_capabilities.allow_updates:
        #     raise RemoteError("Source server does not allow push")

    # get_asset():
    # ...
    # returns Digest, uri, qualifiers
    def fetch_blob(self, uris, *, qualifiers=None):

        # TODO auto turn uris into a list if a string is passed
        
        if not qualifers:
            qualifiers = []

        request = remote_asset_pb2,FetchBlob()
        request.uris.extend(uris)
        request.qualifiers.extend(qualifiers)

        try:
            response = self.fetch_service.FetchBlob(request)
        except grpc.RpcError as e:
            # if e.code() == grpc.StatusCode.NOT_FOUND:
            #     return False
            # if e.code() == grpc.StatusCode.UNIMPLEMENTED:
            #     raise CASCacheError("Unsupported buildbox-casd version: FetchTree unimplemented") from e
            raise


        # TODO handle errors
        # TODO handle response.status
        if response.status == grpc.StatusCode.NOT_FOUND:
            raise NotImplemented
        # TODO handle other response codes
        if response.status != grpc.StatusCode.OK:
            raise AssetCacheError

        return response # or return digest, uri, qualifiers?

    def fetch_directory(self, uris, *, qualifiers=None):
        raise NotImplemented

    def push_blob(self, blob_digest, uris, *, qualifiers=None,
        references_blobs=None, references_directories=None):
        raise NotImplementedError

    def push_directory(self, directory_digest, uris, *, qualifiers=None,
        references_blobs=None, references_directories=None):
        raise NotImplementedError


# Class that keeps config of remotes and deals with caching of assets.
#
# Args:
#    context (Context): The Buildstream context
#
class AssetCache(BaseCache):

    spec_name = "asset_cache_specs"
    spec_error = AssetCacheError
    config_node_name = "asset-caches"
    index_remote_class = AssetRemote

    def __init__(self, context):
        super().__init__(context)

        self._basedir = os.path.join(context.cachedir, "asset_protos")
        os.makedirs(self._basedir, exist_ok=True)

    def fetch_blob(self, uris, *, qualifiers=None):
        raise NotImplementedError

    def fetch_directory(self, uris, *, qualifiers=None):
        raise NotImplementedError

    def push_blob(self, blob_digest, uris, *, qualifiers=None,
        references_blobs=None, references_directories=None):
        raise NotImplementedError

    def push_directory(self, directory_digest, uris, *, qualifiers=None,
        references_blobs=None, references_directories=None):
        raise NotImplementedError
