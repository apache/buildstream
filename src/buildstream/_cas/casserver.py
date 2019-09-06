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
from contextlib import contextmanager
import os
import signal
import sys
import tempfile
import uuid
import errno

import grpc
from google.protobuf.message import DecodeError
import click

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.google.bytestream import bytestream_pb2, bytestream_pb2_grpc
from .._protos.google.rpc import code_pb2
from .._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc, \
    artifact_pb2, artifact_pb2_grpc, source_pb2, source_pb2_grpc

from .. import utils
from .._exceptions import CASError, CASCacheError

from .cascache import CASCache


# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024


# create_server():
#
# Create gRPC CAS artifact server as specified in the Remote Execution API.
#
# Args:
#     repo (str): Path to CAS repository
#     enable_push (bool): Whether to allow blob uploads and artifact updates
#
@contextmanager
def create_server(repo, *, enable_push, quota):
    cas = CASCache(os.path.abspath(repo), cache_quota=quota, protect_session_blobs=False)

    try:
        artifactdir = os.path.join(os.path.abspath(repo), 'artifacts', 'refs')
        sourcedir = os.path.join(os.path.abspath(repo), 'source_protos')

        # Use max_workers default from Python 3.5+
        max_workers = (os.cpu_count() or 1) * 5
        server = grpc.server(futures.ThreadPoolExecutor(max_workers))

        bytestream_pb2_grpc.add_ByteStreamServicer_to_server(
            _ByteStreamServicer(cas, enable_push=enable_push), server)

        remote_execution_pb2_grpc.add_ContentAddressableStorageServicer_to_server(
            _ContentAddressableStorageServicer(cas, enable_push=enable_push), server)

        remote_execution_pb2_grpc.add_CapabilitiesServicer_to_server(
            _CapabilitiesServicer(), server)

        buildstream_pb2_grpc.add_ReferenceStorageServicer_to_server(
            _ReferenceStorageServicer(cas, enable_push=enable_push), server)

        artifact_pb2_grpc.add_ArtifactServiceServicer_to_server(
            _ArtifactServicer(cas, artifactdir), server)

        source_pb2_grpc.add_SourceServiceServicer_to_server(
            _SourceServicer(sourcedir), server)

        # Create up reference storage and artifact capabilities
        artifact_capabilities = buildstream_pb2.ArtifactCapabilities(
            allow_updates=enable_push)
        source_capabilities = buildstream_pb2.SourceCapabilities(
            allow_updates=enable_push)
        buildstream_pb2_grpc.add_CapabilitiesServicer_to_server(
            _BuildStreamCapabilitiesServicer(artifact_capabilities, source_capabilities),
            server)

        yield server

    finally:
        cas.release_resources()


@click.command(short_help="CAS Artifact Server")
@click.option('--port', '-p', type=click.INT, required=True, help="Port number")
@click.option('--server-key', help="Private server key for TLS (PEM-encoded)")
@click.option('--server-cert', help="Public server certificate for TLS (PEM-encoded)")
@click.option('--client-certs', help="Public client certificates for TLS (PEM-encoded)")
@click.option('--enable-push', default=False, is_flag=True,
              help="Allow clients to upload blobs and update artifact cache")
@click.option('--quota', type=click.INT,
              help="Maximum disk usage in bytes",
              default=10e9)
@click.argument('repo')
def server_main(repo, port, server_key, server_cert, client_certs, enable_push,
                quota):
    # Handle SIGTERM by calling sys.exit(0), which will raise a SystemExit exception,
    # properly executing cleanup code in `finally` clauses and context managers.
    # This is required to terminate buildbox-casd on SIGTERM.
    signal.signal(signal.SIGTERM, lambda signalnum, frame: sys.exit(0))

    with create_server(repo,
                       quota=quota,
                       enable_push=enable_push) as server:

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
        finally:
            server.stop(0)


class _ByteStreamServicer(bytestream_pb2_grpc.ByteStreamServicer):
    def __init__(self, cas, *, enable_push):
        super().__init__()
        self.cas = cas
        self.enable_push = enable_push

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

                os.utime(f.fileno())

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

                    try:
                        digest = self.cas.add_object(path=out.name, link_directly=True)
                    except CASCacheError as e:
                        if e.reason == "cache-too-full":
                            context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
                        else:
                            context.set_code(grpc.StatusCode.INTERNAL)
                        return response

                    if digest.hash != client_digest.hash:
                        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                        return response

                    finished = True

        assert finished

        response.committed_size = offset
        return response


class _ContentAddressableStorageServicer(remote_execution_pb2_grpc.ContentAddressableStorageServicer):
    def __init__(self, cas, *, enable_push):
        super().__init__()
        self.cas = cas
        self.enable_push = enable_push

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
                objpath = self.cas.objpath(digest)
                with open(objpath, 'rb') as f:
                    if os.fstat(f.fileno()).st_size != digest.size_bytes:
                        blob_response.status.code = code_pb2.NOT_FOUND
                        continue

                    os.utime(f.fileno())

                    blob_response.data = f.read(digest.size_bytes)
            except FileNotFoundError:
                blob_response.status.code = code_pb2.NOT_FOUND

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
                blob_response.status.code = code_pb2.FAILED_PRECONDITION
                continue

            with tempfile.NamedTemporaryFile(dir=self.cas.tmpdir) as out:
                out.write(blob_request.data)
                out.flush()

                try:
                    server_digest = self.cas.add_object(path=out.name)
                except CASCacheError as e:
                    if e.reason == "cache-too-full":
                        blob_response.status.code = code_pb2.RESOURCE_EXHAUSTED
                    else:
                        blob_response.status.code = code_pb2.INTERNAL
                    continue

                if server_digest.hash != digest.hash:
                    blob_response.status.code = code_pb2.FAILED_PRECONDITION

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
                self.cas.remove(request.key)
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


class _ArtifactServicer(artifact_pb2_grpc.ArtifactServiceServicer):

    def __init__(self, cas, artifactdir):
        super().__init__()
        self.cas = cas
        self.artifactdir = artifactdir
        os.makedirs(artifactdir, exist_ok=True)

    def GetArtifact(self, request, context):
        artifact_path = os.path.join(self.artifactdir, request.cache_key)
        if not os.path.exists(artifact_path):
            context.abort(grpc.StatusCode.NOT_FOUND, "Artifact proto not found")

        artifact = artifact_pb2.Artifact()
        with open(artifact_path, 'rb') as f:
            artifact.ParseFromString(f.read())

        # Now update mtimes of files present.
        try:

            if str(artifact.files):
                self.cas.update_tree_mtime(artifact.files)

            if str(artifact.buildtree):
                # buildtrees might not be there
                try:
                    self.cas.update_tree_mtime(artifact.buildtree)
                except FileNotFoundError:
                    pass

            if str(artifact.public_data):
                os.utime(self.cas.objpath(artifact.public_data))

            for log_file in artifact.logs:
                os.utime(self.cas.objpath(log_file.digest))

        except FileNotFoundError:
            os.unlink(artifact_path)
            context.abort(grpc.StatusCode.NOT_FOUND,
                          "Artifact files incomplete")
        except DecodeError:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          "Artifact files not valid")

        return artifact

    def UpdateArtifact(self, request, context):
        artifact = request.artifact

        # Check that the files specified are in the CAS
        self._check_directory("files", artifact.files, context)

        # Unset protocol buffers don't evaluated to False but do return empty
        # strings, hence str()
        if str(artifact.public_data):
            self._check_file("public data", artifact.public_data, context)

        for log_file in artifact.logs:
            self._check_file("log digest", log_file.digest, context)

        # Add the artifact proto to the cas
        artifact_path = os.path.join(self.artifactdir, request.cache_key)
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        with utils.save_file_atomic(artifact_path, mode='wb') as f:
            f.write(artifact.SerializeToString())

        return artifact

    def ArtifactStatus(self, request, context):
        return artifact_pb2.ArtifactStatusResponse()

    def _check_directory(self, name, digest, context):
        try:
            directory = remote_execution_pb2.Directory()
            with open(self.cas.objpath(digest), 'rb') as f:
                directory.ParseFromString(f.read())
        except FileNotFoundError:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "Artifact {} specified but no files found".format(name))
        except DecodeError:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "Artifact {} specified but directory not found".format(name))

    def _check_file(self, name, digest, context):
        if not os.path.exists(self.cas.objpath(digest)):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "Artifact {} specified but not found".format(name))


class _BuildStreamCapabilitiesServicer(buildstream_pb2_grpc.CapabilitiesServicer):
    def __init__(self, artifact_capabilities, source_capabilities):
        self.artifact_capabilities = artifact_capabilities
        self.source_capabilities = source_capabilities

    def GetCapabilities(self, request, context):
        response = buildstream_pb2.ServerCapabilities()
        response.artifact_capabilities.CopyFrom(self.artifact_capabilities)
        response.source_capabilities.CopyFrom(self.source_capabilities)
        return response


class _SourceServicer(source_pb2_grpc.SourceServiceServicer):
    def __init__(self, sourcedir):
        self.sourcedir = sourcedir

    def GetSource(self, request, context):
        try:
            source_proto = self._get_source(request.cache_key)
        except FileNotFoundError:
            context.abort(grpc.StatusCode.NOT_FOUND, "Source not found")
        except DecodeError:
            context.abort(grpc.StatusCode.NOT_FOUND,
                          "Sources gives invalid directory")

        return source_proto

    def UpdateSource(self, request, context):
        self._set_source(request.cache_key, request.source)
        return request.source

    def _get_source(self, cache_key):
        path = os.path.join(self.sourcedir, cache_key)
        source_proto = source_pb2.Source()
        with open(path, 'r+b') as f:
            source_proto.ParseFromString(f.read())
            os.utime(path)
            return source_proto

    def _set_source(self, cache_key, source_proto):
        path = os.path.join(self.sourcedir, cache_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with utils.save_file_atomic(path, 'w+b') as f:
            f.write(source_proto.SerializeToString())


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
