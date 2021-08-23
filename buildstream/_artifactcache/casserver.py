#
#  Copyright (C) 2018 Codethink Limited
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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

from concurrent import futures
import logging
import os
import signal
import sys
import tempfile
import uuid
import errno
import threading

import click
import grpc

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.google.bytestream import bytestream_pb2, bytestream_pb2_grpc
from .._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc

from .._exceptions import CASError

from .cascache import CASCache


# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024


# Trying to push an artifact that is too large
class ArtifactTooLargeException(Exception):
    pass


# We need a message handler because this will own an ArtifactCache
# which can in turn fire messages.
def message_handler(message, context):
    logging.info(message.message)
    logging.info(message.detail)


# create_server():
#
# Create gRPC CAS artifact server as specified in the Remote Execution API.
#
# Args:
#     repo (str): Path to CAS repository
#     enable_push (bool): Whether to allow blob uploads and artifact updates
#
def create_server(repo, *, enable_push,
                  max_head_size=int(10e9),
                  min_head_size=int(2e9)):
    cas = CASCache(os.path.abspath(repo))

    # Use max_workers default from Python 3.5+
    max_workers = (os.cpu_count() or 1) * 5
    server = grpc.server(futures.ThreadPoolExecutor(max_workers))

    cache_cleaner = _CacheCleaner(cas, max_head_size, min_head_size)

    bytestream_pb2_grpc.add_ByteStreamServicer_to_server(
        _ByteStreamServicer(cas, cache_cleaner, enable_push=enable_push), server)

    remote_execution_pb2_grpc.add_ContentAddressableStorageServicer_to_server(
        _ContentAddressableStorageServicer(cas, cache_cleaner, enable_push=enable_push), server)

    remote_execution_pb2_grpc.add_CapabilitiesServicer_to_server(
        _CapabilitiesServicer(), server)

    buildstream_pb2_grpc.add_ReferenceStorageServicer_to_server(
        _ReferenceStorageServicer(cas, enable_push=enable_push), server)

    return server


@click.command(short_help="CAS Artifact Server")
@click.option('--port', '-p', type=click.INT, required=True, help="Port number")
@click.option('--server-key', help="Private server key for TLS (PEM-encoded)")
@click.option('--server-cert', help="Public server certificate for TLS (PEM-encoded)")
@click.option('--client-certs', help="Public client certificates for TLS (PEM-encoded)")
@click.option('--enable-push', default=False, is_flag=True,
              help="Allow clients to upload blobs and update artifact cache")
@click.option('--head-room-min', type=click.INT,
              help="Disk head room minimum in bytes",
              default=2e9)
@click.option('--head-room-max', type=click.INT,
              help="Disk head room maximum in bytes",
              default=10e9)
@click.argument('repo')
def server_main(repo, port, server_key, server_cert, client_certs, enable_push,
                head_room_min, head_room_max):
    server = create_server(repo,
                           max_head_size=head_room_max,
                           min_head_size=head_room_min,
                           enable_push=enable_push)

    use_tls = bool(server_key)

    if bool(server_cert) != use_tls:
        click.echo("ERROR: --server-key and --server-cert are both required for TLS", err=True)
        sys.exit(-1)

    if client_certs and not use_tls:
        click.echo("ERROR: --client-certs can only be used with --server-key", err=True)
        sys.exit(-1)

    if use_tls:
        # Read public/private key pair
        with open(server_key, 'rb') as f:
            server_key_bytes = f.read()
        with open(server_cert, 'rb') as f:
            server_cert_bytes = f.read()

        if client_certs:
            with open(client_certs, 'rb') as f:
                client_certs_bytes = f.read()
        else:
            client_certs_bytes = None

        credentials = grpc.ssl_server_credentials([(server_key_bytes, server_cert_bytes)],
                                                  root_certificates=client_certs_bytes,
                                                  require_client_auth=bool(client_certs))
        server.add_secure_port('[::]:{}'.format(port), credentials)
    else:
        server.add_insecure_port('[::]:{}'.format(port))

    # Run artifact server
    server.start()
    try:
        while True:
            signal.pause()
    except KeyboardInterrupt:
        server.stop(0)


class _ByteStreamServicer(bytestream_pb2_grpc.ByteStreamServicer):
    def __init__(self, cas, cache_cleaner, *, enable_push):
        super().__init__()
        self.cas = cas
        self.enable_push = enable_push
        self.cache_cleaner = cache_cleaner

    def Read(self, request, context):
        resource_name = request.resource_name
        client_digest = _digest_from_download_resource_name(resource_name)
        if client_digest is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            return

        if request.read_offset > client_digest.size_bytes:
            context.set_code(grpc.StatusCode.OUT_OF_RANGE)
            return

        try:
            with open(self.cas.objpath(client_digest), 'rb') as f:
                if os.fstat(f.fileno()).st_size != client_digest.size_bytes:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    return

                if request.read_offset > 0:
                    f.seek(request.read_offset)

                remaining = client_digest.size_bytes - request.read_offset
                while remaining > 0:
                    chunk_size = min(remaining, _MAX_PAYLOAD_BYTES)
                    remaining -= chunk_size

                    response = bytestream_pb2.ReadResponse()
                    # max. 64 kB chunks
                    response.data = f.read(chunk_size)
                    yield response
        except FileNotFoundError:
            context.set_code(grpc.StatusCode.NOT_FOUND)

    def Write(self, request_iterator, context):
        response = bytestream_pb2.WriteResponse()

        if not self.enable_push:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            return response

        offset = 0
        finished = False
        resource_name = None
        with tempfile.NamedTemporaryFile(dir=self.cas.tmpdir) as out:
            for request in request_iterator:
                if finished or request.write_offset != offset:
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    return response

                if resource_name is None:
                    # First request
                    resource_name = request.resource_name
                    client_digest = _digest_from_upload_resource_name(resource_name)
                    if client_digest is None:
                        context.set_code(grpc.StatusCode.NOT_FOUND)
                        return response

                    while True:
                        if client_digest.size_bytes == 0:
                            break
                        try:
                            self.cache_cleaner.clean_up(client_digest.size_bytes)
                        except ArtifactTooLargeException as e:
                            context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                            context.set_details(str(e))
                            return response

                        try:
                            os.posix_fallocate(out.fileno(), 0, client_digest.size_bytes)
                            break
                        except OSError as e:
                            # Multiple upload can happen in the same time
                            if e.errno != errno.ENOSPC:
                                raise

                elif request.resource_name:
                    # If it is set on subsequent calls, it **must** match the value of the first request.
                    if request.resource_name != resource_name:
                        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                        return response

                if (offset + len(request.data)) > client_digest.size_bytes:
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    return response

                out.write(request.data)
                offset += len(request.data)
                if request.finish_write:
                    if client_digest.size_bytes != offset:
                        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                        return response
                    out.flush()
                    digest = self.cas.add_object(path=out.name, link_directly=True)
                    if digest.hash != client_digest.hash:
                        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                        return response
                    finished = True

        assert finished

        response.committed_size = offset
        return response


class _ContentAddressableStorageServicer(remote_execution_pb2_grpc.ContentAddressableStorageServicer):
    def __init__(self, cas, cache_cleaner, *, enable_push):
        super().__init__()
        self.cas = cas
        self.enable_push = enable_push
        self.cache_cleaner = cache_cleaner

    def FindMissingBlobs(self, request, context):
        response = remote_execution_pb2.FindMissingBlobsResponse()
        for digest in request.blob_digests:
            objpath = self.cas.objpath(digest)
            try:
                os.utime(objpath)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
                d = response.missing_blob_digests.add()
                d.hash = digest.hash
                d.size_bytes = digest.size_bytes

        return response

    def BatchReadBlobs(self, request, context):
        response = remote_execution_pb2.BatchReadBlobsResponse()
        batch_size = 0

        for digest in request.digests:
            batch_size += digest.size_bytes
            if batch_size > _MAX_PAYLOAD_BYTES:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                return response

            blob_response = response.responses.add()
            blob_response.digest.hash = digest.hash
            blob_response.digest.size_bytes = digest.size_bytes
            try:
                with open(self.cas.objpath(digest), 'rb') as f:
                    if os.fstat(f.fileno()).st_size != digest.size_bytes:
                        blob_response.status.code = grpc.StatusCode.NOT_FOUND.value[0]
                        continue

                    blob_response.data = f.read(digest.size_bytes)
            except FileNotFoundError:
                blob_response.status.code = grpc.StatusCode.NOT_FOUND.value[0]

        return response

    def BatchUpdateBlobs(self, request, context):
        response = remote_execution_pb2.BatchUpdateBlobsResponse()

        if not self.enable_push:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            return response

        batch_size = 0

        for blob_request in request.requests:
            digest = blob_request.digest

            batch_size += digest.size_bytes
            if batch_size > _MAX_PAYLOAD_BYTES:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                return response

            blob_response = response.responses.add()
            blob_response.digest.hash = digest.hash
            blob_response.digest.size_bytes = digest.size_bytes

            if len(blob_request.data) != digest.size_bytes:
                blob_response.status.code = grpc.StatusCode.FAILED_PRECONDITION
                continue

            try:
                self.cache_cleaner.clean_up(digest.size_bytes)

                with tempfile.NamedTemporaryFile(dir=self.cas.tmpdir) as out:
                    out.write(blob_request.data)
                    out.flush()
                    server_digest = self.cas.add_object(path=out.name)
                    if server_digest.hash != digest.hash:
                        blob_response.status.code = grpc.StatusCode.FAILED_PRECONDITION

            except ArtifactTooLargeException:
                blob_response.status.code = grpc.StatusCode.RESOURCE_EXHAUSTED

        return response


class _CapabilitiesServicer(remote_execution_pb2_grpc.CapabilitiesServicer):
    def GetCapabilities(self, request, context):
        response = remote_execution_pb2.ServerCapabilities()

        cache_capabilities = response.cache_capabilities
        cache_capabilities.digest_function.append(remote_execution_pb2.SHA256)
        cache_capabilities.action_cache_update_capabilities.update_enabled = False
        cache_capabilities.max_batch_total_size_bytes = _MAX_PAYLOAD_BYTES
        cache_capabilities.symlink_absolute_path_strategy = remote_execution_pb2.CacheCapabilities.ALLOWED

        response.deprecated_api_version.major = 2
        response.low_api_version.major = 2
        response.high_api_version.major = 2

        return response


class _ReferenceStorageServicer(buildstream_pb2_grpc.ReferenceStorageServicer):
    def __init__(self, cas, *, enable_push):
        super().__init__()
        self.cas = cas
        self.enable_push = enable_push

    def GetReference(self, request, context):
        response = buildstream_pb2.GetReferenceResponse()

        try:
            tree = self.cas.resolve_ref(request.key, update_mtime=True)
            try:
                self.cas.update_tree_mtime(tree)
            except FileNotFoundError:
                self.cas.remove(request.key, defer_prune=True)
                context.set_code(grpc.StatusCode.NOT_FOUND)
                return response

            response.digest.hash = tree.hash
            response.digest.size_bytes = tree.size_bytes
        except CASError:
            context.set_code(grpc.StatusCode.NOT_FOUND)

        return response

    def UpdateReference(self, request, context):
        response = buildstream_pb2.UpdateReferenceResponse()

        if not self.enable_push:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            return response

        for key in request.keys:
            self.cas.set_ref(key, request.digest)

        return response

    def Status(self, request, context):
        response = buildstream_pb2.StatusResponse()

        response.allow_updates = self.enable_push

        return response


def _digest_from_download_resource_name(resource_name):
    parts = resource_name.split('/')

    # Accept requests from non-conforming BuildStream 1.1.x clients
    if len(parts) == 2:
        parts.insert(0, 'blobs')

    if len(parts) != 3 or parts[0] != 'blobs':
        return None

    try:
        digest = remote_execution_pb2.Digest()
        digest.hash = parts[1]
        digest.size_bytes = int(parts[2])
        return digest
    except ValueError:
        return None


def _digest_from_upload_resource_name(resource_name):
    parts = resource_name.split('/')

    # Accept requests from non-conforming BuildStream 1.1.x clients
    if len(parts) == 2:
        parts.insert(0, 'uploads')
        parts.insert(1, str(uuid.uuid4()))
        parts.insert(2, 'blobs')

    if len(parts) < 5 or parts[0] != 'uploads' or parts[2] != 'blobs':
        return None

    try:
        uuid_ = uuid.UUID(hex=parts[1])
        if uuid_.version != 4:
            return None

        digest = remote_execution_pb2.Digest()
        digest.hash = parts[3]
        digest.size_bytes = int(parts[4])
        return digest
    except ValueError:
        return None


class _CacheCleaner:

    __cleanup_cache_lock = threading.Lock()

    def __init__(self, cas, max_head_size, min_head_size=int(2e9)):
        self.__cas = cas
        self.__max_head_size = max_head_size
        self.__min_head_size = min_head_size

    def __has_space(self, object_size):
        stats = os.statvfs(self.__cas.casdir)
        free_disk_space = (stats.f_bavail * stats.f_bsize) - self.__min_head_size
        total_disk_space = (stats.f_blocks * stats.f_bsize) - self.__min_head_size

        if object_size > total_disk_space:
            raise ArtifactTooLargeException("Artifact of size: {} is too large for "
                                            "the filesystem which mounts the remote "
                                            "cache".format(object_size))

        return object_size <= free_disk_space

    # _clean_up_cache()
    #
    # Keep removing Least Recently Pushed (LRP) artifacts in a cache until there
    # is enough space for the incoming artifact
    #
    # Args:
    #   object_size: The size of the object being received in bytes
    #
    # Returns:
    #   int: The total bytes removed on the filesystem
    #
    def clean_up(self, object_size):
        if self.__has_space(object_size):
            return 0

        with _CacheCleaner.__cleanup_cache_lock:
            if self.__has_space(object_size):
                # Another thread has done the cleanup for us
                return 0

            stats = os.statvfs(self.__cas.casdir)
            target_disk_space = (stats.f_bavail * stats.f_bsize) - self.__max_head_size

            # obtain a list of LRP artifacts
            LRP_objects = self.__cas.list_objects()

            removed_size = 0  # in bytes
            last_mtime = 0

            while object_size - removed_size > target_disk_space:
                try:
                    last_mtime, to_remove = LRP_objects.pop(0)  # The first element in the list is the LRP artifact
                except IndexError as e:
                    # This exception is caught if there are no more artifacts in the list
                    # LRP_artifacts. This means the the artifact is too large for the filesystem
                    # so we abort the process
                    raise ArtifactTooLargeException("Artifact of size {} is too large for "
                                                    "the filesystem which mounts the remote "
                                                    "cache".format(object_size)) from e

                try:
                    size = os.stat(to_remove).st_size
                    os.unlink(to_remove)
                    removed_size += size
                except FileNotFoundError:
                    pass

            self.__cas.clean_up_refs_until(last_mtime)

            if removed_size > 0:
                logging.info("Successfully removed {} bytes from the cache".format(removed_size))
            else:
                logging.info("No artifacts were removed from the cache.")

            return removed_size
