#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
import os
import sys
import time
import errno
import signal
import subprocess
import shutil
from contextlib import ExitStack

import grpc
import psutil

from .. import utils, _signals
from ._mount import MountMap
from . import Sandbox, SandboxFlags
from ..storage._filebaseddirectory import FileBasedDirectory
from ..storage._casbaseddirectory import CasBasedDirectory
from google.devtools.remoteexecution.v1test import remote_execution_pb2, remote_execution_pb2_grpc
from google.longrunning import operations_pb2, operations_pb2_grpc
from .._artifactcache.cascache import CASCache

# SandboxRemote()
#
# This isn't really a sandbox, it's a stub which sends all the source to a remote server and retrieves the results from it.
#
class SandboxRemote(Sandbox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_ns_available = kwargs['user_ns_available']
        self.die_with_parent_available = kwargs['die_with_parent_available']

    def __run_remote_command(self, cascache, command, input_root_digest):
        remote_command = remote_execution_pb2.Command(arguments=command)
        # (Ignore environment for now)
        # Serialise this into the cascache...
        command_digest = cascache.add_object(buffer=remote_command.SerializeToString())

        command_ref = 'worker-command/{}'.format(command_digest.hash)
        cascache.set_ref(command_ref, command_digest)

        # TODO: push_key_only isn't really meant to work with refs to Command
        # objects - it will try and find the dependencies of it; there are none,
        # but it expects to find a directory. We may need to pass a flag to tell
        # it not to look for any.
        command_push_successful = cascache.push_key_only(command_ref, self._get_project())
        if command_push_successful or cascache.verify_key_pushed(command_ref, self._get_project()):
            # Next, try to create a communication channel
            port = 50051
            channel = grpc.insecure_channel('dekatron.office.codethink.co.uk:{}'.format(port))
            stub = remote_execution_pb2_grpc.ExecutionStub(channel)
            ops_stub = operations_pb2_grpc.OperationsStub(channel)

            # Having done that, create and send the action.

            action = remote_execution_pb2.Action(command_digest = command_digest,
                                                 input_root_digest = input_root_digest,
                                                 output_files = [],
                                                 output_directories = [self.__output_directory],
                                                 platform = None,
                                                 timeout = None,
                                                 do_not_cache = True)

            request = remote_execution_pb2.ExecuteRequest(instance_name = 'default',
                                                          action = action,
                                                          skip_cache_lookup = True)

            response = stub.Execute(request)
            job_name = response.name
        else:
            # Source push failed
            return None
        while True:
            # TODO: Timeout
            request = operations_pb2.GetOperationRequest(name=job_name)
            response = ops_stub.GetOperation(request)
            time.sleep(1)
            if response.done:
                break
        return response

    def run(self, command, flags, *, cwd=None, env=None):
        stdout, stderr = self._get_output()
        sys.stderr.write("Attempting run with remote sandbox...\n")
        # Upload sources
        upload_vdir = self.get_virtual_directory()
        if isinstance(upload_vdir, FileBasedDirectory):
            upload_vdir = self.get_temporary_vdir()
            upload_vdir.import_files(self.get_virtual_directory().get_underlying_directory())

        # Now, push that key (without necessarily needing a ref) to the remote.
        cascache = CASCache(self._get_context())
        cascache.setup_remotes(use_config=True) # Should do that once per sandbox really (or less often)
        ref = 'worker-source/{}'.format(upload_vdir.ref.hash)
        upload_vdir._save(ref)
        source_push_successful = cascache.push_key_only(ref, self._get_project())
        # Fallback to the sandbox default settings for
        # the cwd and environment.

        if env is None:
            env = self._get_environment()

        # We want command args as a list of strings
        if isinstance(command, str):
            command = [command]

        # Now transmit the command to execute
        if source_push_successful or cascache.verify_key_pushed(ref, self._get_project()):
            response = self.__run_remote_command(cascache, command, upload_vdir.ref)

            if response is None or response.HasField("error"):
                # Build failed, so return a failure code
                return 1
            else:
                # If we succeeded, expect response.response to be a... what?
                sys.stderr.write("Received non-error response from server: {}".format(type(response.response)))
        else:
            sys.stderr.write("Failed to push source to remote artifact cache.\n")
            return 1
        # TODO: Pull the results
        return 0

    def run_bwrap(self, argv, stdin, stdout, stderr, env, interactive):
        # Wrapper around subprocess.Popen() with common settings.
        #
        # This function blocks until the subprocess has terminated.
        #
        # It then returns a tuple of (exit code, stdout output, stderr output).
        # If stdout was not equal to subprocess.PIPE, stdout will be None. Same for
        # stderr.

        # Fetch the process actually launched inside the bwrap sandbox, or the
        # intermediat control bwrap processes.
        #
        # NOTE:
        #   The main bwrap process itself is setuid root and as such we cannot
        #   send it any signals. Since we launch bwrap with --unshare-pid, it's
        #   direct child is another bwrap process which retains ownership of the
        #   pid namespace. This is the right process to kill when terminating.
        #
        #   The grandchild is the binary which we asked bwrap to launch on our
        #   behalf, whatever this binary is, it is the right process to use
        #   for suspending and resuming. In the case that this is a shell, the
        #   shell will be group leader and all build scripts will stop/resume
        #   with that shell.
        #
        def get_user_proc(bwrap_pid, grand_child=False):
            bwrap_proc = psutil.Process(bwrap_pid)
            bwrap_children = bwrap_proc.children()
            if bwrap_children:
                if grand_child:
                    bwrap_grand_children = bwrap_children[0].children()
                    if bwrap_grand_children:
                        return bwrap_grand_children[0]
                else:
                    return bwrap_children[0]
            return None

        def terminate_bwrap():
            if process:
                user_proc = get_user_proc(process.pid)
                if user_proc:
                    user_proc.kill()

        def suspend_bwrap():
            if process:
                user_proc = get_user_proc(process.pid, grand_child=True)
                if user_proc:
                    group_id = os.getpgid(user_proc.pid)
                    os.killpg(group_id, signal.SIGSTOP)

        def resume_bwrap():
            if process:
                user_proc = get_user_proc(process.pid, grand_child=True)
                if user_proc:
                    group_id = os.getpgid(user_proc.pid)
                    os.killpg(group_id, signal.SIGCONT)

        with ExitStack() as stack:

            # We want to launch bwrap in a new session in non-interactive
            # mode so that we handle the SIGTERM and SIGTSTP signals separately
            # from the nested bwrap process, but in interactive mode this
            # causes launched shells to lack job control (we dont really
            # know why that is).
            #
            if interactive:
                new_session = False
            else:
                new_session = True
                stack.enter_context(_signals.suspendable(suspend_bwrap, resume_bwrap))
                stack.enter_context(_signals.terminator(terminate_bwrap))

            process = subprocess.Popen(
                argv,
                # The default is to share file descriptors from the parent process
                # to the subprocess, which is rarely good for sandboxing.
                close_fds=True,
                env=env,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                start_new_session=new_session
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
                            user_proc = get_user_proc(process.pid)
                            if user_proc:
                                utils._kill_process_tree(user_proc.pid)

                    # If we receive a KeyboardInterrupt we continue
                    # waiting for the process since we are in the same
                    # process group and it should also have received
                    # the SIGINT.
                    except KeyboardInterrupt:
                        continue

                    break
            # If we can't find the process, it has already died of its
            # own accord, and therefore we don't need to check or kill
            # anything.
            except psutil.NoSuchProcess:
                pass

            # Return the exit code - see the documentation for
            # os.WEXITSTATUS to see why this is required.
            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
            else:
                exit_code = -1

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

        return exit_code

    def try_remove_device(self, device_path):

        # Put some upper limit on the tries here
        max_tries = 1000
        tries = 0

        while True:
            try:
                os.unlink(device_path)
            except OSError as e:
                if e.errno == errno.EBUSY:
                    # This happens on some machines, seems there is a race sometimes
                    # after bubblewrap returns and the device files it bind-mounted did
                    # not finish unmounting.
                    #
                    if tries < max_tries:
                        tries += 1
                        time.sleep(1 / 100)
                        continue
                    else:
                        # We've reached the upper limit of tries, bail out now
                        # because something must have went wrong
                        #
                        raise
                elif e.errno == errno.ENOENT:
                    # Bubblewrap cleaned it up for us, no problem if we cant remove it
                    break
                else:
                    # Something unexpected, reraise this error
                    raise
            else:
                # Successfully removed the symlink
                break
