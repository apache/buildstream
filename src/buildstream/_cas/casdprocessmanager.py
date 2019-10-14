#
#  Copyright (C) 2018 Codethink Limited
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
#

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
import tempfile
import time

import grpc

from .._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from .._protos.build.buildgrid import local_cas_pb2_grpc

from .. import _signals, utils
from .._exceptions import CASCacheError
from .._message import Message, MessageType

_CASD_MAX_LOGFILES = 10


# CASDProcessManager
#
# This manages the subprocess that runs buildbox-casd.
#
# Args:
#     path (str): The root directory for the CAS repository
#     log_dir (str): The directory for the logs
#     log_level (LogLevel): Log level to give to buildbox-casd for logging
#     cache_quota (int): User configured cache quota
#     protect_session_blobs (bool): Disable expiry for blobs used in the current session
#
class CASDProcessManager:

    def __init__(self, path, log_dir, log_level, cache_quota, protect_session_blobs):
        self._log_dir = log_dir

        self._casd_connection = None

        # Place socket in global/user temporary directory to avoid hitting
        # the socket path length limit.
        self._socket_tempdir = tempfile.mkdtemp(prefix='buildstream')
        self.socket_path = os.path.join(self._socket_tempdir, 'casd.sock')
        self.connection_string = "unix:" + self.socket_path

        casd_args = [utils.get_host_tool('buildbox-casd')]
        casd_args.append('--bind=' + self.connection_string)
        casd_args.append('--log-level=' + log_level.value)

        if cache_quota is not None:
            casd_args.append('--quota-high={}'.format(int(cache_quota)))
            casd_args.append('--quota-low={}'.format(int(cache_quota / 2)))

            if protect_session_blobs:
                casd_args.append('--protect-session-blobs')

        casd_args.append(path)

        self.start_time = time.time()
        self._logfile = self._rotate_and_get_next_logfile()

        with open(self._logfile, "w") as logfile_fp:
            # Block SIGINT on buildbox-casd, we don't need to stop it
            # The frontend will take care of it if needed
            with _signals.blocked([signal.SIGINT], ignore=False):
                self._process = subprocess.Popen(
                    casd_args, cwd=path, stdout=logfile_fp, stderr=subprocess.STDOUT)

        self._failure_callback = None
        self._watcher = None

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

        return os.path.join(self._log_dir, str(self.start_time) + ".log")

    # release_resources()
    #
    # Terminate the process and release related resources.
    #
    def release_resources(self, messenger=None):
        self._terminate(messenger)
        self._process = None
        shutil.rmtree(self._socket_tempdir)

    # _terminate()
    #
    # Terminate the buildbox casd process.
    #
    def _terminate(self, messenger=None):
        assert self._watcher is None
        assert self._failure_callback is None

        return_code = self._process.poll()

        if return_code is not None:
            # buildbox-casd is already dead

            if messenger:
                messenger.message(
                    Message(
                        MessageType.BUG,
                        "Buildbox-casd died during the run. Exit code: {}, Logs: {}".format(
                            return_code, self._logfile
                        ),
                    )
                )
            return

        self._process.terminate()

        try:
            # Don't print anything if buildbox-casd terminates quickly
            return_code = self._process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            if messenger:
                cm = messenger.timed_activity("Terminating buildbox-casd")
            else:
                cm = contextlib.suppress()
            with cm:
                try:
                    return_code = self._process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=15)

                    if messenger:
                        messenger.message(
                            Message(MessageType.WARN, "Buildbox-casd didn't exit in time and has been killed")
                        )
                    return

        if return_code != 0 and messenger:
            messenger.message(
                Message(
                    MessageType.BUG,
                    "Buildbox-casd didn't exit cleanly. Exit code: {}, Logs: {}".format(
                        return_code, self._logfile
                    ),
                )
            )

    # set_failure_callback()
    #
    # Call this function if the CASD process stops unexpectedly.
    #
    # Note that we guarantee that the lifetime of any 'watcher' used is bound
    # to the lifetime of the callback - we won't hang on to the asyncio loop
    # longer than necessary.
    #
    # We won't be able to use watchers on win32, so we'll need to support
    # another approach.
    #
    # Args:
    #   func (callable): a callable that takes no parameters
    #
    def set_failure_callback(self, func):
        assert func is not None
        assert self._watcher is None
        assert self._failure_callback is None
        self._failure_callback = func
        self._watcher = asyncio.get_child_watcher()
        self._watcher.add_child_handler(self._process.pid, self._on_casd_failure)

    # clear_failure_callback()
    #
    # No longer call this callable if the CASD process stops unexpectedly
    #
    # Args:
    #   func (callable): The callable that was provided to add_failure_callback().
    #                    Supplying this again allows us to do error checking.
    #
    def clear_failure_callback(self, func):
        assert func is not None
        assert self._failure_callback == func
        self._watcher.remove_child_handler(self._process.pid)
        self._failure_callback = None
        self._watcher = None

    # _on_casd_failure()
    #
    # Handler for casd process terminating unexpectedly
    #
    # Args:
    #   pid (int): the process id under which buildbox-casd was running
    #   returncode (int): the return code with which buildbox-casd exited
    #
    def _on_casd_failure(self, pid, returncode):
        assert self._failure_callback is not None
        self._process.returncode = returncode
        self._failure_callback()

    # get_connection():
    #
    # Return ContentAddressableStorage stub for buildbox-casd channel.
    #
    def get_connection(self):
        if not self._casd_connection:
            self._casd_connection = CASDConnection(
                self.socket_path, self.connection_string, self.start_time)
        return self._casd_connection

    # has_open_grpc_channels():
    #
    # Return whether there are gRPC channel instances. This is used to safeguard
    # against fork() with open gRPC channels.
    #
    def has_open_grpc_channels(self):
        return bool(self._casd_connection)

    # close_grpc_channels():
    #
    # Close the casd channel if it exists
    #
    def close_grpc_channels(self):
        if self._casd_connection:
            self._casd_connection.close()


class CASDConnection:
    def __init__(self, socket_path, connection_string, start_time):
        while not os.path.exists(socket_path):
            # casd is not ready yet, try again after a 10ms delay,
            # but don't wait for more than 15s
            if time.time() > start_time + 15:
                raise CASCacheError("Timed out waiting for buildbox-casd to become ready")

            time.sleep(0.01)

        self._casd_channel = grpc.insecure_channel(connection_string)
        self._casd_cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self._casd_channel)
        self._local_cas = local_cas_pb2_grpc.LocalContentAddressableStorageStub(self._casd_channel)

        # Call GetCapabilities() to establish connection to casd
        capabilities = remote_execution_pb2_grpc.CapabilitiesStub(self._casd_channel)
        capabilities.GetCapabilities(remote_execution_pb2.GetCapabilitiesRequest())

    # get_cas():
    #
    # Return ContentAddressableStorage stub for buildbox-casd channel.
    #
    def get_cas(self):
        assert self._casd_channel is not None
        return self._casd_cas

    # get_local_cas():
    #
    # Return LocalCAS stub for buildbox-casd channel.
    #
    def get_local_cas(self):
        assert self._casd_channel is not None
        return self._local_cas

    # close():
    #
    # Close the casd channel.
    #
    def close(self):
        assert self._casd_channel is not None
        self._local_cas = None
        self._casd_cas = None
        self._casd_channel.close()
        self._casd_channel = None
