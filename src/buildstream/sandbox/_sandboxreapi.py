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

import os
import shlex

from .sandbox import Sandbox, _SandboxFlags, SandboxCommandError, _SandboxBatch
from .. import utils
from .._exceptions import ImplError, SandboxError
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2


# SandboxREAPI()
#
# Abstract class providing a skeleton for sandbox implementations based on
# the Remote Execution API.
#
class SandboxREAPI(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._output_node_properties = kwargs.get("output_node_properties")

    def _run(self, command, *, flags, cwd, env):
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
            vdir.open_directory(cwd[1:], create=True)

        # Ensure directories required for sandboxed execution exist
        for directory in ["dev", "proc", "tmp"]:
            vsubdir = vdir.open_directory(directory, create=True)
            if flags & _SandboxFlags.ROOT_READ_ONLY:
                vsubdir._set_subtree_read_only(False)

        # Create directories for all marked directories. This emulates
        # some of the behaviour of other sandboxes, which create these
        # to use as mount points.
        read_write_directories = []
        mount_sources = self._get_mount_sources()
        for directory in self._get_marked_directories():

            if directory in mount_sources:
                # Bind mount
                mount_point = directory.lstrip(os.path.sep)
                mount_source = mount_sources[directory]

                # Ensure mount point exists in sandbox
                if not vdir.exists(mount_point):
                    if os.path.isdir(mount_source):
                        # Mounting a directory, mount point must be a directory
                        vdir.open_directory(mount_point, create=True)
                    else:
                        # Mounting a file or device node, mount point must be a file
                        split_mount_point = mount_point.rsplit(os.path.sep, 1)
                        parent_vdir = vdir.open_directory(split_mount_point[0], create=True)
                        parent_vdir._create_empty_file(split_mount_point[1])
            else:
                # Read-write directory
                marked_vdir = vdir.open_directory(directory.lstrip(os.path.sep), create=True)
                read_write_directories.append(directory)
                if flags & _SandboxFlags.ROOT_READ_ONLY:
                    marked_vdir._set_subtree_read_only(False)

        if flags & _SandboxFlags.ROOT_READ_ONLY:
            vdir._set_subtree_read_only(True)
        else:
            # The whole sandbox is writable
            read_write_directories = [os.path.sep]

        # Generate Action proto
        input_root_digest = vdir._get_digest()
        platform = self._create_platform(flags)
        command_proto = self._create_command(command, cwd, env, read_write_directories, platform)
        command_digest = cascache.add_object(buffer=command_proto.SerializeToString())
        action = remote_execution_pb2.Action(
            command_digest=command_digest, input_root_digest=input_root_digest, platform=platform
        )

        action_result = self._execute_action(action, flags)  # pylint: disable=assignment-from-no-return

        # Get output of build
        self._process_job_output(
            cwd, action_result.output_directories, action_result.output_files, failure=action_result.exit_code != 0
        )

        # Non-zero exit code means a normal error during the build:
        # the remote execution system has worked correctly but the command failed.
        return action_result.exit_code

    def _create_platform(self, flags):
        config = self._get_config()

        platform_dict = {}

        platform_dict["OSFamily"] = config.build_os
        platform_dict["ISA"] = config.build_arch

        if flags & _SandboxFlags.INHERIT_UID:
            uid = os.geteuid()
            gid = os.getegid()
        else:
            uid = config.build_uid
            gid = config.build_gid
        if uid is not None:
            platform_dict["unixUID"] = str(uid)
        if gid is not None:
            platform_dict["unixGID"] = str(gid)

        if flags & _SandboxFlags.NETWORK_ENABLED:
            platform_dict["network"] = "on"

        if config.remote_apis_socket_path:
            platform_dict["remoteApisSocketPath"] = config.remote_apis_socket_path.lstrip(os.path.sep)

        # Create Platform message with properties sorted by name in code point order
        platform = remote_execution_pb2.Platform()
        for key, value in sorted(platform_dict.items()):
            platform.properties.add(name=key, value=value)

        return platform

    def _create_command(self, command, working_directory, environment, read_write_directories, platform):
        # Creates a command proto
        environment_variables = [
            remote_execution_pb2.Command.EnvironmentVariable(name=k, value=v) for (k, v) in environment.items()
        ]

        # Request read-write directories as output
        output_directories = [os.path.relpath(dir, start=working_directory) for dir in read_write_directories]

        return remote_execution_pb2.Command(
            arguments=command,
            working_directory=working_directory[1:],
            environment_variables=environment_variables,
            output_paths=output_directories,
            output_node_properties=self._output_node_properties,
            output_directory_format=remote_execution_pb2.Command.OutputDirectoryFormat.DIRECTORY_ONLY,
            platform=platform,
        )

    def _fetch_action_result_outputs(self, casremote, action_result):
        # This also ensures that the outputs are uploaded to the cache
        # storage-service, if configured

        context = self._get_context()
        cascache = context.get_cascache()

        # Fetch outputs
        for output_directory in action_result.output_directories:
            # Now do a pull to ensure we have the full directory structure.
            # We first try the root_directory_digest we requested, then fall back to tree_digest

            root_directory_digest = output_directory.root_directory_digest
            if root_directory_digest and root_directory_digest.hash:
                cascache.fetch_directory(casremote, root_directory_digest)
                continue

            tree_digest = output_directory.tree_digest
            if tree_digest and tree_digest.hash:
                cascache.pull_tree(casremote, tree_digest)
                continue

            raise SandboxError("Output directory structure had no digest attached.")

        # Fetch stdout and stderr blobs, if they exist
        blobs = []
        for digest in [action_result.stdout_digest, action_result.stderr_digest]:
            if digest.hash:
                blobs.append(digest)
        if blobs:
            cascache.fetch_blobs(casremote, blobs)

    def _process_job_output(self, working_directory, output_directories, output_files, *, failure):
        # Reads the remote execution server response to an execution request.
        #
        # output_directories is an array of OutputDirectory objects.
        # output_files is an array of OutputFile objects.
        #
        if output_files:
            raise SandboxError("Output files were returned when we didn't request any.")

        context = self._get_context()
        cascache = context.get_cascache()
        vdir = self.get_virtual_directory()

        for output_directory in output_directories:
            dir_digest = output_directory.root_directory_digest
            if dir_digest is None or not dir_digest.hash:
                tree_digest = output_directory.tree_digest
                if tree_digest is None or not tree_digest.hash:
                    raise SandboxError("Output directory structure had no digest attached.")

                # Get digest of output directory from tree digest
                tree = remote_execution_pb2.Tree()
                with open(cascache.objpath(tree_digest), "rb") as f:
                    tree.ParseFromString(f.read())
                root_directory = tree.root.SerializeToString()
                dir_digest = utils._message_digest(root_directory)

            # Create a normalized absolute path (inside the input tree)
            path = os.path.normpath(os.path.join(working_directory, output_directory.path)).lstrip(os.path.sep)

            # Get virtual directory at the path of the output directory
            vsubdir = vdir.open_directory(path, create=True)

            # Replace contents with returned output
            vsubdir._reset(digest=dir_digest)

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
                if (
                    self.sandbox._run_with_flags(
                        ["sh", "-c", "-e", self.script], flags=self.flags, cwd=first.cwd, env=first.env
                    )
                    != 0
                ):
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

    def create_empty_file(self, name):
        self.script += "touch -- {}\n".format(shlex.quote(name))

    def clean_directory(self, name):
        # Do not treat error during cleanup as a fatal build error
        self.script += "rm -rf -- {} || true\n".format(shlex.quote(name))
        if self.first_command:
            # Working directory may be a subdirectory of the build directory.
            # Recreate it if necessary as output capture requires the working directory to exist.
            self.script += "mkdir -p {} || true\n".format(shlex.quote(self.first_command.cwd))
