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
import errno
import time
from contextlib import ExitStack

from . import utils, _signals
from . import Sandbox, SandboxFlags
from ._fuse import SafeHardlinks


# SandboxBwrap()
#
# Default bubblewrap based sandbox implementation.
#
class SandboxBwrap(Sandbox):

    def run(self, command, flags, cwd=None, env=None):

        # Fallback to the sandbox default settings for
        # the cwd and env.
        #
        if cwd is None:
            cwd = self._get_work_directory()

        if env is None:
            env = self._get_environment()

        # We want command args as a list of strings
        if type(command) == str:
            command = [command]

        stdout, stderr = self._get_output()
        root_directory = self.get_directory()
        scratch_directory = self._get_scratch_directory()
        scratch_tempdir = os.path.join(scratch_directory, 'temp')

        # If we're read-only, then just mount the real root, otherwise
        # we're going to redirect that with a safe hardlinking fuse
        # layer.
        if flags & SandboxFlags.ROOT_READ_ONLY:
            root_mount_source = root_directory
        else:
            root_mount_source = os.path.join(scratch_directory, 'root')
            os.makedirs(root_mount_source, exist_ok=True)
            os.makedirs(scratch_tempdir, exist_ok=True)

        if cwd is None:
            cwd = '/'

        # Grab the full path of the bwrap binary
        bwrap_command = [utils.get_host_tool('bwrap')]

        # Create a new pid namespace, this also ensures that any subprocesses
        # are cleaned up when the bwrap process exits.
        bwrap_command += ['--unshare-pid']

        # Add in the root filesystem stuff first rootfs is mounted as RW initially so
        # that further mounts can be placed on top. If a RO root is required, after
        # all other mounts are complete, root is remounted as RO
        bwrap_command += ["--bind", root_mount_source, "/"]

        if not flags & SandboxFlags.NETWORK_ENABLED:
            bwrap_command += ['--unshare-net']

        if cwd is not None:
            bwrap_command += ['--chdir', cwd]

        # Give it a proc and tmpfs
        bwrap_command += [
            '--proc', '/proc',
            '--tmpfs', '/tmp'
        ]

        # Bind some minimal set of host devices
        devices = ['/dev/full', '/dev/null', '/dev/urandom', '/dev/random', '/dev/zero']
        for device in devices:
            bwrap_command += ['--dev-bind', device, device]

        # Add bind mounts to marked directories, ensuring they are readwrite
        #
        # In the future the marked directories may gain some flags which will
        # indicate their nature and how we need to mount them, for now they
        # are just straight forward read-write mounts.
        marked_directories = self._get_marked_directories()
        for directory in marked_directories:
            host_directory = os.path.join(root_directory, directory.lstrip(os.sep))
            bwrap_command += ['--bind', host_directory, directory]

        if flags & SandboxFlags.ROOT_READ_ONLY:
            bwrap_command += ["--remount-ro", "/"]

        # Set UID and GUI
        bwrap_command += ['--unshare-user', '--uid', '0', '--gid', '0']

        # Add the command
        bwrap_command += command

        # bwrap might create some directories while being suid
        # and may give them to root gid, if it does, we'll want
        # to clean them up after, so record what we already had
        # there just in case so that we can safely cleanup the debris.
        #
        existing_basedirs = {
            directory: os.path.exists(os.path.join(root_directory, directory))
            for directory in ['tmp', 'dev', 'proc']
        }

        with ExitStack() as stack:

            # Add the safe hardlink mount to the stack context if we need it
            if not flags & SandboxFlags.ROOT_READ_ONLY:
                mount = SafeHardlinks(root_directory, scratch_tempdir)
                stack.enter_context(mount.mounted(root_mount_source))

            exit_code = self.run_bwrap(bwrap_command, stdout, stderr, env=env)

        # Cleanup things which bwrap might have left behind
        for device in devices:
            device_path = os.path.join(root_mount_source, device.lstrip('/'))

            # This will remove the device in a loop, allowing some
            # retries in case the device file leaked by bubblewrap is still busy
            self.try_remove_device(device_path)

        # Remove /tmp, this is a bwrap owned thing we want to be sure
        # never ends up in an artifact
        for basedir in ['tmp', 'dev', 'proc']:

            # Skip removal of directories which already existed before
            # launching bwrap
            if not existing_basedirs[basedir]:
                continue

            base_directory = os.path.join(root_mount_source, basedir)
            try:
                os.rmdir(base_directory)
            except FileNotFoundError:
                # ignore this, if bwrap cleaned up properly then it's not a problem.
                #
                # If the directory was not empty on the other hand, then this is clearly
                # a bug, bwrap mounted a tempfs here and when it exits, that better be empty.
                pass

        return exit_code

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

        with _signals.suspendable(suspend_bwrap, resume_bwrap), \
            _signals.terminator(terminate_bwrap):

            try:
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
            except KeyboardInterrupt:
                # Dont care about keyboard interrupts, they will happen
                # if a child shell is invoked without available job control
                terminate_bwrap()
                exit_code = -1
                pass

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
