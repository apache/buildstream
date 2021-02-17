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

import shutil
from functools import partial

import grpc

from ._sandboxreapi import SandboxREAPI
from .. import _signals
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.google.rpc import code_pb2
from .._exceptions import BstError, SandboxError
from .._protos.google.longrunning import operations_pb2, operations_pb2_grpc
from .._cas import CASRemote


# SandboxRemote()
#
# This isn't really a sandbox, it's a stub which sends all the sources and build
# commands to a remote server and retrieves the results from it.
#
class SandboxRemote(SandboxREAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._output_files_required = kwargs.get("output_files_required", True)

        context = self._get_context()
        specs = context.remote_execution_specs
        if specs is None:
            return

        self.storage_spec = specs.storage_spec
        self.exec_spec = specs.exec_spec
        self.action_spec = specs.action_spec
        self.operation_name = None

    def run_remote_command(self, channel, action_digest):
        # Sends an execution request to the remote execution server.
        #
        # This function blocks until it gets a response from the server.

        # Try to create a communication channel to the BuildGrid server.
        stub = remote_execution_pb2_grpc.ExecutionStub(channel)
        request = remote_execution_pb2.ExecuteRequest(
            instance_name=self.exec_spec.instance_name, action_digest=action_digest, skip_cache_lookup=False
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

                if status_code in (
                    grpc.StatusCode.INVALID_ARGUMENT,
                    grpc.StatusCode.FAILED_PRECONDITION,
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    grpc.StatusCode.INTERNAL,
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                    grpc.StatusCode.UNAVAILABLE,
                ):
                    raise SandboxError(
                        "Failed contacting remote execution server at {}."
                        "{}: {}".format(self.exec_spec.url, status_code.name, e.details())
                    )

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

            local_missing_blobs = cascache.missing_blobs(required_blobs)
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

                with CASRemote(self.storage_spec, cascache) as casremote:
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
            with CASRemote(self.storage_spec, cascache) as casremote:
                try:
                    casremote.init()
                except grpc.RpcError as e:
                    raise SandboxError(
                        "Failed to contact remote execution CAS endpoint at {}: {}".format(self.storage_spec.url, e)
                    ) from e

                with self._get_context().messenger.timed_activity(
                    "Uploading input root", element_name=self._get_element_name()
                ):
                    # Determine blobs missing on remote
                    try:
                        input_root_digest = action.input_root_digest
                        missing_blobs = list(cascache.missing_blobs_for_directory(input_root_digest, remote=casremote))
                    except grpc.RpcError as e:
                        raise SandboxError("Failed to determine missing blobs: {}".format(e)) from e

                    # Check if any blobs are also missing locally (partial artifact)
                    # and pull them from the artifact cache.
                    try:
                        local_missing_blobs = cascache.missing_blobs(missing_blobs)
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

            # Now request to execute the action
            channel = self.exec_spec.open_channel()
            with channel:
                operation = self.run_remote_command(channel, action_digest)
                action_result = self._extract_action_result(operation)

        # Fetch outputs
        with CASRemote(self.storage_spec, cascache) as casremote:
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
                with cascache.open(action_result.stdout_digest, "r") as f:
                    shutil.copyfileobj(f, stdout)
            elif action_result.stdout_raw:
                stdout.write(str(action_result.stdout_raw, "utf-8", errors="ignore"))
        if stderr:
            if action_result.stderr_digest.hash:
                with cascache.open(action_result.stderr_digest, "r") as f:
                    shutil.copyfileobj(f, stderr)
            elif action_result.stderr_raw:
                stderr.write(str(action_result.stderr_raw, "utf-8", errors="ignore"))

        return action_result

    def _check_action_cache(self, action_digest):
        # Checks the action cache to see if this artifact has already been built
        #
        # Should return either the action response or None if not found, raise
        # Sandboxerror if other grpc error was raised
        if not self.action_spec:
            return None

        channel = self.action_spec.open_channel()
        with channel:
            request = remote_execution_pb2.GetActionResultRequest(
                instance_name=self.action_spec.instance_name, action_digest=action_digest
            )
            stub = remote_execution_pb2_grpc.ActionCacheStub(channel)
            try:
                result = stub.GetActionResult(request)
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise SandboxError("Failed to query action cache: {} ({})".format(e.code(), e.details()))
                return None
            else:
                context = self._get_context()
                context.messenger.info("Action result found in action cache", element_name=self._get_element_name())
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
