#
#  Copyright (C) 2018 Codethink Limited
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
#  Authors:
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

from concurrent import futures
from enum import Enum
import contextlib
import logging
import os
import signal
import sys

import grpc
import click

from .._protos.build.bazel.remote.asset.v1 import remote_asset_pb2_grpc
from .._protos.build.bazel.remote.execution.v2 import (
    remote_execution_pb2,
    remote_execution_pb2_grpc,
)
from .._protos.google.bytestream import bytestream_pb2_grpc
from .._protos.buildstream.v2 import (
    buildstream_pb2,
    buildstream_pb2_grpc,
)

# Note: We'd ideally like to avoid imports from the core codebase as
# much as possible, since we're expecting to eventually split this
# module off into its own project.
#
# Not enough that we'd like to duplicate code, but enough that we want
# to make it very obvious what we're using, so in this case we import
# the specific methods we'll be using.
from ..utils import save_file_atomic, _remove_path_with_parents
from .casdprocessmanager import CASDProcessManager


# The default limit for gRPC messages is 4 MiB.
# Limit payload to 1 MiB to leave sufficient headroom for metadata.
_MAX_PAYLOAD_BYTES = 1024 * 1024


# LogLevel():
#
# Manage log level choices using click.
#
class LogLevel(click.Choice):
    # Levels():
    #
    # Represents the actual buildbox-casd log level.
    #
    class Levels(Enum):
        WARNING = "warning"
        INFO = "info"
        TRACE = "trace"

    def __init__(self):
        super().__init__([m.lower() for m in LogLevel.Levels._member_names_])  # pylint: disable=no-member

    def convert(self, value, param, ctx) -> "LogLevel.Levels":
        return LogLevel.Levels(super().convert(value, param, ctx))

    @classmethod
    def get_logging_equivalent(cls, level) -> int:
        equivalents = {
            cls.Levels.WARNING: logging.WARNING,
            cls.Levels.INFO: logging.INFO,
            cls.Levels.TRACE: logging.DEBUG,
        }

        return equivalents[level]


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
def create_server(repo, *, enable_push, quota, index_only, log_level=LogLevel.Levels.WARNING):
    logger = logging.getLogger("buildstream._cas.casserver")
    logger.setLevel(LogLevel.get_logging_equivalent(log_level))
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt="%(levelname)s: %(funcName)s: %(message)s"))
    logger.addHandler(handler)

    casd_manager = CASDProcessManager(
        os.path.abspath(repo), os.path.join(os.path.abspath(repo), "logs"), log_level, quota, False
    )
    casd_channel = casd_manager.create_channel()

    try:
        root = os.path.abspath(repo)

        # Use max_workers default from Python 3.5+
        max_workers = (os.cpu_count() or 1) * 5
        server = grpc.server(futures.ThreadPoolExecutor(max_workers))

        if not index_only:
            bytestream_pb2_grpc.add_ByteStreamServicer_to_server(
                _ByteStreamServicer(casd_channel, enable_push=enable_push), server
            )

            remote_execution_pb2_grpc.add_ContentAddressableStorageServicer_to_server(
                _ContentAddressableStorageServicer(casd_channel, enable_push=enable_push), server
            )

        remote_execution_pb2_grpc.add_CapabilitiesServicer_to_server(_CapabilitiesServicer(), server)

        # Remote Asset API
        remote_asset_pb2_grpc.add_FetchServicer_to_server(_FetchServicer(casd_channel), server)
        if enable_push:
            remote_asset_pb2_grpc.add_PushServicer_to_server(_PushServicer(casd_channel), server)

        # BuildStream protocols
        buildstream_pb2_grpc.add_ReferenceStorageServicer_to_server(
            _ReferenceStorageServicer(casd_channel, root, enable_push=enable_push), server
        )

        yield server

    finally:
        casd_channel.close()
        casd_manager.release_resources()


@click.command(short_help="CAS Artifact Server")
@click.option("--port", "-p", type=click.INT, required=True, help="Port number")
@click.option("--server-key", help="Private server key for TLS (PEM-encoded)")
@click.option("--server-cert", help="Public server certificate for TLS (PEM-encoded)")
@click.option("--client-certs", help="Public client certificates for TLS (PEM-encoded)")
@click.option("--enable-push", is_flag=True, help="Allow clients to upload blobs and update artifact cache")
@click.option("--quota", type=click.INT, default=10e9, show_default=True, help="Maximum disk usage in bytes")
@click.option(
    "--index-only",
    is_flag=True,
    help='Only provide the BuildStream artifact and source services ("index"), not the CAS ("storage")',
)
@click.option("--log-level", type=LogLevel(), help="The log level to launch with", default="warning")
@click.argument("repo")
def server_main(repo, port, server_key, server_cert, client_certs, enable_push, quota, index_only, log_level):
    # Handle SIGTERM by calling sys.exit(0), which will raise a SystemExit exception,
    # properly executing cleanup code in `finally` clauses and context managers.
    # This is required to terminate buildbox-casd on SIGTERM.
    signal.signal(signal.SIGTERM, lambda signalnum, frame: sys.exit(0))

    with create_server(
        repo, quota=quota, enable_push=enable_push, index_only=index_only, log_level=log_level
    ) as server:

        use_tls = bool(server_key)

        if bool(server_cert) != use_tls:
            click.echo("ERROR: --server-key and --server-cert are both required for TLS", err=True)
            sys.exit(-1)

        if client_certs and not use_tls:
            click.echo("ERROR: --client-certs can only be used with --server-key", err=True)
            sys.exit(-1)

        if use_tls:
            # Read public/private key pair
            with open(server_key, "rb") as f:
                server_key_bytes = f.read()
            with open(server_cert, "rb") as f:
                server_cert_bytes = f.read()

            if client_certs:
                with open(client_certs, "rb") as f:
                    client_certs_bytes = f.read()
            else:
                client_certs_bytes = None

            credentials = grpc.ssl_server_credentials(
                [(server_key_bytes, server_cert_bytes)],
                root_certificates=client_certs_bytes,
                require_client_auth=bool(client_certs),
            )
            server.add_secure_port("[::]:{}".format(port), credentials)
        else:
            server.add_insecure_port("[::]:{}".format(port))

        # Run artifact server
        server.start()
        try:
            while True:
                signal.pause()
        finally:
            server.stop(0)


class _ByteStreamServicer(bytestream_pb2_grpc.ByteStreamServicer):
    def __init__(self, casd, *, enable_push):
        super().__init__()
        self.bytestream = casd.get_bytestream()
        self.enable_push = enable_push
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def Read(self, request, context):
        self.logger.debug("Reading %s", request.resource_name)
        try:
            return self.bytestream.Read(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())

    def Write(self, request_iterator, context):
        # Note that we can't easily give more information because the
        # data is stuck in an iterator that will be consumed if read.
        self.logger.debug("Writing data")
        try:
            return self.bytestream.Write(request_iterator)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())


class _ContentAddressableStorageServicer(remote_execution_pb2_grpc.ContentAddressableStorageServicer):
    def __init__(self, casd, *, enable_push):
        super().__init__()
        self.cas = casd.get_cas()
        self.enable_push = enable_push
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def FindMissingBlobs(self, request, context):
        self.logger.info("Finding '%s'", request.blob_digests)
        try:
            return self.cas.FindMissingBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())

    def BatchReadBlobs(self, request, context):
        self.logger.info("Reading '%s'", request.digests)
        try:
            return self.cas.BatchReadBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())

    def BatchUpdateBlobs(self, request, context):
        self.logger.info("Updating: '%s'", [request.digest for request in request.requests])
        try:
            return self.cas.BatchUpdateBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())


class _CapabilitiesServicer(remote_execution_pb2_grpc.CapabilitiesServicer):
    def __init__(self):
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def GetCapabilities(self, request, context):
        self.logger.info("Retrieving capabilities")
        response = remote_execution_pb2.ServerCapabilities()

        cache_capabilities = response.cache_capabilities
        cache_capabilities.digest_function.append(remote_execution_pb2.DigestFunction.SHA256)
        cache_capabilities.action_cache_update_capabilities.update_enabled = False
        cache_capabilities.max_batch_total_size_bytes = _MAX_PAYLOAD_BYTES
        cache_capabilities.symlink_absolute_path_strategy = remote_execution_pb2.SymlinkAbsolutePathStrategy.ALLOWED

        response.deprecated_api_version.major = 2
        response.low_api_version.major = 2
        response.high_api_version.major = 2

        return response


class _FetchServicer(remote_asset_pb2_grpc.FetchServicer):
    def __init__(self, casd):
        super().__init__()
        self.fetch = casd.get_asset_fetch()
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def FetchBlob(self, request, context):
        self.logger.debug("FetchBlob '%s'", request.uris)
        try:
            return self.fetch.FetchBlob(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())

    def FetchDirectory(self, request, context):
        self.logger.debug("FetchDirectory '%s'", request.uris)
        try:
            return self.fetch.FetchDirectory(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())


class _PushServicer(remote_asset_pb2_grpc.PushServicer):
    def __init__(self, casd):
        super().__init__()
        self.push = casd.get_asset_push()
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def PushBlob(self, request, context):
        self.logger.debug("PushBlob '%s'", request.uris)
        try:
            return self.push.PushBlob(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())

    def PushDirectory(self, request, context):
        self.logger.debug("PushDirectory '%s'", request.uris)
        try:
            return self.push.PushDirectory(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())


class _ReferenceStorageServicer(buildstream_pb2_grpc.ReferenceStorageServicer):
    def __init__(self, casd, cas_root, *, enable_push):
        super().__init__()
        self.cas = casd.get_cas()
        self.root = cas_root
        self.enable_push = enable_push
        self.logger = logging.getLogger("buildstream._cas.casserver")
        self.tmpdir = os.path.join(self.root, "tmp")
        self.casdir = os.path.join(self.root, "cas")
        self.refdir = os.path.join(self.casdir, "refs", "heads")
        os.makedirs(self.tmpdir, exist_ok=True)

    # ref_path():
    #
    # Get the path to a digest's file.
    #
    # Args:
    #     ref - The ref of the digest.
    #
    # Returns:
    #     str - The path to the digest's file.
    #
    def ref_path(self, ref: str) -> str:
        return os.path.join(self.refdir, ref)

    # set_ref():
    #
    # Create or update a ref with a new digest.
    #
    # Args:
    #     ref - The ref of the digest.
    #     tree - The digest to write.
    #
    def set_ref(self, ref: str, tree):
        ref_path = self.ref_path(ref)

        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        with save_file_atomic(ref_path, "wb", tempdir=self.tmpdir) as f:
            f.write(tree.SerializeToString())

    # resolve_ref():
    #
    # Resolve a ref to a digest.
    #
    # Args:
    #     ref (str): The name of the ref
    #
    # Returns:
    #     (Digest): The digest stored in the ref
    #
    def resolve_ref(self, ref):
        ref_path = self.ref_path(ref)

        with open(ref_path, "rb") as f:
            os.utime(ref_path)

            digest = remote_execution_pb2.Digest()
            digest.ParseFromString(f.read())
            return digest

    def GetReference(self, request, context):
        self.logger.debug("'%s'", request.key)
        response = buildstream_pb2.GetReferenceResponse()

        try:
            digest = self.resolve_ref(request.key)
        except FileNotFoundError:
            with contextlib.suppress(FileNotFoundError):
                _remove_path_with_parents(self.refdir, request.key)

            context.set_code(grpc.StatusCode.NOT_FOUND)
            return response

        response.digest.hash = digest.hash
        response.digest.size_bytes = digest.size_bytes

        return response

    def UpdateReference(self, request, context):
        self.logger.debug("%s -> %s", request.keys, request.digest)
        response = buildstream_pb2.UpdateReferenceResponse()

        if not self.enable_push:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            return response

        for key in request.keys:
            self.set_ref(key, request.digest)

        return response

    def Status(self, request, context):
        self.logger.debug("Retrieving status")
        response = buildstream_pb2.StatusResponse()

        response.allow_updates = self.enable_push

        return response
