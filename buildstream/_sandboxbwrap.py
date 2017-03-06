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

# A bubblewrap specific sandbox implementation
#
# This class contains a lot of cannibalised code from sandboxlib.bubblewrap
# see https://gitlab.com/baserock/sandboxlib

import os
import sys
import subprocess
import shutil
import re
import tempfile
import psutil
import signal

from . import utils

# Special value for 'stderr' and 'stdout' parameters to indicate 'capture
# and return the data'.
CAPTURE = subprocess.PIPE

# Special value for 'stderr' parameter to indicate 'forward to stdout'.
STDOUT = subprocess.STDOUT

MOUNT_TYPES = ['dev', 'host-dev', 'tmpfs', 'proc']


class SandboxBwrap():

    def __init__(self, **kwargs):

        self.fs_root = kwargs.get('fs_root', "/")
        # Path of the host that we wish to map as '/' in the sandbox

        self.cwd = kwargs.get('cwd', None)
        # Current working directory we want to start the sandbox in. If
        # None then cwd is inherited from the caller's CWD

        self.stdout = kwargs.get('stdout', CAPTURE)
        # Standard out stream is captured by default

        self.stderr = kwargs.get('stderr', CAPTURE)
        # Standard error stream is captured by default

        self.network_enable = False
        # Boolean flag for if network resources can be utilised

        self.namespace_uid = None
        # User id to use if we are changing the namespace
        self.namespace_gid = None
        # Group id to use if we are changing the namespace

        self.namespace_pid = True
        # Create new pid namespace

        self.namespace_ipc = True
        # Create new ipc namespace

        self.namespace_uts = True
        # Create new uts namespace

        self.namespace_cgroup = True
        # Create new cgroup namespace

        self.mounts = []
        # List of mounts, each in the format (src, dest, type, writeable)

        self.root_ro = True
        # Boolean flag for remounting the root filesystem as read-only after
        # additional mounts have been added.

        self.env = kwargs.get('env', {})
        # Environment variables to use for the sandbox. By default env is not shared

        self.debug = False
        # Debug parameter for printing out the bwrap command that is going to be ran

    def run(self, command):
        # Runs a command inside the sandbox environment
        #
        # Args:
        #     command (List[str]): The command to run in the sandboxed environment
        #
        # Raises:
        #     :class'`.ProgramNotfound` If bwrap(bubblewrap) binary can not be found
        #
        # Returns:
        #     exitcode, stdout, stderr
        #

        # We want command args as a list of strings
        if type(command) == str:
            command = [command]

        # Grab the full path of the bwrap binary
        bwrap_command = [utils.get_host_tool('bwrap')]

        # Create a new pid namespace, this also ensures that any subprocesses
        # are cleaned up when the bwrap process exits.
        bwrap_command += ['--unshare-pid']

        # Add in the root filesystem stuff first
        # rootfs is mounted as RW initially so that further mounts can be
        # placed on top. If a RO root is required, after all other mounts
        # are complete, root is remounted as RO
        bwrap_command += ["--bind", self.fs_root, "/"]

        bwrap_command += self.process_network_config()

        if self.cwd is not None:
            bwrap_command.extend(['--chdir', self.cwd])

        # do pre checks on mounts
        self.create_mount_points()

        # Handles the ro and rw mounts
        bwrap_command += self.process_mounts()
        bwrap_command += self.remount_root_ro()

        # Set UID and GUI
        bwrap_command += self.user_namespace()

        argv = bwrap_command + command
        if self.debug:
            print(" ".join(argv))
        exitcode, out, err = self.run_command(argv, self.stdout, self.stderr, env=self.env)

        return exitcode, out, err

    def set_cwd(self, cwd):
        # Set the CWD for the sandbox
        #
        # Args:
        #     cwd (string): Path to desired working directory when the sandbox is entered
        #

        # TODO check valid path of `cwd`
        self.cwd = cwd

    def set_user_namespace(self, uid, gid):
        # Set the uid and gid to use in the new user namespace
        #
        # Args:
        #     uid : uid to use, e.g. 0 for root
        #     gid : god to use, e.g. 0 for root
        #

        self.namespace_uid = uid
        self.namespace_gid = gid

    def set_env(self, env):
        # Sets the env variables for the sandbox
        #
        # Args:
        #     env (dict): Dictionary of the enviroment variables to use. An empty dict will
        #         clear all envs
        # Raises :class'`TypeError` if env is not a dict.
        #

        # ENV needs to be a dict
        if type(env) is dict:
            self.env = env
        else:
            raise TypeError("env is expected to be a dict, not a {}".format(type(env)))

    def set_mounts(self, mnt_list=[], global_write=False, append=False, **kwargs):
        # Set mounts for the sandbox to use
        #
        # Args:
        #     mnt_list (list): List of dicts describing mounts. Dict is in the format {'src','dest','type','writable'}
        #         Only 'src' and 'dest' are required.
        #     global_write (boolean): Set all mounts given as writable (overrides setting in dict)
        #     append (boolean): If set, multiple calls to `setMounts` extends the list of mounts.
        #         Else they are overridden.
        #
        # The mount dict is in the format {'src','dest','type','writable'}.
        #     - src : Path of the mount on the HOST
        #     - dest : Path we wish to mount to on the TARGET
        #     - type : (optional) Some mounts are special such as dev, proc and tmp, and need to be tagged accordingly
        #     - writable : (optional) Boolean value to make mount writable instead of read-only
        #

        mounts = []
        # Process mounts one by one
        for mnt in mnt_list:
            host_dir = mnt.get('src', None)
            target_dir = mnt.get('dest', None)
            mnt_type = mnt.get('type', None)
            writable = global_write or mnt.get('writable', False)

            # Host dir should be an absolute path
            if host_dir is not None and not os.path.isabs(host_dir):
                host_dir = os.path.join(self.fs_root, host_dir)

            mounts.append((host_dir, target_dir, mnt_type, writable))

        if append:
            self.mounts.extend(mounts)
        else:
            self.mounts = mounts

    def set_network_enable(self, is_enabled=True):
        # Enable/disable networking inside of the sandbox. By default networking is
        # disabled so this needs to be called if you are going to make use of any
        # networked resources.
        #
        # Args:
        #     is_enabled (boolean):
        #

        self.network_enable = is_enabled

    def create_mount_points(self):
        # Creates any mount points that do not currently exist but have
        # been specified as a mount
        #

        for mnt in self.mounts:
            # (host_dir, target_dir, mnt_type, writable)
            target_dir = mnt[1]
            stripped = os.path.abspath(target_dir).lstrip('/')
            path = os.path.join(self.fs_root, stripped)

            if not os.path.exists(path):
                os.makedirs(path)

    def process_mounts(self):
        # Processes mounts that have already been set via the `set_mounts` method
        # to produce mount arguments for bwrap
        #
        # Returns:
        #       List[Str] command line arguments for bwrap
        #

        mount_args = []

        for mnt in self.mounts:
            src, dest, type, wr = mnt

            # Do special mounts first
            if type == "proc":
                mount_args.extend(['--proc', dest])

            # Note, tmpfs data can not be recovered between instances
            elif type == "tmpfs":
                mount_args.extend(['--tmpfs', dest])

            # Create a separate dev mount to the host
            elif type == "dev":
                mount_args.extend(['--dev-bind', src, dest])

            # Share a host dev mount
            elif type == "host-dev":
                mount_args.extend(['--dev', dest])

            # Normal bind mounts
            elif wr:
                mount_args.extend(['--bind', src, dest])

            # Else read-only mount
            else:
                mount_args.extend(['--ro-bind', src, dest])

        return mount_args

    def remount_root_ro(self):
        # Configures bwrap to remount root as read-only if `root_ro` is set
        #
        # Returns:
        #       List[Str] command line arguments for bwrap
        #

        if self.root_ro:
            return ["--remount-ro", "/"]
        else:
            return []

    def process_network_config(self):
        # Configures bwrap to restrict network access if `network_enable` is not set
        #
        # Returns:
        #       List[Str] command line arguments for bwrap
        #

        if not self.network_enable:
            return ['--unshare-net']
        else:
            return []

    def user_namespace(self):
        # Configures bwrap to run arbitrary userid and groupid depending on
        # `namespace_uid` and `namespace_gid`
        #
        # Returns:
        #       List[Str] command line arguments for bwrap
        #

        if self.namespace_uid is not None:
            return ['--unshare-user', '--uid', str(self.namespace_uid), '--gid', str(self.namespace_gid)]
        else:
            return []

    def run_command(self, argv, stdout, stderr, cwd=None, env=None):
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
                cwd=cwd,
                env=env,
                stdout=stdout,
                stderr=stderr,
                # We want a separate session, so that we are alone handling SIGTERM
                start_new_session=True
            )
            out, err = process.communicate()

        return process.returncode, out, err

    def minimal_dev(self, devlist):
        # Creates a minimal dev directory ready for mounting
        #
        # A tmp directory is created and populated with symlinks to device nodes
        # that are required for the sandbox. These are later dev-mounted
        #
        # Args:
        #       devlist (List[String]):
        #
        # Returns:
        #       Dict that follows internal mount convention. Local directory is tmp
        #

        dev = tempfile.mkdtemp("minidev")

        for d in devlist:
            os.symlink(d, dev)

        return {'src': dev, 'dest': '/dev', 'type': 'dev'}
