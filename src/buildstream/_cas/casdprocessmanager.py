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

import contextlib
import threading
import os
import re
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from subprocess import CalledProcessError

import psutil
import grpc

from .._protos.build.bazel.remote.asset.v1 import remote_asset_pb2_grpc
from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2_grpc
from .._protos.build.buildgrid import local_cas_pb2_grpc
from .._protos.google.bytestream import bytestream_pb2_grpc
from .._protos.google.longrunning import operations_pb2_grpc

from .. import _site
from .. import utils
from .._exceptions import CASCacheError

_CASD_MAX_LOGFILES = 10
_CASD_TIMEOUT = 300  # in seconds


#
# Minimum required version of buildbox-casd
#
_REQUIRED_CASD_MAJOR = 1
_REQUIRED_CASD_MINOR = 2
_REQUIRED_CASD_MICRO = 6


# CASDProcessManager
#
# This manages the subprocess that runs buildbox-casd.
#
# Args:
#     path (str): The root directory for the CAS repository
#     log_dir (str): The directory for the logs
#     log_level (LogLevel): Log level to give to buildbox-casd for logging
#     cache_quota (int): User configured cache quota
#     reserved (int): User configured reserved disk space
#     remote_cache_spec (RemoteSpec): Optional remote cache server
#     protect_session_blobs (bool): Disable expiry for blobs used in the current session
#     messenger (Messenger): The messenger to report warnings through the UI
#
class CASDProcessManager:
    def __init__(
        self,
        path,
        log_dir,
        log_level,
        cache_quota,
        remote_cache_spec,
        protect_session_blobs,
        messenger,
        *,
        reserved=None,
        low_watermark=None,
        local_jobs=None
    ):
        os.makedirs(path, exist_ok=True)

        self._log_dir = log_dir

        self._socket_path = self._make_socket_path(path)
        self._connection_string = "unix:" + self._socket_path

        # Early version check
        self._check_casd_version(messenger)

        casd_args = [self.__buildbox_casd()]
        casd_args.append("--bind=" + self._connection_string)
        casd_args.append("--log-level=" + log_level.value)

        if cache_quota is not None:
            casd_args.append("--quota-high={}".format(int(cache_quota)))

        if low_watermark is not None:
            casd_args.append("--quota-low={}%".format(int(low_watermark * 100)))

        if reserved is not None:
            casd_args.append("--reserved={}".format(int(reserved)))

        if protect_session_blobs:
            casd_args.append("--protect-session-blobs")

        if local_jobs is not None:
            try:
                buildbox_run = utils._get_host_tool_internal("buildbox-run", search_subprojects_dir="buildbox")
                casd_args.append("--buildbox-run={}".format(buildbox_run))
                casd_args.append("--jobs={}".format(local_jobs))
            except utils.ProgramNotFoundError:
                # Not fatal as buildbox-run is not needed for remote execution
                # and buildbox-casd local execution will never be used if
                # buildbox-run is not available.
                pass

        if remote_cache_spec:
            casd_args.append("--cas-remote={}".format(remote_cache_spec.url))
            if remote_cache_spec.instance_name:
                casd_args.append("--cas-instance={}".format(remote_cache_spec.instance_name))
            if remote_cache_spec.server_cert_file:
                casd_args.append("--cas-server-cert={}".format(remote_cache_spec.server_cert_file))
            if remote_cache_spec.client_key_file:
                casd_args.append("--cas-client-key={}".format(remote_cache_spec.client_key_file))
                casd_args.append("--cas-client-cert={}".format(remote_cache_spec.client_cert_file))
            if remote_cache_spec.access_token_file:
                casd_args.append("--cas-access-token={}".format(remote_cache_spec.access_token_file))
                if remote_cache_spec.access_token_reload_interval is not None:
                    casd_args.append(
                        "--cas-token-reload-interval={}".format(remote_cache_spec.access_token_reload_interval)
                    )
            if remote_cache_spec.keepalive_time is not None:
                casd_args.append("--cas-keepalive-time={}".format(remote_cache_spec.keepalive_time))
            if remote_cache_spec.retry_limit is not None:
                casd_args.append("--cas-retry-limit={}".format(remote_cache_spec.retry_limit))
            if remote_cache_spec.retry_delay is not None:
                casd_args.append("--cas-retry-delay={}".format(remote_cache_spec.retry_delay))
            if remote_cache_spec.request_timeout is not None:
                casd_args.append("--cas-request-timeout={}".format(remote_cache_spec.request_timeout))

        casd_args.append(path)

        self._start_time = time.time()
        self._logfile = self._rotate_and_get_next_logfile()

        # Create a new process group for buildbox-casd such that SIGINT won't reach it.
        if sys.version_info >= (3, 11):
            process_group_kwargs = {"process_group": 0}
        else:
            process_group_kwargs = {"preexec_fn": os.setpgrp}

        with open(self._logfile, "w", encoding="utf-8") as logfile_fp:
            # The frontend will take care of terminating buildbox-casd.
            self.process = subprocess.Popen(  # pylint: disable=consider-using-with
                casd_args,
                cwd=path,
                stdout=logfile_fp,
                stderr=subprocess.STDOUT,
                env=self.__buildbox_casd_env(),
                **process_group_kwargs
            )

        self._casd_channel = None
        self._bytestream = None
        self._casd_cas = None
        self._local_cas = None
        self._asset_fetch = None
        self._asset_push = None
        self._exec_service = None
        self._operations_service = None
        self._ac_service = None
        self._shutdown_requested = False

        self._lock = threading.Lock()

    def __buildbox_casd(self):
        return utils._get_host_tool_internal("buildbox-casd", search_subprojects_dir="buildbox")

    def __buildbox_casd_env(self):
        env = os.environ.copy()

        # buildbox-casd needs to have buildbox-fuse in its PATH at runtime,
        # otherwise it will fallback to the HardLinkStager backend.
        bundled_buildbox_dir = os.path.join(_site.subprojects, "buildbox")
        if os.path.exists(bundled_buildbox_dir):
            path = env.get("PATH", "").split(os.pathsep)
            path = [bundled_buildbox_dir] + path
            env["PATH"] = os.pathsep.join(path)
        return env

    # _check_casd_version()
    #
    # Check for minimal acceptable version of buildbox-casd.
    #
    # If the version is unacceptable, then an error is raised.
    #
    # If buildbox-casd was built without version information available (or has reported
    # version information with a string which we are unprepared to parse), then
    # a warning is produced to inform the user.
    #
    def _check_casd_version(self, messenger):
        #
        # We specify a trailing "path" argument because some versions of buildbox-casd
        # require specifying the storage path even for invoking the --version option.
        #
        casd_args = [self.__buildbox_casd()]
        casd_args.append("--version")
        casd_args.append("/")

        try:
            version_output = subprocess.check_output(casd_args)
        except CalledProcessError as e:
            raise CASCacheError("Error checking buildbox-casd version") from e

        version_output = version_output.decode("utf-8")
        version_match = re.match(r".*buildbox-casd (\d+).(\d+).(\d+).*", version_output)

        if version_match:
            version_major = int(version_match.group(1))
            version_minor = int(version_match.group(2))
            version_micro = int(version_match.group(3))

            acceptable_version = True
            if version_major < _REQUIRED_CASD_MAJOR:
                acceptable_version = False
            elif version_major == _REQUIRED_CASD_MAJOR:
                if version_minor < _REQUIRED_CASD_MINOR:
                    acceptable_version = False
                elif version_minor == _REQUIRED_CASD_MINOR:
                    if version_micro < _REQUIRED_CASD_MICRO:
                        acceptable_version = False

            if not acceptable_version:
                raise CASCacheError(
                    "BuildStream requires buildbox-casd >= {}.{}.{}".format(
                        _REQUIRED_CASD_MAJOR, _REQUIRED_CASD_MINOR, _REQUIRED_CASD_MICRO
                    ),
                    detail="Currently installed: {}".format(version_output),
                )
        elif messenger:
            messenger.warn(
                "Unable to determine buildbox-casd version", detail="buildbox-casd reported: {}".format(version_output)
            )

    # _make_socket_path()
    #
    # Create a path to the CASD socket, ensuring that we don't exceed
    # the socket path limit.
    #
    # Note that we *may* exceed the path limit if the python-chosen
    # tmpdir path is very long, though this should be /tmp.
    #
    # Args:
    #     path (str): The root directory for the CAS repository.
    #
    # Returns:
    #     (str) - The path to the CASD socket.
    #
    def _make_socket_path(self, path):
        self._socket_tempdir = tempfile.mkdtemp(prefix="buildstream")
        # mkdtemp will create this directory in the "most secure"
        # way. This translates to "u+rwx,go-rwx".
        #
        # This is a good thing, generally, since it prevents us
        # from leaking sensitive information to other users, but
        # it's a problem for the workflow for userchroot, since
        # the setuid casd binary will not share a uid with the
        # user creating the tempdir.
        #
        # Instead, we chmod the directory 755, and only place a
        # symlink to the CAS directory in here, which will allow the
        # CASD process RWX access to a directory without leaking build
        # information.
        os.chmod(
            self._socket_tempdir,
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
        )

        os.symlink(path, os.path.join(self._socket_tempdir, "cas"))
        # FIXME: There is a potential race condition here; if multiple
        # instances happen to create the same socket path, at least
        # one will try to talk to the same server as us.
        #
        # There's no real way to avoid this from our side; we'd need
        # buildbox-casd to tell us that it could not create a fresh
        # socket.
        #
        # We could probably make this even safer by including some
        # thread/process-specific information, but we're not really
        # supporting this use case anyway; it's mostly here fore
        # testing, and to help more gracefully handle the situation.
        #
        # Note: this uses the same random string generation principle
        # as cpython, so this is probably a safe file name.
        random_name = "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789_") for _ in range(8)])
        socket_name = "casserver-{}.sock".format(random_name)
        return os.path.join(self._socket_tempdir, "cas", socket_name)

    # _rotate_and_get_next_logfile()
    #
    # Get the logfile to use for casd
    #
    # This will ensure that we don't create too many casd log files by
    # rotating the logs and only keeping _CASD_MAX_LOGFILES logs around.
    #
    # Returns:
    #   (str): the path to the log file to use
    #
    def _rotate_and_get_next_logfile(self):
        try:
            existing_logs = sorted(os.listdir(self._log_dir))
        except FileNotFoundError:
            os.makedirs(self._log_dir)
        else:
            while len(existing_logs) >= _CASD_MAX_LOGFILES:
                logfile_to_delete = existing_logs.pop(0)
                os.remove(os.path.join(self._log_dir, logfile_to_delete))

        return os.path.join(self._log_dir, str(self._start_time) + ".log")

    # release_resources()
    #
    # Terminate the process and release related resources.
    #
    def release_resources(self, messenger=None):
        self._shutdown_requested = True
        with self._lock:
            if self._casd_channel:
                self._ac_service = None
                self._operations_service = None
                self._exec_service = None
                self._asset_push = None
                self._asset_fetch = None
                self._local_cas = None
                self._casd_cas = None
                self._bytestream = None
                self._casd_channel.close()
                self._casd_channel = None

        self._terminate(messenger)
        self.process = None
        shutil.rmtree(self._socket_tempdir)

    # _terminate()
    #
    # Terminate the buildbox casd process.
    #
    def _terminate(self, messenger=None):
        return_code = self.process.poll()

        if return_code is not None:
            # buildbox-casd is already dead

            if messenger:
                messenger.bug(
                    "Buildbox-casd died during the run. Exit code: {}, Logs: {}".format(return_code, self._logfile)
                )
            return

        self.process.terminate()

        try:
            # Don't print anything if buildbox-casd terminates quickly
            return_code = self.process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if messenger:
                cm = messenger.timed_activity("Terminating buildbox-casd")
            else:
                cm = contextlib.suppress()
            with cm:
                try:
                    return_code = self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=15)

                    if messenger:
                        messenger.warn("Buildbox-casd didn't exit in time and has been killed")
                    return

        if return_code != 0 and messenger:
            messenger.bug(
                "Buildbox-casd didn't exit cleanly. Exit code: {}, Logs: {}".format(return_code, self._logfile)
            )

    def _establish_connection(self):
        with self._lock:
            if self._casd_channel is not None:
                return

            while not os.path.exists(self._socket_path):
                # casd is not ready yet, try again after a 10ms delay,
                # but don't wait for more than specified timeout period
                if time.time() > self._start_time + _CASD_TIMEOUT:
                    raise CASCacheError("Timed out waiting for buildbox-casd to become ready")

                if self._shutdown_requested:
                    # Shutdown has been requested, we can exit
                    return

                # check that process is still alive
                try:
                    proc = psutil.Process(self.process.pid)
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        proc.wait()

                    if not proc.is_running():
                        if self._shutdown_requested:
                            return
                        raise CASCacheError("buildbox-casd process died before connection could be established")
                except psutil.NoSuchProcess:
                    if self._shutdown_requested:
                        return
                    raise CASCacheError("buildbox-casd process died before connection could be established")

                time.sleep(0.01)

            self._casd_channel = grpc.insecure_channel(self._connection_string)
            self._bytestream = bytestream_pb2_grpc.ByteStreamStub(self._casd_channel)
            self._casd_cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self._casd_channel)
            self._local_cas = local_cas_pb2_grpc.LocalContentAddressableStorageStub(self._casd_channel)
            self._asset_fetch = remote_asset_pb2_grpc.FetchStub(self._casd_channel)
            self._asset_push = remote_asset_pb2_grpc.PushStub(self._casd_channel)
            self._exec_service = remote_execution_pb2_grpc.ExecutionStub(self._casd_channel)
            self._operations_service = operations_pb2_grpc.OperationsStub(self._casd_channel)
            self._ac_service = remote_execution_pb2_grpc.ActionCacheStub(self._casd_channel)

    # get_cas():
    #
    # Return ContentAddressableStorage stub for buildbox-casd channel.
    #
    def get_cas(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._casd_cas

    # get_local_cas():
    #
    # Return LocalCAS stub for buildbox-casd channel.
    #
    def get_local_cas(self):
        if self._local_cas is None:
            self._establish_connection()
        return self._local_cas

    def get_bytestream(self):
        if self._bytestream is None:
            self._establish_connection()
        return self._bytestream

    # get_asset_fetch():
    #
    # Return Remote Asset Fetch stub for buildbox-casd channel.
    #
    def get_asset_fetch(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._asset_fetch

    # get_asset_push():
    #
    # Return Remote Asset Push stub for buildbox-casd channel.
    #
    def get_asset_push(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._asset_push

    # get_exec_service():
    #
    # Return Remote Execution stub for buildbox-casd channel.
    #
    def get_exec_service(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._exec_service

    # get_operations_service():
    #
    # Return Operations stub for buildbox-casd channel.
    #
    def get_operations_service(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._operations_service

    # get_ac_service():
    #
    # Return Action Cache stub for buildbox-casd channel.
    #
    def get_ac_service(self):
        if self._casd_channel is None:
            self._establish_connection()
        return self._ac_service
