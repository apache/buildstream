import grpc

from .._protos.google.rpc import code_pb2
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.build.buildgrid import local_cas_pb2
from .._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc

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
        self.cas = None
        self.ref_storage = None
        self.batch_update_supported = None
        self.batch_read_supported = None
        self.capabilities = None
        self.max_batch_total_size_bytes = None
        self.local_cas_instance_name = None

    # check_remote
    # _configure_protocols():
    #
    # Configure remote-specific protocols. This method should *never*
    # be called outside of init().
    #
    def _configure_protocols(self):
        self.cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self.channel)
        self.capabilities = remote_execution_pb2_grpc.CapabilitiesStub(self.channel)
        self.ref_storage = buildstream_pb2_grpc.ReferenceStorageStub(self.channel)

        # Figure out what batch sizes the server will accept, falling
        # back to our _MAX_PAYLOAD_BYTES
        self.max_batch_total_size_bytes = _MAX_PAYLOAD_BYTES
        try:
            request = remote_execution_pb2.GetCapabilitiesRequest()
            if self.instance_name:
                request.instance_name = self.instance_name
            response = self.capabilities.GetCapabilities(request)
            server_max_batch_total_size_bytes = response.cache_capabilities.max_batch_total_size_bytes
            if 0 < server_max_batch_total_size_bytes < self.max_batch_total_size_bytes:
                self.max_batch_total_size_bytes = server_max_batch_total_size_bytes
        except grpc.RpcError as e:
            # Simply use the defaults for servers that don't implement
            # GetCapabilities()
            if e.code() != grpc.StatusCode.UNIMPLEMENTED:
                raise

        # Check whether the server supports BatchReadBlobs()
        self.batch_read_supported = self._check_support(
            remote_execution_pb2.BatchReadBlobsRequest,
            self.cas.BatchReadBlobs
        )

        # Check whether the server supports BatchUpdateBlobs()
        self.batch_update_supported = self._check_support(
            remote_execution_pb2.BatchUpdateBlobsRequest,
            self.cas.BatchUpdateBlobs
        )

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

    # _check_support():
    #
    # Figure out if a remote server supports a given method based on
    # grpc.StatusCode.UNIMPLEMENTED and grpc.StatusCode.PERMISSION_DENIED.
    #
    # Args:
    #    request_type (callable): The type of request to check.
    #    invoker (callable): The remote method that will be invoked.
    #
    # Returns:
    #    (bool) - Whether the request is supported.
    #
    def _check_support(self, request_type, invoker):
        try:
            request = request_type()
            if self.instance_name:
                request.instance_name = self.instance_name
            invoker(request)
            return True
        except grpc.RpcError as e:
            if not e.code() in (grpc.StatusCode.UNIMPLEMENTED, grpc.StatusCode.PERMISSION_DENIED):
                raise

        return False

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
class _CASBatchRead():
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
                        raise BlobNotFound(response.digest.hash, "Failed to download blob {}: {}".format(
                            response.digest.hash, response.status.code))

                    missing_blobs.append(response.digest)

                if response.status.code != code_pb2.OK:
                    raise CASRemoteError("Failed to download blob {}: {}".format(
                        response.digest.hash, response.status.code))
                if response.digest.size_bytes != len(response.data):
                    raise CASRemoteError("Failed to download blob {}: expected {} bytes, received {} bytes".format(
                        response.digest.hash, response.digest.size_bytes, len(response.data)))


# Represents a batch of blobs queued for upload.
#
class _CASBatchUpdate():
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

                    raise CASRemoteError("Failed to upload blob {}: {}".format(
                        response.digest.hash, response.status.code), reason=reason)
