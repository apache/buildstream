#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
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
#        William Salmon <will.salmon@codethink.co.uk>

import collections
import json
import os
import sys
import time
import errno
import signal
import subprocess
import shutil
from contextlib import ExitStack, suppress
from tempfile import TemporaryFile

import psutil

from .._exceptions import SandboxError
from .. import utils, _signals
from . import Sandbox, SandboxFlags, SandboxCommandError
from .. import _site


# SandboxBwrap()
#
# Default bubblewrap based sandbox implementation.
#
class SandboxBwrap(Sandbox):
    _have_good_bwrap = None

    # Minimal set of devices for the sandbox
    DEVICES = [
        '/dev/full',
        '/dev/null',
        '/dev/urandom',
        '/dev/random',
        '/dev/zero'
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linux32 = kwargs['linux32']

    @classmethod
    def check_available(cls):
        cls._have_fuse = os.path.exists("/dev/fuse")
        if not cls._have_fuse:
            cls._dummy_reasons += ['Fuse is unavailable']

        try:
            utils.get_host_tool('bwrap')
        except utils.ProgramNotFoundError as Error:
            cls._bwrap_exists = False
            cls._have_good_bwrap = False
            cls._die_with_parent_available = False
            cls._json_status_available = False
            cls._dummy_reasons += ['Bubblewrap not found']
            raise SandboxError(" and ".join(cls._dummy_reasons),
                               reason="unavailable-local-sandbox") from Error

        bwrap_version = _site.get_bwrap_version()

        cls._bwrap_exists = True
        cls._have_good_bwrap = (0, 1, 2) <= bwrap_version
        cls._die_with_parent_available = (0, 1, 8) <= bwrap_version
        cls._json_status_available = (0, 3, 2) <= bwrap_version
        if not cls._have_good_bwrap:
            cls._dummy_reasons += ['Bubblewrap is too old']
            raise SandboxError(" and ".join(cls._dummy_reasons))

        cls._uid = os.geteuid()
        cls._gid = os.getegid()

        cls.user_ns_available = cls._check_user_ns_available()

    @staticmethod
    def _check_user_ns_available():
        # Here, lets check if bwrap is able to create user namespaces,
        # issue a warning if it's not available, and save the state
        # locally so that we can inform the sandbox to not try it
        # later on.
        bwrap = utils.get_host_tool('bwrap')
        try:
            whoami = utils.get_host_tool('whoami')
            output = subprocess.check_output([
                bwrap,
                '--ro-bind', '/', '/',
                '--unshare-user',
                '--uid', '0', '--gid', '0',
                whoami,
            ], universal_newlines=True).strip()
        except subprocess.CalledProcessError:
            output = ''
        except utils.ProgramNotFoundError:
            output = ''

        return output == 'root'

    @classmethod
    def check_sandbox_config(cls, local_platform, config):
        if cls.user_ns_available:
            # User namespace support allows arbitrary build UID/GID settings.
            pass
        elif (config.build_uid != local_platform._uid or config.build_gid != local_platform._gid):
            # Without user namespace support, the UID/GID in the sandbox
            # will match the host UID/GID.
            return False

        host_os = local_platform.get_host_os()
        host_arch = local_platform.get_host_arch()
        if config.build_os != host_os:
            raise SandboxError("Configured and host OS don't match.")
        if config.build_arch != host_arch and not local_platform.can_crossbuild(config):
            raise SandboxError("Configured architecture and host architecture don't match.")

        return True

    def _run(self, command, flags, *, cwd, env):
        stdout, stderr = self._get_output()

        # Allowable access to underlying storage as we're part of the sandbox
        root_directory = self.get_virtual_directory()._get_underlying_directory()

        if not self._has_command(command[0], env):
            raise SandboxCommandError("Staged artifacts do not provide command "
                                      "'{}'".format(command[0]),
                                      reason='missing-command')

        # NOTE: MountMap transitively imports `_fuse/fuse.py` which raises an
        # EnvironmentError when fuse is not found. Since this module is
        # expected to be imported even in absence of fuse, MountMap is imported
        # here, and not at the top of the module.
        from ._mount import MountMap

        # Create the mount map, this will tell us where
        # each mount point needs to be mounted from and to
        mount_map = MountMap(self, flags & SandboxFlags.ROOT_READ_ONLY)
        root_mount_source = mount_map.get_mount_source('/')

        # start command with linux32 if needed
        if self.linux32:
            bwrap_command = [utils.get_host_tool('linux32')]
        else:
            bwrap_command = []

        # Grab the full path of the bwrap binary
        bwrap_command += [utils.get_host_tool('bwrap')]

        for k, v in env.items():
            bwrap_command += ['--setenv', k, v]
        for k in os.environ.keys() - env.keys():
            bwrap_command += ['--unsetenv', k]

        # Create a new pid namespace, this also ensures that any subprocesses
        # are cleaned up when the bwrap process exits.
        bwrap_command += ['--unshare-pid']

        # Ensure subprocesses are cleaned up when the bwrap parent dies.
        if self._die_with_parent_available:
            bwrap_command += ['--die-with-parent']

        # Add in the root filesystem stuff first.
        #
        # The rootfs is mounted as RW initially so that further mounts can be
        # placed on top. If a RO root is required, after all other mounts are
        # complete, root is remounted as RO
        bwrap_command += ["--bind", root_mount_source, "/"]

        if not flags & SandboxFlags.NETWORK_ENABLED:
            bwrap_command += ['--unshare-net']
            bwrap_command += ['--unshare-uts', '--hostname', 'buildstream']
            bwrap_command += ['--unshare-ipc']

        # Give it a proc and tmpfs
        bwrap_command += [
            '--proc', '/proc',
            '--tmpfs', '/tmp'
        ]

        # In interactive mode, we want a complete devpts inside
        # the container, so there is a /dev/console and such. In
        # the regular non-interactive sandbox, we want to hand pick
        # a minimal set of devices to expose to the sandbox.
        #
        if flags & SandboxFlags.INTERACTIVE:
            bwrap_command += ['--dev', '/dev']
        else:
            for device in self.DEVICES:
                bwrap_command += ['--dev-bind', device, device]

        # Add bind mounts to any marked directories
        marked_directories = self._get_marked_directories()
        mount_source_overrides = self._get_mount_sources()
        for mark in marked_directories:
            mount_point = mark['directory']
            if mount_point in mount_source_overrides:  # pylint: disable=consider-using-get
                mount_source = mount_source_overrides[mount_point]
            else:
                mount_source = mount_map.get_mount_source(mount_point)

            # Use --dev-bind for all mounts, this is simply a bind mount which does
            # not restrictive about devices.
            #
            # While it's important for users to be able to mount devices
            # into the sandbox for `bst shell` testing purposes, it is
            # harmless to do in a build environment where the directories
            # we mount just never contain device files.
            #
            bwrap_command += ['--dev-bind', mount_source, mount_point]

        if flags & SandboxFlags.ROOT_READ_ONLY:
            bwrap_command += ["--remount-ro", "/"]

        if cwd is not None:
            bwrap_command += ['--dir', cwd]
            bwrap_command += ['--chdir', cwd]

        # Set UID and GUI
        if self.user_ns_available:
            bwrap_command += ['--unshare-user']
            if not flags & SandboxFlags.INHERIT_UID:
                uid = self._get_config().build_uid
                gid = self._get_config().build_gid
                bwrap_command += ['--uid', str(uid), '--gid', str(gid)]

        with ExitStack() as stack:
            pass_fds = ()
            # Improve error reporting with json-status if available
            if self._json_status_available:
                json_status_file = stack.enter_context(TemporaryFile())
                pass_fds = (json_status_file.fileno(),)
                bwrap_command += ['--json-status-fd', str(json_status_file.fileno())]

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

            # Use the MountMap context manager to ensure that any redirected
            # mounts through fuse layers are in context and ready for bwrap
            # to mount them from.
            #
            stack.enter_context(mount_map.mounted(self))

            # If we're interactive, we want to inherit our stdin,
            # otherwise redirect to /dev/null, ensuring process
            # disconnected from terminal.
            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin
            else:
                stdin = stack.enter_context(open(os.devnull, "r"))

            # Run bubblewrap !
            exit_code = self.run_bwrap(bwrap_command, stdin, stdout, stderr,
                                       (flags & SandboxFlags.INTERACTIVE), pass_fds)

            # Cleanup things which bwrap might have left behind, while
            # everything is still mounted because bwrap can be creating
            # the devices on the fuse mount, so we should remove it there.
            if not flags & SandboxFlags.INTERACTIVE:
                for device in self.DEVICES:
                    device_path = os.path.join(root_mount_source, device.lstrip('/'))

                    # This will remove the device in a loop, allowing some
                    # retries in case the device file leaked by bubblewrap is still busy
                    self.try_remove_device(device_path)

            # Remove /tmp, this is a bwrap owned thing we want to be sure
            # never ends up in an artifact
            for basedir in ['tmp', 'dev', 'proc']:

                # Skip removal of directories which already existed before
                # launching bwrap
                if existing_basedirs[basedir]:
                    continue

                base_directory = os.path.join(root_mount_source, basedir)

                if flags & SandboxFlags.INTERACTIVE:
                    # Be more lenient in interactive mode here.
                    #
                    # In interactive mode; it's possible that the project shell
                    # configuration has mounted some things below the base
                    # directories, such as /dev/dri, and in this case it's less
                    # important to consider cleanup, as we wont be collecting
                    # this build result and creating an artifact.
                    #
                    # Note: Ideally; we should instead fix upstream bubblewrap to
                    #       cleanup any debris it creates at startup time, and do
                    #       the same ourselves for any directories we explicitly create.
                    #
                    shutil.rmtree(base_directory, ignore_errors=True)
                else:
                    try:
                        os.rmdir(base_directory)
                    except FileNotFoundError:
                        # ignore this, if bwrap cleaned up properly then it's not a problem.
                        #
                        # If the directory was not empty on the other hand, then this is clearly
                        # a bug, bwrap mounted a tempfs here and when it exits, that better be empty.
                        pass

            if self._json_status_available:
                json_status_file.seek(0, 0)
                child_exit_code = None
                # The JSON status file's output is a JSON object per line
                # with the keys present identifying the type of message.
                # The only message relevant to us now is the exit-code of the subprocess.
                for line in json_status_file:
                    with suppress(json.decoder.JSONDecodeError):
                        o = json.loads(line.decode())
                        if isinstance(o, collections.abc.Mapping) and 'exit-code' in o:
                            child_exit_code = o['exit-code']
                            break
                if child_exit_code is None:
                    raise SandboxError("`bwrap' terminated during sandbox setup with exitcode {}".format(exit_code),
                                       reason="bwrap-sandbox-fail")
                exit_code = child_exit_code

        self._vdir._mark_changed()
        return exit_code

    def run_bwrap(self, argv, stdin, stdout, stderr, interactive, pass_fds):
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
                pass_fds=pass_fds,
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
