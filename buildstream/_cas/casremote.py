from collections import namedtuple
import io
import os
import multiprocessing
import signal
import tempfile
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
        _yaml.node_validate(spec_node, ['url', 'push', 'server-cert', 'client-key', 'client-cert', 'instance_name'])
        url = _yaml.node_get(spec_node, str, 'url')
        push = _yaml.node_get(spec_node, bool, 'push', default_value=False)
        if not url:
            provenance = _yaml.node_get_provenance(spec_node, 'url')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: empty artifact cache URL".format(provenance))

        instance_name = _yaml.node_get(spec_node, str, 'server-cert', default_value=None)

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
    def __init__(self, spec, tmpdir):
        self.spec = spec
        self._initialized = False
        self.channel = None
        self.bytestream = None
        self.cas = None
        self.ref_storage = None
        self.batch_update_supported = None
        self.batch_read_supported = None
        self.capabilities = None
        self.max_batch_total_size_bytes = None

        # Need str because python 3.5 and lower doesn't deal with path like
        # objects here.
        self.tmpdir = str(tmpdir)
        os.makedirs(self.tmpdir, exist_ok=True)

        self.__tmp_downloads = []  # files in the tmpdir waiting to be added to local caches

        self.__batch_read = None
        self.__batch_update = None

    def init(self):
        if not self._initialized:
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

            self.bytestream = bytestream_pb2_grpc.ByteStreamStub(self.channel)
            self.cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self.channel)
            self.capabilities = remote_execution_pb2_grpc.CapabilitiesStub(self.channel)
            self.ref_storage = buildstream_pb2_grpc.ReferenceStorageStub(self.channel)

            self.max_batch_total_size_bytes = _MAX_PAYLOAD_BYTES
            try:
                request = remote_execution_pb2.GetCapabilitiesRequest()
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
                response = self.cas.BatchReadBlobs(request)
                self.batch_read_supported = True
                self.__batch_read = _CASBatchRead(self)
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.UNIMPLEMENTED:
                    raise

            # Check whether the server supports BatchUpdateBlobs()
            self.batch_update_supported = False
            try:
                request = remote_execution_pb2.BatchUpdateBlobsRequest()
                response = self.cas.BatchUpdateBlobs(request)
                self.batch_update_supported = True
                self.__batch_update = _CASBatchUpdate(self)
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
    def check_remote(cls, remote_spec, tmpdir, q):

        def __check_remote():
            try:
                remote = cls(remote_spec, tmpdir)
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

    # verify_digest_on_remote():
    #
    # Check whether the object is already on the server in which case
    # there is no need to upload it.
    #
    # Args:
    #     digest (Digest): The object digest.
    #
    def verify_digest_on_remote(self, digest):
        self.init()

        request = remote_execution_pb2.FindMissingBlobsRequest()
        request.blob_digests.extend([digest])

        response = self.cas.FindMissingBlobs(request)
        if digest in response.missing_blob_digests:
            return False

        return True

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

    # get_reference():
    #
    # Args:
    #    ref (str): The ref to request
    #
    # Returns:
    #    (digest): digest of ref, None if not found
    #
    def get_reference(self, ref):
        try:
            self.init()

            request = buildstream_pb2.GetReferenceRequest()
            request.key = ref
            return self.ref_storage.GetReference(request).digest
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise CASRemoteError("Failed to find ref {}: {}".format(ref, e)) from e
            else:
                return None

    def get_tree_blob(self, tree_digest):
        self.init()
        f = tempfile.NamedTemporaryFile(dir=self.tmpdir)
        self._fetch_blob(tree_digest, f)

        tree = remote_execution_pb2.Tree()
        with open(f.name, 'rb') as tmp:
            tree.ParseFromString(tmp.read())

        return tree

    # yield_directory_digests():
    #
    # Recursively iterates over digests for files, symbolic links and other
    # directories starting from a root digest
    #
    # Args:
    #     root_digest (digest): The root_digest to get a tree of
    #     progress (callable): The progress callback, if any
    #     subdir (str): The optional specific subdir to pull
    #     excluded_subdirs (list): The optional list of subdirs to not pull
    #
    # Returns:
    #     (iter digests): recursively iterates over digests contained in root directory
    #
    def yield_directory_digests(self, root_digest, *, progress=None,
                                subdir=None, excluded_subdirs=None):
        self.init()

        # Fetch artifact, excluded_subdirs determined in pullqueue
        if excluded_subdirs is None:
            excluded_subdirs = []

        # get directory blob
        f = tempfile.NamedTemporaryFile(dir=self.tmpdir)
        self._fetch_blob(root_digest, f)

        directory = remote_execution_pb2.Directory()
        with open(f.name, 'rb') as tmp:
            directory.ParseFromString(tmp.read())

        yield root_digest
        for filenode in directory.files:
            yield filenode.digest

        for dirnode in directory.directories:
            if dirnode.name not in excluded_subdirs:
                yield from self.yield_directory_digests(dirnode.digest)

    # yield_tree_digests():
    #
    # Fetches a tree file from digests and then iterates over child digests
    #
    # Args:
    #     tree_digest (digest): tree digest
    #
    # Returns:
    #     (iter digests): iterates over digests in tree message
    def yield_tree_digests(self, tree):
        self.init()

        tree.children.extend([tree.root])
        for directory in tree.children:
            for filenode in directory.files:
                yield filenode.digest

            # add the directory to downloaded tmp files to be added
            f = tempfile.NamedTemporaryFile(dir=self.tmpdir)
            f.write(directory.SerializeToString())
            f.flush()
            self.__tmp_downloads.append(f)

    # request_blob():
    #
    # Request blob, triggering download depending via bytestream or cas
    # BatchReadBlobs depending on size.
    #
    # Args:
    #    digest (Digest): digest of the requested blob
    #
    def request_blob(self, digest):
        if (not self.batch_read_supported or
                digest.size_bytes > self.max_batch_total_size_bytes):
            f = tempfile.NamedTemporaryFile(dir=self.tmpdir)
            self._fetch_blob(digest, f)
            self.__tmp_downloads.append(f)
        elif self.__batch_read.add(digest) is False:
            self._download_batch()
            self.__batch_read.add(digest)

    # get_blobs():
    #
    # Yield over downloaded blobs in the tmp file locations, causing the files
    # to be deleted once they go out of scope.
    #
    # Args:
    #    complete_batch (bool): download any outstanding batch read request
    #
    # Returns:
    #    iterator over NamedTemporaryFile
    def get_blobs(self, complete_batch=False):
        # Send read batch request and download
        if (complete_batch is True and
                self.batch_read_supported is True):
            self._download_batch()

        while self.__tmp_downloads:
            yield self.__tmp_downloads.pop()

    ################################################
    #             Local Private Methods            #
    ################################################
    def _fetch_blob(self, digest, stream):
        resource_name = '/'.join(['blobs', digest.hash, str(digest.size_bytes)])
        request = bytestream_pb2.ReadRequest()
        request.resource_name = resource_name
        request.read_offset = 0
        for response in self.bytestream.Read(request):
            stream.write(response.data)
        stream.flush()

        assert digest.size_bytes == os.fstat(stream.fileno()).st_size

    def _send_blob(self, digest, stream, u_uid=uuid.uuid4()):
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

    def _download_batch(self):
        for _, data in self.__batch_read.send():
            f = tempfile.NamedTemporaryFile(dir=self.tmpdir)
            f.write(data)
            f.flush()
            self.__tmp_downloads.append(f)

        self.__batch_read = _CASBatchRead(self)


# Represents a batch of blobs queued for fetching.
#
class _CASBatchRead():
    def __init__(self, remote):
        self._remote = remote
        self._max_total_size_bytes = remote.max_batch_total_size_bytes
        self._request = remote_execution_pb2.BatchReadBlobsRequest()
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

    def send(self):
        assert not self._sent
        self._sent = True

        if not self._request.digests:
            return

        batch_response = self._remote.cas.BatchReadBlobs(self._request)

        for response in batch_response.responses:
            if response.status.code == code_pb2.NOT_FOUND:
                raise BlobNotFound(response.digest.hash, "Failed to download blob {}: {}".format(
                    response.digest.hash, response.status.code))
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
