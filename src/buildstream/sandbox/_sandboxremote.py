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
import shlex
from collections import namedtuple
from urllib.parse import urlparse
from functools import partial

import grpc

from .. import utils
from .._message import Message, MessageType
from .sandbox import Sandbox, SandboxCommandError, _SandboxBatch
from ..storage.directory import VirtualDirectoryError
from ..storage._casbaseddirectory import CasBasedDirectory
from .. import _signals
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.google.rpc import code_pb2
from .._exceptions import BstError, SandboxError
from .. import _yaml
from .._protos.google.longrunning import operations_pb2, operations_pb2_grpc
from .._cas import CASRemote, CASRemoteSpec


class RemoteExecutionSpec(namedtuple('RemoteExecutionSpec', 'exec_service storage_service action_service')):
    pass


# SandboxRemote()
#
# This isn't really a sandbox, it's a stub which sends all the sources and build
# commands to a remote server and retrieves the results from it.
#
class SandboxRemote(Sandbox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._output_files_required = kwargs.get('output_files_required', True)

        config = kwargs['specs']  # This should be a RemoteExecutionSpec
        if config is None:
            return

        # gRPC doesn't support fork without exec, which is used in the main process.
        assert not utils._is_main_process()

        self.storage_url = config.storage_service['url']
        self.exec_url = config.exec_service['url']

        exec_certs = {}
        for key in ['client-cert', 'client-key', 'server-cert']:
            if key in config.exec_service:
                with open(config.exec_service[key], 'rb') as f:
                    exec_certs[key] = f.read()

        self.exec_credentials = grpc.ssl_channel_credentials(
            root_certificates=exec_certs.get('server-cert'),
            private_key=exec_certs.get('client-key'),
            certificate_chain=exec_certs.get('client-cert'))

        action_certs = {}
        for key in ['client-cert', 'client-key', 'server-cert']:
            if key in config.action_service:
                with open(config.action_service[key], 'rb') as f:
                    action_certs[key] = f.read()

        if config.action_service:
            self.action_url = config.action_service['url']
            self.action_instance = config.action_service.get('instance-name', None)
            self.action_credentials = grpc.ssl_channel_credentials(
                root_certificates=action_certs.get('server-cert'),
                private_key=action_certs.get('client-key'),
                certificate_chain=action_certs.get('client-cert'))
        else:
            self.action_url = None
            self.action_instance = None
            self.action_credentials = None

        self.exec_instance = config.exec_service.get('instance-name', None)
        self.storage_instance = config.storage_service.get('instance-name', None)

        self.storage_remote_spec = CASRemoteSpec(self.storage_url, push=True,
                                                 server_cert=config.storage_service.get('server-cert'),
                                                 client_key=config.storage_service.get('client-key'),
                                                 client_cert=config.storage_service.get('client-cert'),
                                                 instance_name=self.storage_instance)
        self.operation_name = None

    def info(self, msg):
        self._get_context().messenger.message(Message(None, MessageType.INFO, msg))

    @staticmethod
    def specs_from_config_node(config_node, basedir=None):

        def require_node(config, keyname):
            val = config.get_mapping(keyname, default=None)
            if val is None:
                provenance = _yaml.node_get_provenance(remote_config, key=keyname)
                raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                                      "{}: '{}' was not present in the remote "
                                      "execution configuration (remote-execution). "
                                      .format(str(provenance), keyname))
            return val

        remote_config = config_node.get_mapping('remote-execution', default=None)
        if remote_config is None:
            return None

        service_keys = ['execution-service', 'storage-service', 'action-cache-service']

        _yaml.node_validate(remote_config, ['url', *service_keys])

        exec_config = require_node(remote_config, 'execution-service')
        storage_config = require_node(remote_config, 'storage-service')
        action_config = remote_config.get_mapping('action-cache-service', default={})

        tls_keys = ['client-key', 'client-cert', 'server-cert']

        _yaml.node_validate(exec_config, ['url', 'instance-name', *tls_keys])
        _yaml.node_validate(storage_config, ['url', 'instance-name', *tls_keys])
        if action_config:
            _yaml.node_validate(action_config, ['url', 'instance-name', *tls_keys])

        # Maintain some backwards compatibility with older configs, in which
        # 'url' was the only valid key for remote-execution:
        if 'url' in remote_config:
            if 'execution-service' not in remote_config:
                exec_config = _yaml.Node.from_dict({'url': remote_config['url']})
            else:
                provenance = _yaml.node_get_provenance(remote_config, key='url')
                raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                                      "{}: 'url' and 'execution-service' keys were found in the remote "
                                      "execution configuration (remote-execution). "
                                      "You can only specify one of these."
                                      .format(str(provenance)))

        service_configs = [exec_config, storage_config, action_config]

        def resolve_path(path):
            if basedir and path:
                return os.path.join(basedir, path)
            else:
                return path

        for config_key, config in zip(service_keys, service_configs):
            # Either both or none of the TLS client key/cert pair must be specified:
            if ('client-key' in config) != ('client-cert' in config):
                provenance = _yaml.node_get_provenance(remote_config, key=config_key)
                raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                                      "{}: TLS client key/cert pair is incomplete. "
                                      "You must specify both 'client-key' and 'client-cert' "
                                      "for authenticated HTTPS connections."
                                      .format(str(provenance)))

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
        request = remote_execution_pb2.ExecuteRequest(instance_name=self.exec_instance,
                                                      action_digest=action_digest,
                                                      skip_cache_lookup=False)

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
                    raise SandboxError("Failed contacting remote execution server at {}."
                                       .format(self.exec_url))

                elif status_code in (grpc.StatusCode.INVALID_ARGUMENT,
                                     grpc.StatusCode.FAILED_PRECONDITION,
                                     grpc.StatusCode.RESOURCE_EXHAUSTED,
                                     grpc.StatusCode.INTERNAL,
                                     grpc.StatusCode.DEADLINE_EXCEEDED):
                    raise SandboxError("{} ({}).".format(e.details(), status_code.name))

                elif running_operation and status_code == grpc.StatusCode.UNIMPLEMENTED:
                    raise SandboxError("Failed trying to recover from connection loss: "
                                       "server does not support operation status polling recovery.")

            return last_operation

        # Set up signal handler to trigger cancel_operation on SIGTERM
        operation = None
        with self._get_context().messenger.timed_activity("Waiting for the remote build to complete"), \
                _signals.terminator(partial(self.cancel_operation, channel)):
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
        request = operations_pb2.CancelOperationRequest(
            name=str(self.operation_name))

        try:
            stub.CancelOperation(request)
        except grpc.RpcError as e:
            if (e.code() == grpc.StatusCode.UNIMPLEMENTED or
                    e.code() == grpc.StatusCode.INVALID_ARGUMENT):
                pass
            else:
                raise SandboxError("Failed trying to send CancelOperation request: "
                                   "{} ({})".format(e.details(), e.code().name))

    def process_job_output(self, output_directories, output_files, *, failure):
        # Reads the remote execution server response to an execution request.
        #
        # output_directories is an array of OutputDirectory objects.
        # output_files is an array of OutputFile objects.
        #
        # We only specify one output_directory, so it's an error
        # for there to be any output files or more than one directory at the moment.
        #
        if output_files:
            raise SandboxError("Output files were returned when we didn't request any.")
        elif not output_directories:
            error_text = "No output directory was returned from the build server."
            raise SandboxError(error_text)
        elif len(output_directories) > 1:
            error_text = "More than one output directory was returned from the build server: {}."
            raise SandboxError(error_text.format(output_directories))

        tree_digest = output_directories[0].tree_digest
        if tree_digest is None or not tree_digest.hash:
            raise SandboxError("Output directory structure had no digest attached.")

        context = self._get_context()
        project = self._get_project()
        cascache = context.get_cascache()
        artifactcache = context.artifactcache
        casremote = CASRemote(self.storage_remote_spec)

        # Now do a pull to ensure we have the full directory structure.
        dir_digest = cascache.pull_tree(casremote, tree_digest)
        if dir_digest is None or not dir_digest.hash or not dir_digest.size_bytes:
            raise SandboxError("Output directory structure pulling from remote failed.")

        # At the moment, we will get the whole directory back in the first directory argument and we need
        # to replace the sandbox's virtual directory with that. Creating a new virtual directory object
        # from another hash will be interesting, though...

        new_dir = CasBasedDirectory(context.artifactcache.cas, digest=dir_digest)
        self._set_virtual_directory(new_dir)

        # Fetch the file blobs if needed
        if self._output_files_required or artifactcache.has_push_remotes():
            required_blobs = []
            directories = []

            directories.append(self._output_directory)
            if self._build_directory and (self._build_directory_always or failure):
                directories.append(self._build_directory)

            for directory in directories:
                try:
                    vdir = new_dir.descend(*directory.strip(os.sep).split(os.sep))
                    dir_digest = vdir._get_digest()
                    required_blobs += cascache.required_blobs_for_directory(dir_digest)
                except VirtualDirectoryError:
                    # If the directory does not exist, there is no need to
                    # download file blobs.
                    pass

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

                remote_missing_blobs = cascache.fetch_blobs(casremote, blobs_to_fetch)
                if remote_missing_blobs:
                    raise SandboxError("{} output files are missing on the CAS server"
                                       .format(len(remote_missing_blobs)))

    def _run(self, command, flags, *, cwd, env):
        stdout, stderr = self._get_output()

        context = self._get_context()
        project = self._get_project()
        cascache = context.get_cascache()
        artifactcache = context.artifactcache

        # set up virtual dircetory
        upload_vdir = self.get_virtual_directory()

        # Create directories for all marked directories. This emulates
        # some of the behaviour of other sandboxes, which create these
        # to use as mount points.
        for mark in self._get_marked_directories():
            directory = mark['directory']
            # Create each marked directory
            upload_vdir.descend(*directory.split(os.path.sep), create=True)

        # Generate action_digest first
        input_root_digest = upload_vdir._get_digest()
        command_proto = self._create_command(command, cwd, env)
        command_digest = utils._message_digest(command_proto.SerializeToString())
        action = remote_execution_pb2.Action(command_digest=command_digest,
                                             input_root_digest=input_root_digest)
        action_digest = utils._message_digest(action.SerializeToString())

        # Next, try to create a communication channel to the BuildGrid server.
        url = urlparse(self.exec_url)
        if not url.port:
            raise SandboxError("You must supply a protocol and port number in the execution-service url, "
                               "for example: http://buildservice:50051.")
        if url.scheme == 'http':
            channel = grpc.insecure_channel('{}:{}'.format(url.hostname, url.port))
        elif url.scheme == 'https':
            channel = grpc.secure_channel('{}:{}'.format(url.hostname, url.port), self.exec_credentials)
        else:
            raise SandboxError("Remote execution currently only supports the 'http' protocol "
                               "and '{}' was supplied.".format(url.scheme))

        # check action cache download and download if there
        action_result = self._check_action_cache(action_digest)

        if not action_result:
            casremote = CASRemote(self.storage_remote_spec)
            try:
                casremote.init()
            except grpc.RpcError as e:
                raise SandboxError("Failed to contact remote execution CAS endpoint at {}: {}"
                                   .format(self.storage_url, e)) from e

            # Determine blobs missing on remote
            try:
                missing_blobs = cascache.remote_missing_blobs_for_directory(casremote, input_root_digest)
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

            # Now, push the missing blobs to the remote.
            try:
                cascache.send_blobs(casremote, missing_blobs)
            except grpc.RpcError as e:
                raise SandboxError("Failed to push source directory to remote: {}".format(e)) from e

            # Push command and action
            try:
                casremote.push_message(command_proto)
            except grpc.RpcError as e:
                raise SandboxError("Failed to push command to remote: {}".format(e))

            try:
                casremote.push_message(action)
            except grpc.RpcError as e:
                raise SandboxError("Failed to push action to remote: {}".format(e))

            # Now request to execute the action
            operation = self.run_remote_command(channel, action_digest)
            action_result = self._extract_action_result(operation)

        # Get output of build
        self.process_job_output(action_result.output_directories, action_result.output_files,
                                failure=action_result.exit_code != 0)

        if stdout:
            if action_result.stdout_raw:
                stdout.write(str(action_result.stdout_raw, 'utf-8', errors='ignore'))
        if stderr:
            if action_result.stderr_raw:
                stderr.write(str(action_result.stderr_raw, 'utf-8', errors='ignore'))

        if action_result.exit_code != 0:
            # A normal error during the build: the remote execution system
            # has worked correctly but the command failed.
            return action_result.exit_code

        return 0

    def _check_action_cache(self, action_digest):
        # Checks the action cache to see if this artifact has already been built
        #
        # Should return either the action response or None if not found, raise
        # Sandboxerror if other grpc error was raised
        if not self.action_url:
            return None
        url = urlparse(self.action_url)
        if not url.port:
            raise SandboxError("You must supply a protocol and port number in the action-cache-service url, "
                               "for example: http://buildservice:50051.")
        if url.scheme == 'http':
            channel = grpc.insecure_channel('{}:{}'.format(url.hostname, url.port))
        elif url.scheme == 'https':
            channel = grpc.secure_channel('{}:{}'.format(url.hostname, url.port), self.action_credentials)

        request = remote_execution_pb2.GetActionResultRequest(instance_name=self.action_instance,
                                                              action_digest=action_digest)
        stub = remote_execution_pb2_grpc.ActionCacheStub(channel)
        try:
            result = stub.GetActionResult(request)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise SandboxError("Failed to query action cache: {} ({})"
                                   .format(e.code(), e.details()))
            else:
                return None
        else:
            self.info("Action result found in action cache")
            return result

    def _create_command(self, command, working_directory, environment):
        # Creates a command proto
        environment_variables = [remote_execution_pb2.Command.
                                 EnvironmentVariable(name=k, value=v)
                                 for (k, v) in environment.items()]

        # Request the whole directory tree as output
        output_directory = os.path.relpath(os.path.sep, start=working_directory)

        return remote_execution_pb2.Command(arguments=command,
                                            working_directory=working_directory,
                                            environment_variables=environment_variables,
                                            output_files=[],
                                            output_directories=[output_directory],
                                            platform=None)

    @staticmethod
    def _extract_action_result(operation):
        if operation is None:
            # Failure of remote execution, usually due to an error in BuildStream
            raise SandboxError("No response returned from server")

        assert not operation.HasField('error') and operation.HasField('response')

        execution_response = remote_execution_pb2.ExecuteResponse()
        # The response is expected to be an ExecutionResponse message
        assert operation.response.Is(execution_response.DESCRIPTOR)

        operation.response.Unpack(execution_response)

        if execution_response.status.code != code_pb2.OK:
            # An unexpected error during execution: the remote execution
            # system failed at processing the execution request.
            if execution_response.status.message:
                raise SandboxError(execution_response.status.message)
            else:
                raise SandboxError("Remote server failed at executing the build request.")

        return execution_response.result

    def _create_batch(self, main_group, flags, *, collect=None):
        return _SandboxRemoteBatch(self, main_group, flags, collect=collect)

    def _use_cas_based_directory(self):
        # Always use CasBasedDirectory for remote execution
        return True


# _SandboxRemoteBatch()
#
# Command batching by shell script generation.
#
class _SandboxRemoteBatch(_SandboxBatch):

    def __init__(self, sandbox, main_group, flags, *, collect=None):
        super().__init__(sandbox, main_group, flags, collect=collect)

        self.script = None
        self.first_command = None
        self.cwd = None
        self.env = None

    def execute(self):
        self.script = ""

        self.main_group.execute(self)

        first = self.first_command
        if first and self.sandbox.run(['sh', '-c', '-e', self.script], self.flags, cwd=first.cwd, env=first.env) != 0:
            raise SandboxCommandError("Command execution failed", collect=self.collect)

    def execute_group(self, group):
        group.execute_children(self)

    def execute_command(self, command):
        if self.first_command is None:
            # First command in batch
            # Initial working directory and environment of script already matches
            # the command configuration.
            self.first_command = command
        else:
            # Change working directory for this command
            if command.cwd != self.cwd:
                self.script += "mkdir -p {}\n".format(command.cwd)
                self.script += "cd {}\n".format(command.cwd)

            # Update environment for this command
            for key in self.env.keys():
                if key not in command.env:
                    self.script += "unset {}\n".format(key)
            for key, value in command.env.items():
                if key not in self.env or self.env[key] != value:
                    self.script += "export {}={}\n".format(key, shlex.quote(value))

        # Keep track of current working directory and environment
        self.cwd = command.cwd
        self.env = command.env

        # Actual command execution
        cmdline = ' '.join(shlex.quote(cmd) for cmd in command.command)
        self.script += "(set -ex; {})".format(cmdline)

        # Error handling
        label = command.label or cmdline
        quoted_label = shlex.quote("'{}'".format(label))
        self.script += " || (echo Command {} failed with exitcode $? >&2 ; exit 1)\n".format(quoted_label)

    def execute_call(self, call):
        raise SandboxError("SandboxRemote does not support callbacks in command batches")
