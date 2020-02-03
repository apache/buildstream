#
#  Copyright (C) 2018-2019 Bloomberg Finance LP
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

import os
import shlex

from .sandbox import Sandbox, SandboxCommandError, _SandboxBatch
from .. import utils
from .._exceptions import ImplError, SandboxError
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2


# SandboxREAPI()
#
# Abstract class providing a skeleton for sandbox implementations based on
# the Remote Execution API.
#
class SandboxREAPI(Sandbox):
    def _use_cas_based_directory(self):
        # Always use CasBasedDirectory for REAPI
        return True

    def _run(self, command, flags, *, cwd, env):
        stdout, stderr = self._get_output()

        context = self._get_context()
        cascache = context.get_cascache()

        # set up virtual dircetory
        vdir = self.get_virtual_directory()

        if not self._has_command(command[0], env):
            raise SandboxCommandError(
                "Staged artifacts do not provide command " "'{}'".format(command[0]), reason="missing-command"
            )

        # Ensure working directory exists
        if len(cwd) > 1:
            assert cwd.startswith("/")
            vdir.descend(*cwd[1:].split(os.path.sep), create=True)

        # Ensure directories required for sandboxed execution exist
        for directory in ["dev", "proc", "tmp"]:
            vdir.descend(directory, create=True)

        # Create directories for all marked directories. This emulates
        # some of the behaviour of other sandboxes, which create these
        # to use as mount points.
        mount_sources = self._get_mount_sources()
        for mark in self._get_marked_directories():
            directory = mark["directory"]
            if directory in mount_sources:
                continue
            # Create each marked directory
            vdir.descend(*directory.split(os.path.sep), create=True)

        # Generate Action proto
        input_root_digest = vdir._get_digest()
        command_proto = self._create_command(command, cwd, env)
        command_digest = cascache.add_object(buffer=command_proto.SerializeToString())
        action = remote_execution_pb2.Action(command_digest=command_digest, input_root_digest=input_root_digest)

        action_result = self._execute_action(action, flags)  # pylint: disable=assignment-from-no-return

        # Get output of build
        self._process_job_output(
            action_result.output_directories, action_result.output_files, failure=action_result.exit_code != 0
        )

        if stdout:
            if action_result.stdout_raw:
                stdout.write(str(action_result.stdout_raw, "utf-8", errors="ignore"))
        if stderr:
            if action_result.stderr_raw:
                stderr.write(str(action_result.stderr_raw, "utf-8", errors="ignore"))

        # Non-zero exit code means a normal error during the build:
        # the remote execution system has worked correctly but the command failed.
        return action_result.exit_code

    def _create_command(self, command, working_directory, environment):
        # Creates a command proto
        environment_variables = [
            remote_execution_pb2.Command.EnvironmentVariable(name=k, value=v) for (k, v) in environment.items()
        ]

        # Request the whole directory tree as output
        output_directory = os.path.relpath(os.path.sep, start=working_directory)

        return remote_execution_pb2.Command(
            arguments=command,
            working_directory=working_directory[1:],
            environment_variables=environment_variables,
            output_files=[],
            output_directories=[output_directory],
            platform=None,
        )

    def _process_job_output(self, output_directories, output_files, *, failure):
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
        if not output_directories:
            error_text = "No output directory was returned from the build server."
            raise SandboxError(error_text)
        if len(output_directories) > 1:
            error_text = "More than one output directory was returned from the build server: {}."
            raise SandboxError(error_text.format(output_directories))

        tree_digest = output_directories[0].tree_digest
        if tree_digest is None or not tree_digest.hash:
            raise SandboxError("Output directory structure had no digest attached.")

        context = self._get_context()
        cascache = context.get_cascache()

        # Get digest of root directory from tree digest
        tree = remote_execution_pb2.Tree()
        with open(cascache.objpath(tree_digest), "rb") as f:
            tree.ParseFromString(f.read())
        root_directory = tree.root.SerializeToString()
        dir_digest = utils._message_digest(root_directory)

        # At the moment, we will get the whole directory back in the first directory argument and we need
        # to replace the sandbox's virtual directory with that. Creating a new virtual directory object
        # from another hash will be interesting, though...

        vdir = self.get_virtual_directory()
        vdir._reset(digest=dir_digest)

    def _create_batch(self, main_group, flags, *, collect=None):
        return _SandboxREAPIBatch(self, main_group, flags, collect=collect)

    def _execute_action(self, action, flags):
        raise ImplError("Sandbox of type '{}' does not implement _execute_action()".format(type(self).__name__))


# _SandboxREAPIBatch()
#
# Command batching by shell script generation.
#
class _SandboxREAPIBatch(_SandboxBatch):
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
        if first:
            context = self.sandbox._get_context()
            with context.messenger.timed_activity(
                "Running commands",
                detail=self.main_group.combined_label(),
                element_name=self.sandbox._get_element_name(),
            ):
                if self.sandbox.run(["sh", "-c", "-e", self.script], self.flags, cwd=first.cwd, env=first.env) != 0:
                    raise SandboxCommandError("Command failed", collect=self.collect)

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
        cmdline = " ".join(shlex.quote(cmd) for cmd in command.command)
        self.script += "(set -ex; {})".format(cmdline)

        # Error handling
        label = command.label or cmdline
        quoted_label = shlex.quote("'{}'".format(label))
        self.script += " || (echo Command {} failed with exitcode $? >&2 ; exit 1)\n".format(quoted_label)

    def execute_call(self, call):
        raise SandboxError("SandboxRemote does not support callbacks in command batches")
