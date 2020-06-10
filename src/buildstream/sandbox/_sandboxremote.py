#!/usr/bin/env python3
#
#  Copyright (C) 2018 Bloomberg LP
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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>

import os
import shutil
from collections import namedtuple
from urllib.parse import urlparse
from functools import partial

import grpc

from .. import utils
from ..node import Node
from .._message import Message, MessageType
from ._sandboxreapi import SandboxREAPI
from .. import _signals
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.google.rpc import code_pb2
from .._exceptions import BstError, SandboxError
from .. import _yaml
from .._protos.google.longrunning import operations_pb2, operations_pb2_grpc
from .._cas import CASRemote
from .._remote import RemoteSpec


class RemoteExecutionSpec(namedtuple("RemoteExecutionSpec", "exec_service storage_service action_service")):
    pass


# SandboxRemote()
#
# This isn't really a sandbox, it's a stub which sends all the sources and build
# commands to a remote server and retrieves the results from it.
#
class SandboxRemote(SandboxREAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._output_files_required = kwargs.get("output_files_required", True)

        config = kwargs["specs"]  # This should be a RemoteExecutionSpec
        if config is None:
            return

        # gRPC doesn't support fork without exec, which is used in the main process.
        assert not utils._is_main_process()

        self.storage_url = config.storage_service["url"]
        self.exec_url = config.exec_service["url"]

        exec_certs = {}
        for key in ["client-cert", "client-key", "server-cert"]:
            if key in config.exec_service:
                with open(config.exec_service[key], "rb") as f:
                    exec_certs[key] = f.read()

        self.exec_credentials = grpc.ssl_channel_credentials(
            root_certificates=exec_certs.get("server-cert"),
            private_key=exec_certs.get("client-key"),
            certificate_chain=exec_certs.get("client-cert"),
        )

        action_certs = {}
        for key in ["client-cert", "client-key", "server-cert"]:
            if key in config.action_service:
                with open(config.action_service[key], "rb") as f:
                    action_certs[key] = f.read()

        if config.action_service:
            self.action_url = config.action_service["url"]
            self.action_instance = config.action_service.get("instance-name", None)
            self.action_credentials = grpc.ssl_channel_credentials(
                root_certificates=action_certs.get("server-cert"),
                private_key=action_certs.get("client-key"),
                certificate_chain=action_certs.get("client-cert"),
            )
        else:
            self.action_url = None
            self.action_instance = None
            self.action_credentials = None

        self.exec_instance = config.exec_service.get("instance-name", None)
        self.storage_instance = config.storage_service.get("instance-name", None)

        self.storage_remote_spec = RemoteSpec(
            self.storage_url,
            push=True,
            server_cert=config.storage_service.get("server-cert"),
            client_key=config.storage_service.get("client-key"),
            client_cert=config.storage_service.get("client-cert"),
            instance_name=self.storage_instance,
        )
        self.operation_name = None

    def info(self, msg):
        self._get_context().messenger.message(Message(MessageType.INFO, msg, element_name=self._get_element_name()))

    @staticmethod
    def specs_from_config_node(config_node, basedir=None):
        def require_node(config, keyname):
            val = config.get_mapping(keyname, default=None)
            if val is None:
                provenance = remote_config.get_provenance()
                raise _yaml.LoadError(
                    "{}: '{}' was not present in the remote "
                    "execution configuration (remote-execution). ".format(str(provenance), keyname),
                    _yaml.LoadErrorReason.INVALID_DATA,
                )
            return val

        remote_config = config_node.get_mapping("remote-execution", default=None)
        if remote_config is None:
            return None

        service_keys = ["execution-service", "storage-service", "action-cache-service"]

        remote_config.validate_keys(["url", *service_keys])

        exec_config = require_node(remote_config, "execution-service")
        storage_config = require_node(remote_config, "storage-service")
        action_config = remote_config.get_mapping("action-cache-service", default={})

        tls_keys = ["client-key", "client-cert", "server-cert"]

        exec_config.validate_keys(["url", "instance-name", *tls_keys])
        storage_config.validate_keys(["url", "instance-name", *tls_keys])
        if action_config:
            action_config.validate_keys(["url", "instance-name", *tls_keys])

        # Maintain some backwards compatibility with older configs, in which
        # 'url' was the only valid key for remote-execution:
        if "url" in remote_config:
            if "execution-service" not in remote_config:
                exec_config = Node.from_dict({"url": remote_config["url"]})
            else:
                provenance = remote_config.get_node("url").get_provenance()
                raise _yaml.LoadError(
                    "{}: 'url' and 'execution-service' keys were found in the remote "
                    "execution configuration (remote-execution). "
                    "You can only specify one of these.".format(str(provenance)),
                    _yaml.LoadErrorReason.INVALID_DATA,
                )

        service_configs = [exec_config, storage_config, action_config]

        def resolve_path(path):
            if basedir and path:
                return os.path.join(basedir, path)
            else:
                return path

        for config_key, config in zip(service_keys, service_configs):
            # Either both or none of the TLS client key/cert pair must be specified:
            if ("client-key" in config) != ("client-cert" in config):
                provenance = remote_config.get_node(config_key).get_provenance()
                raise _yaml.LoadError(
                    "{}: TLS client key/cert pair is incomplete. "
                    "You must specify both 'client-key' and 'client-cert' "
                    "for authenticated HTTPS connections.".format(str(provenance)),
                    _yaml.LoadErrorReason.INVALID_DATA,
                )

            for tls_key in tls_keys:
                if tls_key in config:
                    config[tls_key] = resolve_path(config.get_str(tls_key))

        # TODO: we should probably not be stripping node info and rather load files the safe way
        return RemoteExecutionSpec(*[conf.strip_node_info() for conf in service_configs])

    def run_remote_command(self, channel, action_digest):
        # Sends an execution request to the remote execution server.
        #
        # This function blocks until it gets a response from the server.

        # Try to create a communication channel to the BuildGrid server.
        stub = remote_execution_pb2_grpc.ExecutionStub(channel)
        request = remote_execution_pb2.ExecuteRequest(
            instance_name=self.exec_instance, action_digest=action_digest, skip_cache_lookup=False
        )

        def __run_remote_command(stub, execute_request=None, running_operation=None):
            try:
                last_operation = None
                if execute_request is not None:
                    operation_iterator = stub.Execute(execute_request)
                else:
                    request = remote_execution_pb2.WaitExecutionRequest(name=running_operation.name)
                    operation_iterator = stub.WaitExecution(request)

                for operation in operation_iterator:
                    if not self.operation_name:
                        self.operation_name = operation.name
                    if operation.done:
                        return operation
                    else:
                        last_operation = operation

            except grpc.RpcError as e:
                status_code = e.code()
                if status_code == grpc.StatusCode.UNAVAILABLE:
                    raise SandboxError("Failed contacting remote execution server at {}.".format(self.exec_url))

                if status_code in (
                    grpc.StatusCode.INVALID_ARGUMENT,
                    grpc.StatusCode.FAILED_PRECONDITION,
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    grpc.StatusCode.INTERNAL,
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                ):
                    raise SandboxError("{} ({}).".format(e.details(), status_code.name))

                if running_operation and status_code == grpc.StatusCode.UNIMPLEMENTED:
                    raise SandboxError(
                        "Failed trying to recover from connection loss: "
                        "server does not support operation status polling recovery."
                    )

            return last_operation

        # Set up signal handler to trigger cancel_operation on SIGTERM
        operation = None
        with self._get_context().messenger.timed_activity(
            "Waiting for the remote build to complete", element_name=self._get_element_name()
        ), _signals.terminator(partial(self.cancel_operation, channel)):
            operation = __run_remote_command(stub, execute_request=request)
            if operation is None:
                return None
            elif operation.done:
                return operation
            while operation is not None and not operation.done:
                operation = __run_remote_command(stub, running_operation=operation)

        return operation

    def cancel_operation(self, channel):
        # If we don't have the name can't send request.
        if self.operation_name is None:
            return

        stub = operations_pb2_grpc.OperationsStub(channel)
        request = operations_pb2.CancelOperationRequest(name=str(self.operation_name))

        try:
            stub.CancelOperation(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNIMPLEMENTED or e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                pass
            else:
                raise SandboxError(
                    "Failed trying to send CancelOperation request: " "{} ({})".format(e.details(), e.code().name)
                )

    def _fetch_missing_blobs(self, vdir):
        context = self._get_context()
        project = self._get_project()
        cascache = context.get_cascache()
        artifactcache = context.artifactcache

        # Fetch the file blobs if needed
        if self._output_files_required or artifactcache.has_push_remotes():
            dir_digest = vdir._get_digest()
            required_blobs = cascache.required_blobs_for_directory(dir_digest)

            local_missing_blobs = cascache.local_missing_blobs(required_blobs)
            if local_missing_blobs:
                if self._output_files_required:
                    # Fetch all blobs from Remote Execution CAS server
                    blobs_to_fetch = local_missing_blobs
                else:
                    # Output files are not required in the local cache,
                    # however, artifact push remotes will need them.
                    # Only fetch blobs that are missing on one or multiple
                    # artifact servers.
                    blobs_to_fetch = artifactcache.find_missing_blobs(project, local_missing_blobs)

                with CASRemote(self.storage_remote_spec, cascache) as casremote:
                    cascache.fetch_blobs(casremote, blobs_to_fetch)

    def _execute_action(self, action, flags):
        stdout, stderr = self._get_output()

        context = self._get_context()
        project = self._get_project()
        cascache = context.get_cascache()
        artifactcache = context.artifactcache

        action_digest = cascache.add_object(buffer=action.SerializeToString())

        # check action cache download and download if there
        action_result = self._check_action_cache(action_digest)

        if not action_result:
            with CASRemote(self.storage_remote_spec, cascache) as casremote:
                try:
                    casremote.init()
                except grpc.RpcError as e:
                    raise SandboxError(
                        "Failed to contact remote execution CAS endpoint at {}: {}".format(self.storage_url, e)
                    ) from e

                with self._get_context().messenger.timed_activity(
                    "Uploading input root", element_name=self._get_element_name()
                ):
                    # Determine blobs missing on remote
                    try:
                        input_root_digest = action.input_root_digest
                        missing_blobs = list(cascache.remote_missing_blobs_for_directory(casremote, input_root_digest))
                    except grpc.RpcError as e:
                        raise SandboxError("Failed to determine missing blobs: {}".format(e)) from e

                    # Check if any blobs are also missing locally (partial artifact)
                    # and pull them from the artifact cache.
                    try:
                        local_missing_blobs = cascache.local_missing_blobs(missing_blobs)
                        if local_missing_blobs:
                            artifactcache.fetch_missing_blobs(project, local_missing_blobs)
                    except (grpc.RpcError, BstError) as e:
                        raise SandboxError("Failed to pull missing blobs from artifact cache: {}".format(e)) from e

                    # Add command and action messages to blob list to push
                    missing_blobs.append(action.command_digest)
                    missing_blobs.append(action_digest)

                    # Now, push the missing blobs to the remote.
                    try:
                        cascache.send_blobs(casremote, missing_blobs)
                    except grpc.RpcError as e:
                        raise SandboxError("Failed to push source directory to remote: {}".format(e)) from e

            # Next, try to create a communication channel to the BuildGrid server.
            url = urlparse(self.exec_url)
            if not url.port:
                raise SandboxError(
                    "You must supply a protocol and port number in the execution-service url, "
                    "for example: http://buildservice:50051."
                )
            if url.scheme == "http":
                channel = grpc.insecure_channel("{}:{}".format(url.hostname, url.port))
            elif url.scheme == "https":
                channel = grpc.secure_channel("{}:{}".format(url.hostname, url.port), self.exec_credentials)
            else:
                raise SandboxError(
                    "Remote execution currently only supports the 'http' protocol "
                    "and '{}' was supplied.".format(url.scheme)
                )

            # Now request to execute the action
            with channel:
                operation = self.run_remote_command(channel, action_digest)
                action_result = self._extract_action_result(operation)

        # Fetch outputs
        with CASRemote(self.storage_remote_spec, cascache) as casremote:
            for output_directory in action_result.output_directories:
                tree_digest = output_directory.tree_digest
                if tree_digest is None or not tree_digest.hash:
                    raise SandboxError("Output directory structure had no digest attached.")

                # Now do a pull to ensure we have the full directory structure.
                cascache.pull_tree(casremote, tree_digest)

            # Fetch stdout and stderr blobs
            cascache.fetch_blobs(casremote, [action_result.stdout_digest, action_result.stderr_digest])

        # Forward remote stdout and stderr
        if stdout:
            if action_result.stdout_digest.hash:
                with open(cascache.objpath(action_result.stdout_digest), "r") as f:
                    shutil.copyfileobj(f, stdout)
            elif action_result.stdout_raw:
                stdout.write(str(action_result.stdout_raw, "utf-8", errors="ignore"))
        if stderr:
            if action_result.stderr_digest.hash:
                with open(cascache.objpath(action_result.stderr_digest), "r") as f:
                    shutil.copyfileobj(f, stderr)
            elif action_result.stderr_raw:
                stderr.write(str(action_result.stderr_raw, "utf-8", errors="ignore"))

        return action_result

    def _check_action_cache(self, action_digest):
        # Checks the action cache to see if this artifact has already been built
        #
        # Should return either the action response or None if not found, raise
        # Sandboxerror if other grpc error was raised
        if not self.action_url:
            return None
        url = urlparse(self.action_url)
        if not url.port:
            raise SandboxError(
                "You must supply a protocol and port number in the action-cache-service url, "
                "for example: http://buildservice:50051."
            )
        if url.scheme == "http":
            channel = grpc.insecure_channel("{}:{}".format(url.hostname, url.port))
        elif url.scheme == "https":
            channel = grpc.secure_channel("{}:{}".format(url.hostname, url.port), self.action_credentials)

        with channel:
            request = remote_execution_pb2.GetActionResultRequest(
                instance_name=self.action_instance, action_digest=action_digest
            )
            stub = remote_execution_pb2_grpc.ActionCacheStub(channel)
            try:
                result = stub.GetActionResult(request)
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise SandboxError("Failed to query action cache: {} ({})".format(e.code(), e.details()))
                return None
            else:
                self.info("Action result found in action cache")
                return result

    @staticmethod
    def _extract_action_result(operation):
        if operation is None:
            # Failure of remote execution, usually due to an error in BuildStream
            raise SandboxError("No response returned from server")

        assert not operation.HasField("error") and operation.HasField("response")

        execution_response = remote_execution_pb2.ExecuteResponse()
        # The response is expected to be an ExecutionResponse message
        assert operation.response.Is(execution_response.DESCRIPTOR)

        operation.response.Unpack(execution_response)

        if execution_response.status.code != code_pb2.OK:
            # An unexpected error during execution: the remote execution
            # system failed at processing the execution request.
            if execution_response.status.message:
                raise SandboxError(execution_response.status.message)
            # Otherwise, report the failure in a more general manner
            raise SandboxError("Remote server failed at executing the build request.")

        return execution_response.result
