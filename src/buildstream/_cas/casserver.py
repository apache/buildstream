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
from enum import Enum
import contextlib
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
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


# LogLevel():
#
# Represents the buildbox-casd log level.
#
class LogLevel(Enum):
    WARNING = "warning"
    INFO = "info"
    TRACE = "trace"

    @classmethod
    def get_logging_equivalent(cls, level: 'LogLevel') -> int:
        equivalents = {
            cls.WARNING: logging.WARNING,
            cls.INFO: logging.INFO,
            cls.TRACE: logging.DEBUG
        }

        # Yes, logging.WARNING/INFO/DEBUG are ints
        # I also don't know why
        return equivalents[level]


class ClickLogLevel(click.Choice):
    def __init__(self):
        super().__init__([m.lower() for m in LogLevel._member_names_])  # pylint: disable=no-member

    def convert(self, value, param, ctx):
        return LogLevel(super().convert(value, param, ctx))


# CASdRunner():
#
# Manage a buildbox-casd process.
#
# FIXME: Probably better to replace this with the work from !1638
#
class CASdRunner:
    def __init__(self, path: str, *, cache_quota: int = None, log_level: LogLevel = LogLevel.WARNING):
        self.root = path
        self.casdir = os.path.join(path, "cas")
        self.tmpdir = os.path.join(path, "tmp")

        self._casd_process = None
        self._casd_socket_path = None
        self._casd_socket_tempdir = None
        self._log_level = log_level
        self._quota = cache_quota

    # start_casd():
    #
    # Start the CASd process.
    #
    def start_casd(self):
        assert not self._casd_process, "CASd was already started"

        os.makedirs(os.path.join(self.casdir, "refs", "heads"), exist_ok=True)
        os.makedirs(os.path.join(self.casdir, "objects"), exist_ok=True)
        os.makedirs(self.tmpdir, exist_ok=True)

        # Place socket in global/user temporary directory to avoid hitting
        # the socket path length limit.
        self._casd_socket_tempdir = tempfile.mkdtemp(prefix="buildstream")
        self._casd_socket_path = os.path.join(self._casd_socket_tempdir, "casd.sock")

        casd_args = [utils.get_host_tool("buildbox-casd")]
        casd_args.append("--bind=unix:" + self._casd_socket_path)
        casd_args.append("--log-level=" + self._log_level.value)

        if self._quota is not None:
            casd_args.append("--quota-high={}".format(int(self._quota)))
            casd_args.append("--quota-low={}".format(int(self._quota / 2)))

        casd_args.append(self.root)

        blocked_signals = signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGINT])

        try:
            self._casd_process = subprocess.Popen(
                casd_args,
                cwd=self.root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked_signals)

    # stop():
    #
    # Stop and tear down the CASd process.
    #
    def stop(self):
        return_code = self._casd_process.poll()

        if return_code is not None:
            self._casd_process = None
            logging.error(
                "Buildbox-casd died during the run. Exit code: %s", return_code
            )
            logging.error(self._casd_process.stdout.read().decode())
            return

        self._casd_process.terminate()

        try:
            return_code = self._casd_process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress():
                try:
                    return_code = self._casd_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self._casd_process.kill()
                    self._casd_process.wait(timeout=15)
                    logging.warning(
                        "Buildbox-casd didn't exit in time and has been killed"
                    )
                    logging.error(self._casd_process.stdout.read().decode())
                    self._casd_process = None
                    return

        if return_code != 0:
            logging.error(
                "Buildbox-casd didn't exit cleanly. Exit code: %d", return_code
            )
            logging.error(self._casd_process.stdout.read().decode())

        self._casd_process = None

    # get_socket_path():
    #
    # Get the path to the socket of the CASd process - None if the
    # process has not been started yet.
    #
    def get_socket_path(self) -> str:
        assert self._casd_socket_path is not None, "CASd has not been started"
        return self._casd_socket_path

    # get_casdir():
    #
    # Get the path to the directory managed by CASd.
    #
    def get_casdir(self) -> str:
        return self.casdir


# create_server():
#
# Create gRPC CAS artifact server as specified in the Remote Execution API.
#
# Args:
#     repo (str): Path to CAS repository
#     enable_push (bool): Whether to allow blob uploads and artifact updates
#     index_only (bool): Whether to store CAS blobs or only artifacts
#
@contextlib.contextmanager
def create_server(repo, *, enable_push, quota, index_only, log_level=LogLevel.WARNING):
    logger = logging.getLogger('casserver')
    logger.setLevel(LogLevel.get_logging_equivalent(log_level))
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(LogLevel.get_logging_equivalent(log_level))
    logger.addHandler(handler)

    cas = CASCache(os.path.abspath(repo), cache_quota=quota, protect_session_blobs=False)
    cas_runner = CASdRunner(os.path.abspath(repo), cache_quota=quota)
    cas_runner.start_casd()

    try:
        artifactdir = os.path.join(os.path.abspath(repo), 'artifacts', 'refs')
        sourcedir = os.path.join(os.path.abspath(repo), 'source_protos')

        # Use max_workers default from Python 3.5+
        max_workers = (os.cpu_count() or 1) * 5
        server = grpc.server(futures.ThreadPoolExecutor(max_workers))

        if not index_only:
            bytestream_pb2_grpc.add_ByteStreamServicer_to_server(
                _ByteStreamServicer(cas, enable_push=enable_push), server)

            remote_execution_pb2_grpc.add_ContentAddressableStorageServicer_to_server(
                _ContentAddressableStorageServicer(cas, enable_push=enable_push), server)

        remote_execution_pb2_grpc.add_CapabilitiesServicer_to_server(
            _CapabilitiesServicer(), server)

        buildstream_pb2_grpc.add_ReferenceStorageServicer_to_server(
            _ReferenceStorageServicer(cas, enable_push=enable_push), server)

        artifact_pb2_grpc.add_ArtifactServiceServicer_to_server(
            _ArtifactServicer(cas, artifactdir, update_cas=not index_only), server)

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
        cas_runner.stop()


@click.command(short_help="CAS Artifact Server")
@click.option('--port', '-p', type=click.INT, required=True, help="Port number")
@click.option('--server-key', help="Private server key for TLS (PEM-encoded)")
@click.option('--server-cert', help="Public server certificate for TLS (PEM-encoded)")
@click.option('--client-certs', help="Public client certificates for TLS (PEM-encoded)")
@click.option('--enable-push', is_flag=True,
              help="Allow clients to upload blobs and update artifact cache")
@click.option('--quota', type=click.INT, default=10e9, show_default=True,
              help="Maximum disk usage in bytes")
@click.option('--index-only', is_flag=True,
              help="Only provide the BuildStream artifact and source services (\"index\"), not the CAS (\"storage\")")
@click.option('--log-level', type=ClickLogLevel(),
              help="The log level to launch with")
@click.argument('repo')
def server_main(repo, port, server_key, server_cert, client_certs, enable_push,
                quota, index_only, log_level):
    # Handle SIGTERM by calling sys.exit(0), which will raise a SystemExit exception,
    # properly executing cleanup code in `finally` clauses and context managers.
    # This is required to terminate buildbox-casd on SIGTERM.
    signal.signal(signal.SIGTERM, lambda signalnum, frame: sys.exit(0))

    with create_server(repo,
                       quota=quota,
                       enable_push=enable_push,
                       index_only=index_only,
                       log_level=log_level) as server:

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
        self.logger = logging.getLogger("casserver")

    def Read(self, request, context):
        self.logger.info("Read")
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
        self.logger.info("Write")
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
        self.logger = logging.getLogger("casserver")

    def FindMissingBlobs(self, request, context):
        self.logger.info("FindMissingBlobs")
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
        self.logger.info("BatchReadBlobs")
        self.logger.debug(request.digests)
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
        self.logger.info("BatchUpdateBlobs")
        self.logger.debug([request.digest for request in request.requests])
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
    def __init__(self):
        self.logger = logging.getLogger("casserver")

    def GetCapabilities(self, request, context):
        self.logger.info("GetCapabilities")
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
        self.logger = logging.getLogger("casserver")

    def GetReference(self, request, context):
        self.logger.debug("GetReference")
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
        self.logger.debug("UpdateReference")
        response = buildstream_pb2.UpdateReferenceResponse()

        if not self.enable_push:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            return response

        for key in request.keys:
            self.cas.set_ref(key, request.digest)

        return response

    def Status(self, request, context):
        self.logger.debug("Status")
        response = buildstream_pb2.StatusResponse()

        response.allow_updates = self.enable_push

        return response


class _ArtifactServicer(artifact_pb2_grpc.ArtifactServiceServicer):

    def __init__(self, cas, artifactdir, *, update_cas=True):
        super().__init__()
        self.cas = cas
        self.artifactdir = artifactdir
        self.update_cas = update_cas
        os.makedirs(artifactdir, exist_ok=True)
        self.logger = logging.getLogger("casserver")

    def GetArtifact(self, request, context):
        self.logger.info("GetArtifact")
        self.logger.debug(request.cache_key)
        artifact_path = os.path.join(self.artifactdir, request.cache_key)
        if not os.path.exists(artifact_path):
            context.abort(grpc.StatusCode.NOT_FOUND, "Artifact proto not found")

        artifact = artifact_pb2.Artifact()
        with open(artifact_path, 'rb') as f:
            artifact.ParseFromString(f.read())

        # Artifact-only servers will not have blobs on their system,
        # so we can't reasonably update their mtimes. Instead, we exit
        # early, and let the CAS server deal with its blobs.
        #
        # FIXME: We could try to run FindMissingBlobs on the other
        #        server. This is tricky to do from here, of course,
        #        because we don't know who the other server is, but
        #        the client could be smart about it - but this might
        #        make things slower.
        #
        #        It needs some more thought...
        if not self.update_cas:
            return artifact

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
        self.logger.info("UpdateArtifact")
        self.logger.debug(request.cache_key)
        artifact = request.artifact

        if self.update_cas:
            # Check that the files specified are in the CAS
            if str(artifact.files):
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
        self.logger.info("ArtifactStatus")
        return artifact_pb2.ArtifactStatusResponse()

    def _check_directory(self, name, digest, context):
        try:
            directory = remote_execution_pb2.Directory()
            with open(self.cas.objpath(digest), 'rb') as f:
                directory.ParseFromString(f.read())
        except FileNotFoundError:
            self.logger.warning("Artifact %s specified but no files found (%s)", name, self.cas.objpath(digest))
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "Artifact {} specified but no files found".format(name))
        except DecodeError:
            self.logger.warning("Artifact %s specified but directory not found (%s)", name, self.cas.objpath(digest))
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
        self.logger = logging.getLogger("casserver")

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
