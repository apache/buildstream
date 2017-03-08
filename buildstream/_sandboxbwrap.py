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
import subprocess
import shutil
import re
import tempfile
import psutil
import signal

from . import utils
from . import Sandbox, SandboxFlags


# SandboxBwrap()
#
# Default bubblewrap based sandbox implementation.
#
class SandboxBwrap(Sandbox):

    def run(self, command, flags, cwd=None, env=None):

        # We want command args as a list of strings
        if type(command) == str:
            command = [command]

        stdout, stderr = self._get_output()
        directory = self.get_directory()
        if cwd is None:
            cwd = '/buildstream'

        # Ensure mount points exist
        for mount in ['proc', 'dev', 'buildstream']:
            os.makedirs(os.path.join(directory, mount), exist_ok=True)

        # Grab the full path of the bwrap binary
        bwrap_command = [utils.get_host_tool('bwrap')]

        # Create a new pid namespace, this also ensures that any subprocesses
        # are cleaned up when the bwrap process exits.
        bwrap_command += ['--unshare-pid']

        # Add in the root filesystem stuff first rootfs is mounted as RW initially so
        # that further mounts can be placed on top. If a RO root is required, after
        # all other mounts are complete, root is remounted as RO
        bwrap_command += ["--bind", directory, "/"]

        if not flags & SandboxFlags.NETWORK_ENABLED:
            bwrap_command += ['--unshare-net']

        if cwd is not None:
            bwrap_command += ['--chdir', cwd]

        # Setup the mounts we want to use
        bwrap_command += [
            # Give it a proc and tmpfs
            '--proc', '/proc',
            '--tmpfs', '/tmp',
            # XXX Entire host dev, instead use the devices list from the Project !
            '--dev', '/dev',
            # Read/Write /buildstream directory
            '--bind', os.path.join(directory, 'buildstream'), '/buildstream'
        ]

        if flags & SandboxFlags.ROOT_READ_ONLY:
            bwrap_command += ["--remount-ro", "/"]

        # Set UID and GUI
        bwrap_command += ['--unshare-user', '--uid', '0', '--gid', '0']

        # Add the command
        bwrap_command += command

        # Run it and return exit code.
        return self.run_bwrap(bwrap_command, stdout, stderr, env=env)

    def run_bwrap(self, argv, stdout, stderr, env):
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

        with utils._suspendable(suspend_bwrap, resume_bwrap), \
            utils._terminator(terminate_bwrap):

            process = subprocess.Popen(
                argv,
                # The default is to share file descriptors from the parent process
                # to the subprocess, which is rarely good for sandboxing.
                close_fds=True,
                env=env,
                stdout=stdout,
                stderr=stderr,
                # We want a separate session, so that we are alone handling SIGTERM
                start_new_session=True
            )
            process.communicate()
            exit_code = process.poll()

        return exit_code
