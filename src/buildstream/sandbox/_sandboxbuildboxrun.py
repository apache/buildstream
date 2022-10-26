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
import signal
import subprocess
import sys
from contextlib import ExitStack

import psutil

from .. import utils, _signals
from . import _SandboxFlags
from .._exceptions import SandboxError
from .._platform import Platform
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from ._sandboxreapi import SandboxREAPI


# SandboxBuildBoxRun()
#
# BuildBox-based sandbox implementation.
#
class SandboxBuildBoxRun(SandboxREAPI):
    @classmethod
    def __buildbox_run(cls):
        return utils._get_host_tool_internal("buildbox-run", search_subprojects_dir="buildbox")

    @classmethod
    def check_available(cls):
        try:
            path = cls.__buildbox_run()
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
    def check_sandbox_config(cls, config):
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
                self.__buildbox_run(),
                "--remote={}".format(casd_process_manager._connection_string),
                "--action={}".format(action_file.name),
                "--action-result={}".format(result_file.name),
            ]

            # Do not redirect stdout/stderr
            if "no-logs-capture" in self._capabilities:
                buildbox_command.append("--no-logs-capture")

            marked_directories = self._get_marked_directories()
            mount_sources = self._get_mount_sources()
            for mount_point in marked_directories:
                mount_source = mount_sources.get(mount_point)
                if not mount_source:
                    # Handled by the input tree in the action
                    continue

                if "bind-mount" not in self._capabilities:
                    context = self._get_context()
                    context.messenger.warn("buildbox-run does not support host-files")
                    break

                buildbox_command.append("--bind-mount={}:{}".format(mount_source, mount_point))

            # If we're interactive, we want to inherit our stdin,
            # otherwise redirect to /dev/null, ensuring process
            # disconnected from terminal.
            if flags & _SandboxFlags.INTERACTIVE:
                stdin = sys.stdin

                if "bind-mount" in self._capabilities:
                    # In interactive mode, we want a complete devpts inside
                    # the container, so there is a /dev/console and such.
                    buildbox_command.append("--bind-mount=/dev:/dev")
            else:
                stdin = subprocess.DEVNULL

            self._run_buildbox(
                buildbox_command,
                stdin,
                stdout,
                stderr,
                interactive=(flags & _SandboxFlags.INTERACTIVE),
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

            process = subprocess.Popen(  # pylint: disable=consider-using-with
                argv,
                close_fds=True,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                start_new_session=new_session,
            )

            # Wait for the child process to finish, ensuring that
            # a SIGINT has exactly the effect the user probably
            # expects (i.e. let the child process handle it).
            try:
                while True:
                    try:
                        # Here, we don't use `process.wait()` directly without a timeout
                        # This is because, if we were to do that, and the process would never
                        # output anything, the control would never be given back to the python
                        # process, which might thus not be able to check for request to
                        # shutdown, or kill the process.
                        # We therefore loop with a timeout, to ensure the python process
                        # can act if it needs.
                        returncode = process.wait(timeout=1)
                        # If the process exits due to a signal, we
                        # brutally murder it to avoid zombies
                        if returncode < 0:
                            utils._kill_process_tree(process.pid)

                    except subprocess.TimeoutExpired:
                        continue

                    # Unlike in the bwrap case, here only the main
                    # process seems to receive the SIGINT. We pass
                    # on the signal to the child and then continue
                    # to wait.
                    except _signals.TerminateException:
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
