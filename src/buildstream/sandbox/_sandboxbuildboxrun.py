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

import grpc
import psutil

from .. import utils, _signals
from . import _SandboxFlags
from .._exceptions import SandboxError, SandboxUnavailableError
from .._platform import Platform
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from ._reremote import RERemote
from ._sandboxreapi import SandboxREAPI


# SandboxBuildBoxRun()
#
# BuildBox-based sandbox implementation.
#
class SandboxBuildBoxRun(SandboxREAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        context = self._get_context()
        cascache = context.get_cascache()

        re_specs = context.remote_execution_specs
        if re_specs and re_specs.action_spec:
            self.re_remote = RERemote(context.remote_cache_spec, re_specs, cascache)
            try:
                self.re_remote.init()
                self.re_remote.check()
            except grpc.RpcError as e:
                urls = set()
                if re_specs.storage_spec:
                    urls.add(re_specs.storage_spec.url)
                urls.add(re_specs.action_spec.url)
                raise SandboxError("Failed to contact remote cache endpoint at {}: {}".format(sorted(urls), e)) from e
        else:
            self.re_remote = None

    @classmethod
    def __buildbox_run(cls):
        return utils._get_host_tool_internal("buildbox-run", search_subprojects_dir="buildbox")

    @classmethod
    def _setup(cls):
        try:
            path = cls.__buildbox_run()
        except utils.ProgramNotFoundError as e:
            raise SandboxUnavailableError("buildbox-run not found", reason="unavailable-local-sandbox") from e

        exit_code, output = utils._call([path, "--capabilities"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if exit_code == 0:
            # buildbox-run --capabilities prints one capability per line
            cls._capabilities = set(output.split("\n"))
        else:
            # buildbox-run is not functional
            raise SandboxError(
                "buildbox-run exited with code {}. Output: {}".format(exit_code, output),
                reason="buildbox-run-not-functional",
            )

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
            raise SandboxUnavailableError("OS '{}' is not supported by buildbox-run.".format(config.build_os))
        if config.build_arch not in cls._isas:
            raise SandboxUnavailableError("ISA '{}' is not supported by buildbox-run.".format(config.build_arch))

        if config.build_uid is not None and "platform:unixUID" not in cls._capabilities:
            raise SandboxUnavailableError("Configuring sandbox UID is not supported by buildbox-run.")
        if config.build_gid is not None and "platform:unixGID" not in cls._capabilities:
            raise SandboxUnavailableError("Configuring sandbox GID is not supported by buildbox-run.")

        if config.remote_apis_socket_path is not None and "platform:remoteApisSocketPath" not in cls._capabilities:
            raise SandboxUnavailableError("Configuring Remote APIs socket path is not supported by buildbox-run.")

    def _execute_action(self, action, flags):
        stdout, stderr = self._get_output()

        context = self._get_context()
        cascache = context.get_cascache()
        casd = cascache.get_casd()
        config = self._get_config()

        if config.remote_apis_socket_path and context.remote_cache_spec and not self.re_remote:
            raise SandboxError(
                "Using 'remote-apis-socket' with 'storage-service' requires 'action-cache-service' or 'execution-service' configured in the 'remote-execution' section."
            )

        with utils._tempnamedfile() as action_file, utils._tempnamedfile() as result_file:
            action_file.write(action.SerializeToString())
            action_file.flush()

            buildbox_command = [
                self.__buildbox_run(),
                "--remote={}".format(casd._connection_string),
                "--action={}".format(action_file.name),
                "--action-result={}".format(result_file.name),
            ]

            if self.re_remote:
                buildbox_command.append("--instance={}".format(self.re_remote.local_cas_instance_name))
            if config.remote_apis_socket_action_cache_enable_update:
                buildbox_command.append("--nested-ac-enable-update")

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

            action_result = remote_execution_pb2.ActionResult().FromString(result_file.read())

        if self.re_remote and context.remote_execution_specs.storage_spec and context.remote_cache_spec:
            # This ensures that the outputs are uploaded to the cache storage-service
            # in case different CAS remotes have been configured in the `cache` and `remote-execution` sections.
            self._fetch_action_result_outputs(self.re_remote, action_result)

        return action_result

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

            if interactive and stdin.isatty():
                # Make this process the foreground process again, otherwise the
                # next read() on stdin will trigger SIGTTIN and stop the process.
                # This is required because the sandboxed process does not have
                # permission to do this on its own (running in separate PID namespace).
                #
                # tcsetpgrp() will trigger SIGTTOU when called from a background
                # process, so ignore it temporarily.
                handler = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
                os.tcsetpgrp(0, os.getpid())
                signal.signal(signal.SIGTTOU, handler)

            if returncode != 0:
                raise SandboxError("buildbox-run failed with returncode {}".format(returncode))
