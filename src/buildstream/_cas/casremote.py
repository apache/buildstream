from collections import namedtuple
import os
import multiprocessing
import signal
from urllib.parse import urlparse

import grpc

from .._protos.google.rpc import code_pb2
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.build.buildgrid import local_cas_pb2
from .._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc

from .._exceptions import CASRemoteError, LoadError, LoadErrorReason
from .. import _signals
from .. import utils

# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024


class BlobNotFound(CASRemoteError):

    def __init__(self, blob, msg):
        self.blob = blob
        super().__init__(msg)


# Represents a single remote CAS cache.
#
class CASRemote():
    def __init__(self, spec, cascache):
        self.spec = spec
        self._initialized = False
        self.cascache = cascache
        self.channel = None
        self.instance_name = None
        self.cas = None
        self.ref_storage = None
        self.batch_update_supported = None
        self.batch_read_supported = None
        self.capabilities = None
        self.max_batch_total_size_bytes = None
        self.local_cas_instance_name = None

    def init(self):
        if not self._initialized:
            server_cert_bytes = None
            client_key_bytes = None
            client_cert_bytes = None

            url = urlparse(self.spec.url)
            if url.scheme == 'http':
                port = url.port or 80
                self.channel = grpc.insecure_channel('{}:{}'.format(url.hostname, port))
            elif url.scheme == 'https':
                port = url.port or 443

                if self.spec.server_cert:
                    with open(self.spec.server_cert, 'rb') as f:
                        server_cert_bytes = f.read()

                if self.spec.client_key:
                    with open(self.spec.client_key, 'rb') as f:
                        client_key_bytes = f.read()

                if self.spec.client_cert:
                    with open(self.spec.client_cert, 'rb') as f:
                        client_cert_bytes = f.read()

                credentials = grpc.ssl_channel_credentials(root_certificates=server_cert_bytes,
                                                           private_key=client_key_bytes,
                                                           certificate_chain=client_cert_bytes)
                self.channel = grpc.secure_channel('{}:{}'.format(url.hostname, port), credentials)
            else:
                raise CASRemoteError("Unsupported URL: {}".format(self.spec.url))

            self.instance_name = self.spec.instance_name or None

            self.cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self.channel)
            self.capabilities = remote_execution_pb2_grpc.CapabilitiesStub(self.channel)
            self.ref_storage = buildstream_pb2_grpc.ReferenceStorageStub(self.channel)

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
                # Simply use the defaults for servers that don't implement GetCapabilities()
                if e.code() != grpc.StatusCode.UNIMPLEMENTED:
                    raise

            # Check whether the server supports BatchReadBlobs()
            self.batch_read_supported = False
            try:
                request = remote_execution_pb2.BatchReadBlobsRequest()
                if self.instance_name:
                    request.instance_name = self.instance_name
                response = self.cas.BatchReadBlobs(request)
                self.batch_read_supported = True
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.UNIMPLEMENTED:
                    raise

            # Check whether the server supports BatchUpdateBlobs()
            self.batch_update_supported = False
            try:
                request = remote_execution_pb2.BatchUpdateBlobsRequest()
                if self.instance_name:
                    request.instance_name = self.instance_name
                response = self.cas.BatchUpdateBlobs(request)
                self.batch_update_supported = True
            except grpc.RpcError as e:
                if (e.code() != grpc.StatusCode.UNIMPLEMENTED and
                        e.code() != grpc.StatusCode.PERMISSION_DENIED):
                    raise

            local_cas = self.cascache._get_local_cas()
            request = local_cas_pb2.GetInstanceNameForRemoteRequest()
            request.url = self.spec.url
            if self.spec.instance_name:
                request.instance_name = self.spec.instance_name
            if server_cert_bytes:
                request.server_cert = server_cert_bytes
            if client_key_bytes:
                request.client_key = client_key_bytes
            if client_cert_bytes:
                request.client_cert = client_cert_bytes
            response = local_cas.GetInstanceNameForRemote(request)
            self.local_cas_instance_name = response.instance_name

            self._initialized = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None

    # check_remote
    #
    # Used when checking whether remote_specs work in the buildstream main
    # thread, runs this in a seperate process to avoid creation of gRPC threads
    # in the main BuildStream process
    # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
    @classmethod
    def check_remote(cls, remote_spec, cascache, q):

        def __check_remote():
            try:
                remote = cls(remote_spec, cascache)
                remote.init()

                request = buildstream_pb2.StatusRequest()
                response = remote.ref_storage.Status(request)

                if remote_spec.push and not response.allow_updates:
                    q.put('CAS server does not allow push')
                else:
                    # No error
                    q.put(None)

            except grpc.RpcError as e:
                # str(e) is too verbose for errors reported to the user
                q.put(e.details())

            except Exception as e:               # pylint: disable=broad-except
                # Whatever happens, we need to return it to the calling process
                #
                q.put(str(e))

        p = multiprocessing.Process(target=__check_remote)

        try:
            # Keep SIGINT blocked in the child process
            with _signals.blocked([signal.SIGINT], ignore=False):
                p.start()

            error = q.get()
            p.join()
        except KeyboardInterrupt:
            utils._kill_process_tree(p.pid)
            raise

        return error

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
        self._request = local_cas_pb2.FetchMissingBlobsRequest()
        self._request.instance_name = remote.local_cas_instance_name
        self._sent = False

    def add(self, digest):
        assert not self._sent

        request_digest = self._request.blob_digests.add()
        request_digest.CopyFrom(digest)

    def send(self, *, missing_blobs=None):
        assert not self._sent
        self._sent = True

        if not self._request.blob_digests:
            return

        local_cas = self._remote.cascache._get_local_cas()
        batch_response = local_cas.FetchMissingBlobs(self._request)

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
        self._request = local_cas_pb2.UploadMissingBlobsRequest()
        self._request.instance_name = remote.local_cas_instance_name
        self._sent = False

    def add(self, digest):
        assert not self._sent

        request_digest = self._request.blob_digests.add()
        request_digest.CopyFrom(digest)

    def send(self):
        assert not self._sent
        self._sent = True

        if not self._request.blob_digests:
            return

        local_cas = self._remote.cascache._get_local_cas()
        batch_response = local_cas.UploadMissingBlobs(self._request)

        for response in batch_response.responses:
            if response.status.code != code_pb2.OK:
                if response.status.code == code_pb2.RESOURCE_EXHAUSTED:
                    reason = "cache-too-full"
                else:
                    reason = None

                raise CASRemoteError("Failed to upload blob {}: {}".format(
                    response.digest.hash, response.status.code), reason=reason)
