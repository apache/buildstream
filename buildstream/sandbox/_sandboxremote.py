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
from urllib.parse import urlparse

import grpc

from . import Sandbox
from ..storage._filebaseddirectory import FileBasedDirectory
from ..storage._casbaseddirectory import CasBasedDirectory
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._platform import Platform


class SandboxError(Exception):
    pass


# SandboxRemote()
#
# This isn't really a sandbox, it's a stub which sends all the sources and build
# commands to a remote server and retrieves the results from it.
#
class SandboxRemote(Sandbox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        url = urlparse(kwargs['server_url'])
        if not url.scheme or not url.hostname or not url.port:
            raise SandboxError("Configured remote URL '{}' does not match the expected layout. "
                               .format(kwargs['server_url']) +
                               "It should be of the form <protocol>://<domain name>:<port>.")
        elif url.scheme != 'http':
            raise SandboxError("Configured remote '{}' uses an unsupported protocol. "
                               "Only plain HTTP is currenlty supported (no HTTPS).")

        self.server_url = '{}:{}'.format(url.hostname, url.port)

    def run_remote_command(self, command, input_root_digest, working_directory, environment):
        # Sends an execution request to the remote execution server.
        #
        # This function blocks until it gets a response from the server.
        #
        environment_variables = [remote_execution_pb2.Command.
                                 EnvironmentVariable(name=k, value=v)
                                 for (k, v) in environment.items()]

        # Create and send the Command object.
        remote_command = remote_execution_pb2.Command(arguments=command,
                                                      working_directory=working_directory,
                                                      environment_variables=environment_variables,
                                                      output_files=[],
                                                      output_directories=[self._output_directory],
                                                      platform=None)
        platform = Platform.get_platform()
        cascache = platform.artifactcache
        # Upload the Command message to the remote CAS server
        command_digest = cascache.push_message(self._get_project(), remote_command)
        if not command_digest or not cascache.verify_digest_pushed(self._get_project(), command_digest):
            # Command push failed
            return None

        # Create and send the action.
        action = remote_execution_pb2.Action(command_digest=command_digest,
                                             input_root_digest=input_root_digest,
                                             timeout=None,
                                             do_not_cache=False)

        # Upload the Action message to the remote CAS server
        action_digest = cascache.push_message(self._get_project(), action)
        if not action_digest or not cascache.verify_digest_pushed(self._get_project(), action_digest):
            # Action push failed
            return None

        # Next, try to create a communication channel to the BuildGrid server.
        channel = grpc.insecure_channel(self.server_url)
        stub = remote_execution_pb2_grpc.ExecutionStub(channel)
        request = remote_execution_pb2.ExecuteRequest(action_digest=action_digest,
                                                      skip_cache_lookup=False)
        try:
            operation_iterator = stub.Execute(request)
        except grpc.RpcError:
            return None

        operation = None
        with self._get_context().timed_activity("Waiting for the remote build to complete"):
            # It is advantageous to check operation_iterator.code() is grpc.StatusCode.OK here,
            # which will check the server is actually contactable. However, calling it when the
            # server is available seems to cause .code() to hang forever.
            for operation in operation_iterator:
                if operation.done:
                    break

        return operation

    def process_job_output(self, output_directories, output_files):
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

        platform = Platform.get_platform()
        cascache = platform.artifactcache
        # Now do a pull to ensure we have the necessary parts.
        dir_digest = cascache.pull_tree(self._get_project(), tree_digest)
        if dir_digest is None or not dir_digest.hash or not dir_digest.size_bytes:
            raise SandboxError("Output directory structure pulling from remote failed.")

        path_components = os.path.split(self._output_directory)

        # Now what we have is a digest for the output. Once we return, the calling process will
        # attempt to descend into our directory and find that directory, so we need to overwrite
        # that.

        if not path_components:
            # The artifact wants the whole directory; we could just return the returned hash in its
            # place, but we don't have a means to do that yet.
            raise SandboxError("Unimplemented: Output directory is empty or equal to the sandbox root.")

        # At the moment, we will get the whole directory back in the first directory argument and we need
        # to replace the sandbox's virtual directory with that. Creating a new virtual directory object
        # from another hash will be interesting, though...

        new_dir = CasBasedDirectory(self._get_context(), ref=dir_digest)
        self._set_virtual_directory(new_dir)

    def run(self, command, flags, *, cwd=None, env=None):
        # Upload sources
        upload_vdir = self.get_virtual_directory()

        if isinstance(upload_vdir, FileBasedDirectory):
            # Make a new temporary directory to put source in
            upload_vdir = CasBasedDirectory(self._get_context(), ref=None)
            upload_vdir.import_files(self.get_virtual_directory()._get_underlying_directory())

        upload_vdir.recalculate_hash()

        platform = Platform.get_platform()
        cascache = platform.artifactcache
        # Now, push that key (without necessarily needing a ref) to the remote.
        cascache.push_directory(self._get_project(), upload_vdir)
        if not cascache.verify_digest_pushed(self._get_project(), upload_vdir.ref):
            raise SandboxError("Failed to verify that source has been pushed to the remote artifact cache.")

        # Set up environment and working directory
        if cwd is None:
            cwd = self._get_work_directory()

        if cwd is None:
            cwd = '/'

        if env is None:
            env = self._get_environment()

        # We want command args as a list of strings
        if isinstance(command, str):
            command = [command]

        # Now transmit the command to execute
        operation = self.run_remote_command(command, upload_vdir.ref, cwd, env)

        if operation is None:
            # Failure of remote execution, usually due to an error in BuildStream
            # NB This error could be raised in __run_remote_command
            raise SandboxError("No response returned from server")

        assert not operation.HasField('error') and operation.HasField('response')

        execution_response = remote_execution_pb2.ExecuteResponse()
        # The response is expected to be an ExecutionResponse message
        assert operation.response.Is(execution_response.DESCRIPTOR)

        operation.response.Unpack(execution_response)

        if execution_response.status.code != 0:
            # A normal error during the build: the remote execution system
            # has worked correctly but the command failed.
            # execution_response.error also contains 'message' (str) and
            # 'details' (iterator of Any) which we ignore at the moment.
            return execution_response.status.code

        action_result = execution_response.result

        self.process_job_output(action_result.output_directories, action_result.output_files)

        return 0
