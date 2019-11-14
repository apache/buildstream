#
#  Copyright (C) 2018-2019 Bloomberg Finance LP
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

from .._protos.google.rpc import code_pb2
from .._protos.build.buildgrid import local_cas_pb2

from .._remote import BaseRemote
from .._exceptions import CASRemoteError

# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024

# How many digests to put in a single gRPC message.
# A 256-bit hash requires 64 bytes of space (hexadecimal encoding).
# 80 bytes provide sufficient space for hash, size, and protobuf overhead.
_MAX_DIGESTS = _MAX_PAYLOAD_BYTES / 80


class BlobNotFound(CASRemoteError):
    def __init__(self, blob, msg):
        self.blob = blob
        super().__init__(msg)


# Represents a single remote CAS cache.
#
class CASRemote(BaseRemote):
    def __init__(self, spec, cascache, **kwargs):
        super().__init__(spec, **kwargs)

        self.cascache = cascache
        self.local_cas_instance_name = None

    # check_remote
    # _configure_protocols():
    #
    # Configure remote-specific protocols. This method should *never*
    # be called outside of init().
    #
    def _configure_protocols(self):
        local_cas = self.cascache._get_local_cas()
        request = local_cas_pb2.GetInstanceNameForRemoteRequest()
        request.url = self.spec.url
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name
        if self.server_cert:
            request.server_cert = self.server_cert
        if self.client_key:
            request.client_key = self.client_key
        if self.client_cert:
            request.client_cert = self.client_cert
        response = local_cas.GetInstanceNameForRemote(request)
        self.local_cas_instance_name = response.instance_name

    # push_message():
    #
    # Push the given protobuf message to a remote.
    #
    # Args:
    #     message (Message): A protobuf message to push.
    #
    # Raises:
    #     (CASRemoteError): if there was an error
    #
    def push_message(self, message):

        message_buffer = message.SerializeToString()

        self.init()

        return self.cascache.add_object(buffer=message_buffer, instance_name=self.local_cas_instance_name)


# Represents a batch of blobs queued for fetching.
#
class _CASBatchRead:
    def __init__(self, remote):
        self._remote = remote
        self._requests = []
        self._request = None
        self._sent = False

    def add(self, digest):
        assert not self._sent

        if not self._request or len(self._request.blob_digests) >= _MAX_DIGESTS:
            self._request = local_cas_pb2.FetchMissingBlobsRequest()
            self._request.instance_name = self._remote.local_cas_instance_name
            self._requests.append(self._request)

        request_digest = self._request.blob_digests.add()
        request_digest.CopyFrom(digest)

    def send(self, *, missing_blobs=None):
        assert not self._sent
        self._sent = True

        if not self._requests:
            return

        local_cas = self._remote.cascache._get_local_cas()

        for request in self._requests:
            batch_response = local_cas.FetchMissingBlobs(request)

            for response in batch_response.responses:
                if response.status.code == code_pb2.NOT_FOUND:
                    if missing_blobs is None:
                        raise BlobNotFound(
                            response.digest.hash,
                            "Failed to download blob {}: {}".format(response.digest.hash, response.status.code),
                        )

                    missing_blobs.append(response.digest)

                if response.status.code != code_pb2.OK:
                    raise CASRemoteError(
                        "Failed to download blob {}: {}".format(response.digest.hash, response.status.code)
                    )
                if response.digest.size_bytes != len(response.data):
                    raise CASRemoteError(
                        "Failed to download blob {}: expected {} bytes, received {} bytes".format(
                            response.digest.hash, response.digest.size_bytes, len(response.data)
                        )
                    )


# Represents a batch of blobs queued for upload.
#
class _CASBatchUpdate:
    def __init__(self, remote):
        self._remote = remote
        self._requests = []
        self._request = None
        self._sent = False

    def add(self, digest):
        assert not self._sent

        if not self._request or len(self._request.blob_digests) >= _MAX_DIGESTS:
            self._request = local_cas_pb2.UploadMissingBlobsRequest()
            self._request.instance_name = self._remote.local_cas_instance_name
            self._requests.append(self._request)

        request_digest = self._request.blob_digests.add()
        request_digest.CopyFrom(digest)

    def send(self):
        assert not self._sent
        self._sent = True

        if not self._requests:
            return

        local_cas = self._remote.cascache._get_local_cas()

        for request in self._requests:
            batch_response = local_cas.UploadMissingBlobs(request)

            for response in batch_response.responses:
                if response.status.code != code_pb2.OK:
                    if response.status.code == code_pb2.RESOURCE_EXHAUSTED:
                        reason = "cache-too-full"
                    else:
                        reason = None

                    raise CASRemoteError(
                        "Failed to upload blob {}: {}".format(response.digest.hash, response.status.code),
                        reason=reason,
                    )
