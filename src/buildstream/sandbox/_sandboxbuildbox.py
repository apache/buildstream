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

import os
import sys
import signal
import subprocess
from contextlib import ExitStack

import psutil

from .. import utils, _signals, ProgramNotFoundError
from . import Sandbox, SandboxFlags
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from ..storage._casbaseddirectory import CasBasedDirectory
from .._exceptions import SandboxError


# SandboxBuidBox()
#
# BuildBox-based sandbox implementation.
#
class SandboxBuildBox(Sandbox):

    def __init__(self, context, project, directory, **kwargs):
        if kwargs.get('allow_real_directory'):
            raise SandboxError("BuildBox does not support real directories")
        else:
            kwargs['allow_real_directory'] = False
        super().__init__(context, project, directory, **kwargs)

    @classmethod
    def check_available(cls):
        try:
            utils.get_host_tool('buildbox')
        except utils.ProgramNotFoundError as Error:
            cls._dummy_reasons += ["buildbox not found"]
            raise SandboxError(" and ".join(cls._dummy_reasons),
                               reason="unavailable-local-sandbox") from Error

    @classmethod
    def check_sandbox_config(cls, platform, config):
        # Report error for elements requiring non-0 UID/GID
        # TODO
        if config.build_uid != 0 or config.build_gid != 0:
            return False

        # Check host os and architecture match
        if config.build_os != platform.get_host_os():
            raise SandboxError("Configured and host OS don't match.")
        elif config.build_arch != platform.get_host_arch():
            raise SandboxError("Configured and host architecture don't match.")

        return True

    def _run(self, command, flags, *, cwd, env):
        stdout, stderr = self._get_output()

        root_directory = self.get_virtual_directory()
        scratch_directory = self._get_scratch_directory()

        if not self._has_command(command[0], env):
            raise SandboxError("Staged artifacts do not provide command "
                               "'{}'".format(command[0]),
                               reason='missing-command')

        # Grab the full path of the buildbox binary
        try:
            buildbox_command = [utils.get_host_tool('buildbox')]
        except ProgramNotFoundError as Err:
            raise SandboxError(("BuildBox not on path, you are using the BuildBox sandbox because "
                                "BST_FORCE_SANDBOX=buildbox")) from Err

        for mark in self._get_marked_directories():
            path = mark['directory']
            assert path.startswith('/') and len(path) > 1
            root_directory.descend(*path[1:].split(os.path.sep), create=True)

        digest = root_directory._get_digest()
        with open(os.path.join(scratch_directory, 'in'), 'wb') as input_digest_file:
            input_digest_file.write(digest.SerializeToString())

        buildbox_command += ["--local=" + root_directory.cas_cache.casdir]
        buildbox_command += ["--input-digest=in"]
        buildbox_command += ["--output-digest=out"]

        common_details = ("BuildBox is a experimental sandbox and does not support the requested feature.\n"
                          "You are using this feature because BST_FORCE_SANDBOX=buildbox.")

        if not flags & SandboxFlags.NETWORK_ENABLED:
            # TODO
            self._issue_warning(
                "BuildBox sandbox does not have Networking yet",
                detail=common_details
            )

        if cwd is not None:
            buildbox_command += ['--chdir=' + cwd]

        # In interactive mode, we want a complete devpts inside
        # the container, so there is a /dev/console and such. In
        # the regular non-interactive sandbox, we want to hand pick
        # a minimal set of devices to expose to the sandbox.
        #
        if flags & SandboxFlags.INTERACTIVE:
            # TODO
            self._issue_warning(
                "BuildBox sandbox does not fully support BuildStream shells yet",
                detail=common_details
            )

        if flags & SandboxFlags.ROOT_READ_ONLY:
            # TODO
            self._issue_warning(
                "BuildBox sandbox does not fully support BuildStream `Read only Root`",
                detail=common_details
            )

        # Set UID and GID
        if not flags & SandboxFlags.INHERIT_UID:
            # TODO
            self._issue_warning(
                "BuildBox sandbox does not fully support BuildStream Inherit UID",
                detail=common_details
            )

        os.makedirs(os.path.join(scratch_directory, 'mnt'), exist_ok=True)
        buildbox_command += ['mnt']

        # Add the command
        buildbox_command += command

        # Use the MountMap context manager to ensure that any redirected
        # mounts through fuse layers are in context and ready for buildbox
        # to mount them from.
        #
        with ExitStack() as stack:
            # Ensure the cwd exists
            if cwd is not None and len(cwd) > 1:
                assert cwd.startswith('/')
                root_directory.descend(*cwd[1:].split(os.path.sep), create=True)

            # If we're interactive, we want to inherit our stdin,
            # otherwise redirect to /dev/null, ensuring process
            # disconnected from terminal.
            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin
            else:
                stdin = stack.enter_context(open(os.devnull, "r"))

            # Run buildbox !
            exit_code = self.run_buildbox(buildbox_command, stdin, stdout, stderr, env,
                                          interactive=(flags & SandboxFlags.INTERACTIVE),
                                          cwd=scratch_directory)

            if exit_code == 0:
                with open(os.path.join(scratch_directory, 'out'), 'rb') as output_digest_file:
                    output_digest = remote_execution_pb2.Digest()
                    output_digest.ParseFromString(output_digest_file.read())
                    self._vdir = CasBasedDirectory(root_directory.cas_cache, digest=output_digest)

        return exit_code

    def run_buildbox(self, argv, stdin, stdout, stderr, env, *, interactive, cwd):
        def kill_proc():
            if process:
                # First attempt to gracefully terminate
                proc = psutil.Process(process.pid)
                proc.terminate()

                try:
                    proc.wait(20)
                except psutil.TimeoutExpired:
                    utils._kill_process_tree(process.pid)

        def suspend_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGSTOP)

        def resume_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGCONT)

        with _signals.suspendable(suspend_proc, resume_proc), _signals.terminator(kill_proc):
            process = subprocess.Popen(
                argv,
                close_fds=True,
                env=env,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                start_new_session=interactive
            )

            # Wait for the child process to finish, ensuring that
            # a SIGINT has exactly the effect the user probably
            # expects (i.e. let the child process handle it).
            try:
                while True:
                    try:
                        _, status = os.waitpid(process.pid, 0)
                        # If the process exits due to a signal, we
                        # brutally murder it to avoid zombies
                        if not os.WIFEXITED(status):
                            utils._kill_process_tree(process.pid)

                    # Unlike in the bwrap case, here only the main
                    # process seems to receive the SIGINT. We pass
                    # on the signal to the child and then continue
                    # to wait.
                    except KeyboardInterrupt:
                        process.send_signal(signal.SIGINT)
                        continue

                    break
            # If we can't find the process, it has already died of
            # its own accord, and therefore we don't need to check
            # or kill anything.
            except psutil.NoSuchProcess:
                pass

            # Return the exit code - see the documentation for
            # os.WEXITSTATUS to see why this is required.
            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
            else:
                exit_code = -1

        return exit_code

    def _use_cas_based_directory(self):
        # Always use CasBasedDirectory for BuildBox
        return True
