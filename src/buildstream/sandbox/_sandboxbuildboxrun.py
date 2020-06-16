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
import signal
import subprocess
import sys
from contextlib import ExitStack

import psutil

from .. import utils, _signals
from . import SandboxFlags
from .._exceptions import SandboxError
from .._message import Message, MessageType
from .._platform import Platform
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from ._sandboxreapi import SandboxREAPI


# SandboxBuildBoxRun()
#
# BuildBox-based sandbox implementation.
#
class SandboxBuildBoxRun(SandboxREAPI):
    @classmethod
    def check_available(cls):
        try:
            path = utils.get_host_tool("buildbox-run")
        except utils.ProgramNotFoundError as Error:
            cls._dummy_reasons += ["buildbox-run not found"]
            raise SandboxError(" and ".join(cls._dummy_reasons), reason="unavailable-local-sandbox") from Error

        exit_code, output = utils._call([path, "--capabilities"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if exit_code == 0:
            # buildbox-run --capabilities prints one capability per line
            cls._capabilities = set(output.split("\n"))
        elif "Invalid option --capabilities" in output:
            # buildbox-run is too old to support extra capabilities
            cls._capabilities = set()
        else:
            # buildbox-run is not functional
            cls._dummy_reasons += ["buildbox-run: {}".format(output)]
            raise SandboxError(" and ".join(cls._dummy_reasons), reason="unavailable-local-sandbox")

        osfamily_prefix = "platform:OSFamily="
        cls._osfamilies = {cap[len(osfamily_prefix) :] for cap in cls._capabilities if cap.startswith(osfamily_prefix)}
        if not cls._osfamilies:
            # buildbox-run is too old to list supported OS families,
            # limit support to native building on the host OS.
            cls._osfamilies.add(Platform.get_host_os())

        isa_prefix = "platform:ISA="
        cls._isas = {cap[len(isa_prefix) :] for cap in cls._capabilities if cap.startswith(isa_prefix)}
        if not cls._isas:
            # buildbox-run is too old to list supported ISAs,
            # limit support to native building on the host ISA.
            cls._isas.add(Platform.get_host_arch())

    @classmethod
    def check_sandbox_config(cls, platform, config):
        if config.build_os not in cls._osfamilies:
            raise SandboxError("OS '{}' is not supported by buildbox-run.".format(config.build_os))
        if config.build_arch not in cls._isas:
            raise SandboxError("ISA '{}' is not supported by buildbox-run.".format(config.build_arch))

        if config.build_uid is not None and "platform:unixUID" not in cls._capabilities:
            raise SandboxError("Configuring sandbox UID is not supported by buildbox-run.")
        if config.build_gid is not None and "platform:unixGID" not in cls._capabilities:
            raise SandboxError("Configuring sandbox GID is not supported by buildbox-run.")

    def _execute_action(self, action, flags):
        stdout, stderr = self._get_output()

        context = self._get_context()
        cascache = context.get_cascache()
        casd_process_manager = cascache.get_casd_process_manager()

        with utils._tempnamedfile() as action_file, utils._tempnamedfile() as result_file:
            action_file.write(action.SerializeToString())
            action_file.flush()

            buildbox_command = [
                utils.get_host_tool("buildbox-run"),
                "--use-localcas",
                "--remote={}".format(casd_process_manager._connection_string),
                "--action={}".format(action_file.name),
                "--action-result={}".format(result_file.name),
            ]

            # Do not redirect stdout/stderr
            if "no-logs-capture" in self._capabilities:
                buildbox_command.append("--no-logs-capture")

            marked_directories = self._get_marked_directories()
            mount_sources = self._get_mount_sources()
            for mark in marked_directories:
                mount_point = mark["directory"]
                mount_source = mount_sources.get(mount_point)
                if not mount_source:
                    # Handled by the input tree in the action
                    continue

                if "bind-mount" not in self._capabilities:
                    self._warn("buildbox-run does not support host-files")
                    break

                buildbox_command.append("--bind-mount={}:{}".format(mount_source, mount_point))

            # If we're interactive, we want to inherit our stdin,
            # otherwise redirect to /dev/null, ensuring process
            # disconnected from terminal.
            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin

                if "bind-mount" in self._capabilities:
                    # In interactive mode, we want a complete devpts inside
                    # the container, so there is a /dev/console and such.
                    buildbox_command.append("--bind-mount=/dev:/dev")
            else:
                stdin = subprocess.DEVNULL

            self._run_buildbox(
                buildbox_command, stdin, stdout, stderr, interactive=(flags & SandboxFlags.INTERACTIVE),
            )

            return remote_execution_pb2.ActionResult().FromString(result_file.read())

    def _run_buildbox(self, argv, stdin, stdout, stderr, *, interactive):
        def kill_proc():
            if process:
                # First attempt to gracefully terminate
                proc = psutil.Process(process.pid)
                proc.terminate()

                try:
                    proc.wait(15)
                except psutil.TimeoutExpired:
                    utils._kill_process_tree(process.pid)

        def suspend_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGSTOP)

        def resume_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGCONT)

        with ExitStack() as stack:

            # We want to launch buildbox-run in a new session in non-interactive
            # mode so that we handle the SIGTERM and SIGTSTP signals separately
            # from the nested process, but in interactive mode this causes
            # launched shells to lack job control as the signals don't reach
            # the shell process.
            #
            if interactive:
                new_session = False
            else:
                new_session = True
                stack.enter_context(_signals.suspendable(suspend_proc, resume_proc))
                stack.enter_context(_signals.terminator(kill_proc))

            process = subprocess.Popen(
                argv, close_fds=True, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=new_session,
            )

            # Wait for the child process to finish, ensuring that
            # a SIGINT has exactly the effect the user probably
            # expects (i.e. let the child process handle it).
            try:
                while True:
                    try:
                        returncode = process.wait()
                        # If the process exits due to a signal, we
                        # brutally murder it to avoid zombies
                        if returncode < 0:
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

            if returncode != 0:
                raise SandboxError("buildbox-run failed with returncode {}".format(returncode))

    def _supported_platform_properties(self):
        return {"OSFamily", "ISA", "unixUID", "unixGID", "network"}

    def _warn(self, msg):
        self._get_context().messenger.message(Message(MessageType.WARN, msg))
