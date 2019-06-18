from collections import namedtuple
import io
import os
import multiprocessing
import signal
from urllib.parse import urlparse
import uuid

import grpc

from .. import _yaml
from .._protos.google.rpc import code_pb2
from .._protos.google.bytestream import bytestream_pb2, bytestream_pb2_grpc
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc

from .._exceptions import CASRemoteError, LoadError, LoadErrorReason
from .. import _signals
from .. import utils

# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024


class CASRemoteSpec(namedtuple('CASRemoteSpec', 'url push server_cert client_key client_cert instance_name')):

    # _new_from_config_node
    #
    # Creates an CASRemoteSpec() from a YAML loaded node
    #
    @staticmethod
    def _new_from_config_node(spec_node, basedir=None):
        _yaml.node_validate(spec_node, ['url', 'push', 'server-cert', 'client-key', 'client-cert', 'instance-name'])
        url = _yaml.node_get(spec_node, str, 'url')
        push = _yaml.node_get(spec_node, bool, 'push', default_value=False)
        if not url:
            provenance = _yaml.node_get_provenance(spec_node, 'url')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: empty artifact cache URL".format(provenance))

        instance_name = _yaml.node_get(spec_node, str, 'instance-name', default_value=None)

        server_cert = _yaml.node_get(spec_node, str, 'server-cert', default_value=None)
        if server_cert and basedir:
            server_cert = os.path.join(basedir, server_cert)

        client_key = _yaml.node_get(spec_node, str, 'client-key', default_value=None)
        if client_key and basedir:
            client_key = os.path.join(basedir, client_key)

        client_cert = _yaml.node_get(spec_node, str, 'client-cert', default_value=None)
        if client_cert and basedir:
            client_cert = os.path.join(basedir, client_cert)

        if client_key and not client_cert:
            provenance = _yaml.node_get_provenance(spec_node, 'client-key')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: 'client-key' was specified without 'client-cert'".format(provenance))

        if client_cert and not client_key:
            provenance = _yaml.node_get_provenance(spec_node, 'client-cert')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: 'client-cert' was specified without 'client-key'".format(provenance))

        return CASRemoteSpec(url, push, server_cert, client_key, client_cert, instance_name)


CASRemoteSpec.__new__.__defaults__ = (None, None, None, None)


class BlobNotFound(CASRemoteError):

    def __init__(self, blob, msg):
        self.blob = blob
        super().__init__(msg)


# Represents a single remote CAS cache.
#
class CASRemote():
    def __init__(self, spec):
        self.spec = spec
        self._initialized = False
        self.channel = None
        self.instance_name = None
        self.bytestream = None
        self.cas = None
        self.ref_storage = None
        self.batch_update_supported = None
        self.batch_read_supported = None
        self.capabilities = None
        self.max_batch_total_size_bytes = None

    def init(self):
        if not self._initialized:
            # gRPC doesn't support fork without exec, which is used in the main process.
            assert not utils._is_main_process()

            url = urlparse(self.spec.url)
            if url.scheme == 'http':
                port = url.port or 80
                self.channel = grpc.insecure_channel('{}:{}'.format(url.hostname, port))
            elif url.scheme == 'https':
                port = url.port or 443

                if self.spec.server_cert:
                    with open(self.spec.server_cert, 'rb') as f:
                        server_cert_bytes = f.read()
                else:
                    server_cert_bytes = None

                if self.spec.client_key:
                    with open(self.spec.client_key, 'rb') as f:
                        client_key_bytes = f.read()
                else:
                    client_key_bytes = None

                if self.spec.client_cert:
                    with open(self.spec.client_cert, 'rb') as f:
                        client_cert_bytes = f.read()
                else:
                    client_cert_bytes = None

                credentials = grpc.ssl_channel_credentials(root_certificates=server_cert_bytes,
                                                           private_key=client_key_bytes,
                                                           certificate_chain=client_cert_bytes)
                self.channel = grpc.secure_channel('{}:{}'.format(url.hostname, port), credentials)
            else:
                raise CASRemoteError("Unsupported URL: {}".format(self.spec.url))

            self.instance_name = self.spec.instance_name or None

            self.bytestream = bytestream_pb2_grpc.ByteStreamStub(self.channel)
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

            self._initialized = True

    # check_remote
    #
    # Used when checking whether remote_specs work in the buildstream main
    # thread, runs this in a seperate process to avoid creation of gRPC threads
    # in the main BuildStream process
    # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
    @classmethod
    def check_remote(cls, remote_spec, q):

        def __check_remote():
            try:
                remote = cls(remote_spec)
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
        message_digest = utils._message_digest(message_buffer)

        self.init()

        with io.BytesIO(message_buffer) as b:
            self._send_blob(message_digest, b)

        return message_digest

    ################################################
    #             Local Private Methods            #
    ################################################
    def _fetch_blob(self, digest, stream):
        if self.instance_name:
            resource_name = '/'.join([self.instance_name, 'blobs',
                                      digest.hash, str(digest.size_bytes)])
        else:
            resource_name = '/'.join(['blobs',
                                      digest.hash, str(digest.size_bytes)])

        request = bytestream_pb2.ReadRequest()
        request.resource_name = resource_name
        request.read_offset = 0
        for response in self.bytestream.Read(request):
            stream.write(response.data)
        stream.flush()

        assert digest.size_bytes == os.fstat(stream.fileno()).st_size

    def _send_blob(self, digest, stream, u_uid=uuid.uuid4()):
        if self.instance_name:
            resource_name = '/'.join([self.instance_name, 'uploads', str(u_uid), 'blobs',
                                      digest.hash, str(digest.size_bytes)])
        else:
            resource_name = '/'.join(['uploads', str(u_uid), 'blobs',
                                      digest.hash, str(digest.size_bytes)])

        def request_stream(resname, instream):
            offset = 0
            finished = False
            remaining = digest.size_bytes
            while not finished:
                chunk_size = min(remaining, _MAX_PAYLOAD_BYTES)
                remaining -= chunk_size

                request = bytestream_pb2.WriteRequest()
                request.write_offset = offset
                # max. _MAX_PAYLOAD_BYTES chunks
                request.data = instream.read(chunk_size)
                request.resource_name = resname
                request.finish_write = remaining <= 0

                yield request

                offset += chunk_size
                finished = request.finish_write

        response = self.bytestream.Write(request_stream(resource_name, stream))

        assert response.committed_size == digest.size_bytes


# Represents a batch of blobs queued for fetching.
#
class _CASBatchRead():
    def __init__(self, remote):
        self._remote = remote
        self._max_total_size_bytes = remote.max_batch_total_size_bytes
        self._request = remote_execution_pb2.BatchReadBlobsRequest()
        if remote.instance_name:
            self._request.instance_name = remote.instance_name
        self._size = 0
        self._sent = False

    def add(self, digest):
        assert not self._sent

        new_batch_size = self._size + digest.size_bytes
        if new_batch_size > self._max_total_size_bytes:
            # Not enough space left in current batch
            return False

        request_digest = self._request.digests.add()
        request_digest.hash = digest.hash
        request_digest.size_bytes = digest.size_bytes
        self._size = new_batch_size
        return True

    def send(self, *, missing_blobs=None):
        assert not self._sent
        self._sent = True

        if not self._request.digests:
            return

        batch_response = self._remote.cas.BatchReadBlobs(self._request)

        for response in batch_response.responses:
            if response.status.code == code_pb2.NOT_FOUND:
                if missing_blobs is None:
                    raise BlobNotFound(response.digest.hash, "Failed to download blob {}: {}".format(
                        response.digest.hash, response.status.code))
                else:
                    missing_blobs.append(response.digest)

            if response.status.code != code_pb2.OK:
                raise CASRemoteError("Failed to download blob {}: {}".format(
                    response.digest.hash, response.status.code))
            if response.digest.size_bytes != len(response.data):
                raise CASRemoteError("Failed to download blob {}: expected {} bytes, received {} bytes".format(
                    response.digest.hash, response.digest.size_bytes, len(response.data)))

            yield (response.digest, response.data)


# Represents a batch of blobs queued for upload.
#
class _CASBatchUpdate():
    def __init__(self, remote):
        self._remote = remote
        self._max_total_size_bytes = remote.max_batch_total_size_bytes
        self._request = remote_execution_pb2.BatchUpdateBlobsRequest()
        if remote.instance_name:
            self._request.instance_name = remote.instance_name
        self._size = 0
        self._sent = False

    def add(self, digest, stream):
        assert not self._sent

        new_batch_size = self._size + digest.size_bytes
        if new_batch_size > self._max_total_size_bytes:
            # Not enough space left in current batch
            return False

        blob_request = self._request.requests.add()
        blob_request.digest.hash = digest.hash
        blob_request.digest.size_bytes = digest.size_bytes
        blob_request.data = stream.read(digest.size_bytes)
        self._size = new_batch_size
        return True

    def send(self):
        assert not self._sent
        self._sent = True

        if not self._request.requests:
            return

        batch_response = self._remote.cas.BatchUpdateBlobs(self._request)

        for response in batch_response.responses:
            if response.status.code != code_pb2.OK:
                raise CASRemoteError("Failed to upload blob {}: {}".format(
                    response.digest.hash, response.status.code))
