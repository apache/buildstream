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

        context = self._get_context()
        cascache = context.get_cascache()

        specs = context.remote_execution_specs
        if specs is None:
            return

        self.storage_spec = specs.storage_spec
        self.exec_spec = specs.exec_spec
        self.action_spec = specs.action_spec
        self.operation_name = None

        if self.storage_spec:
            self.own_storage_remote = True
            self.storage_remote = CASRemote(self.storage_spec, cascache)
            try:
                self.storage_remote.init()
            except grpc.RpcError as e:
                raise SandboxError(
                    "Failed to contact remote execution CAS endpoint at {}: {}".format(self.storage_spec.url, e)
                ) from e
        else:
            self.own_storage_remote = False
            self.storage_remote = cascache.get_default_remote()

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
        cascache = context.get_cascache()

        # Fetch the file blobs
        if self.storage_spec:
            dir_digest = vdir._get_digest()
            required_blobs = cascache.required_blobs_for_directory(dir_digest)

            local_missing_blobs = cascache.missing_blobs(required_blobs)
            if local_missing_blobs:
                cascache.fetch_blobs(self.storage_remote, local_missing_blobs)

    def _execute_action(self, action, flags):
        stdout, stderr = self._get_output()

        context = self._get_context()
        project = self._get_project()
        cascache = context.get_cascache()
        artifactcache = context.artifactcache

        action_digest = cascache.add_object(buffer=action.SerializeToString())

        casremote = self.storage_remote

        # check action cache download and download if there
        action_result = self._check_action_cache(action_digest)

        if not action_result:
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

    def _cleanup(self):
        if self.own_storage_remote:
            self.storage_remote.close()
