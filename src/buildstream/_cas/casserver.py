#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2020 Bloomberg Finance LP
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
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
from .. import _signals
from .._protos.build.bazel.remote.execution.v2 import (
    remote_execution_pb2,
    remote_execution_pb2_grpc,
)
from .._protos.google.bytestream import bytestream_pb2_grpc

# Note: We'd ideally like to avoid imports from the core codebase as
# much as possible, since we're expecting to eventually split this
# module off into its own project.
#
# Not enough that we'd like to duplicate code, but enough that we want
# to make it very obvious what we're using, so in this case we import
# the specific methods we'll be using.
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
        if isinstance(value, LogLevel.Levels):
            value = value.value

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
        os.path.abspath(repo), os.path.join(os.path.abspath(repo), "logs"), log_level, quota, None, False
    )
    casd_channel = casd_manager.create_channel()

    try:
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

        # Ensure we have the signal handler set for SIGTERM
        # This allows threads from GRPC to call our methods that do register
        # handlers at exit.
        with _signals.terminator(lambda: None):
            yield server

    finally:
        casd_channel.request_shutdown()
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
            ret = self.bytestream.Read(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret

    def Write(self, request_iterator, context):
        # Note that we can't easily give more information because the
        # data is stuck in an iterator that will be consumed if read.
        self.logger.debug("Writing data")
        try:
            ret = self.bytestream.Write(request_iterator)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret


class _ContentAddressableStorageServicer(remote_execution_pb2_grpc.ContentAddressableStorageServicer):
    def __init__(self, casd, *, enable_push):
        super().__init__()
        self.cas = casd.get_cas()
        self.enable_push = enable_push
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def FindMissingBlobs(self, request, context):
        self.logger.info("Finding '%s'", request.blob_digests)
        try:
            ret = self.cas.FindMissingBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret

    def BatchReadBlobs(self, request, context):
        self.logger.info("Reading '%s'", request.digests)
        try:
            ret = self.cas.BatchReadBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret

    def BatchUpdateBlobs(self, request, context):
        self.logger.info("Updating: '%s'", [request.digest for request in request.requests])
        try:
            ret = self.cas.BatchUpdateBlobs(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret


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
            ret = self.fetch.FetchBlob(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret

    def FetchDirectory(self, request, context):
        self.logger.debug("FetchDirectory '%s'", request.uris)
        try:
            ret = self.fetch.FetchDirectory(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret


class _PushServicer(remote_asset_pb2_grpc.PushServicer):
    def __init__(self, casd):
        super().__init__()
        self.push = casd.get_asset_push()
        self.logger = logging.getLogger("buildstream._cas.casserver")

    def PushBlob(self, request, context):
        self.logger.debug("PushBlob '%s'", request.uris)
        try:
            ret = self.push.PushBlob(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret

    def PushDirectory(self, request, context):
        self.logger.debug("PushDirectory '%s'", request.uris)
        try:
            ret = self.push.PushDirectory(request)
        except grpc.RpcError as err:
            context.abort(err.code(), err.details())
        return ret
