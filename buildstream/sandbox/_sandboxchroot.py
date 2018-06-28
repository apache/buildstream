#
#  Copyright (C) 2017 Codethink Limited
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
#        Tristan Maat <tristan.maat@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import sys
import stat
import signal
import subprocess
from contextlib import contextmanager, ExitStack
import psutil

from .._exceptions import SandboxError
from .. import utils
from .. import _signals
from ._mounter import Mounter
from ._mount import MountMap
from . import Sandbox, SandboxFlags


class SandboxChroot(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        uid = self._get_config().build_uid
        gid = self._get_config().build_gid
        if uid != 0 or gid != 0:
            raise SandboxError("Chroot sandboxes cannot specify a non-root uid/gid "
                               "({},{} were supplied via config)".format(uid, gid))

        self.mount_map = None

    def run(self, command, flags, *, cwd=None, env=None):

        # Default settings
        if cwd is None:
            cwd = self._get_work_directory()

        if cwd is None:
            cwd = '/'

        if env is None:
            env = self._get_environment()

        if not self._has_command(command[0], env):
            raise SandboxError("Staged artifacts do not provide command "
                               "'{}'".format(command[0]),
                               reason='missing-command')

        # Command must be a list
        if isinstance(command, str):
            command = [command]

        stdout, stderr = self._get_output()

        # Create the mount map, this will tell us where
        # each mount point needs to be mounted from and to
        self.mount_map = MountMap(self, flags & SandboxFlags.ROOT_READ_ONLY)
        root_mount_source = self.mount_map.get_mount_source('/')

        # Create a sysroot and run the command inside it
        with ExitStack() as stack:
            os.makedirs('/var/run/buildstream', exist_ok=True)

            # FIXME: While we do not currently do anything to prevent
            # network access, we also don't copy /etc/resolv.conf to
            # the new rootfs.
            #
            # This effectively disables network access, since DNs will
            # never resolve, so anything a normal process wants to do
            # will fail. Malicious processes could gain rights to
            # anything anyway.
            #
            # Nonetheless a better solution could perhaps be found.

            rootfs = stack.enter_context(utils._tempdir(dir='/var/run/buildstream'))
            stack.enter_context(self.create_devices(self.get_directory(), flags))
            stack.enter_context(self.mount_dirs(rootfs, flags, stdout, stderr))

            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin
            else:
                stdin = stack.enter_context(open(os.devnull, 'r'))

            # Ensure the cwd exists
            if cwd is not None:
                workdir = os.path.join(root_mount_source, cwd.lstrip(os.sep))
                os.makedirs(workdir, exist_ok=True)

            status = self.chroot(rootfs, command, stdin, stdout,
                                 stderr, cwd, env, flags)

        return status

    # chroot()
    #
    # A helper function to chroot into the rootfs.
    #
    # Args:
    #    rootfs (str): The path of the sysroot to chroot into
    #    command (list): The command to execute in the chroot env
    #    stdin (file): The stdin
    #    stdout (file): The stdout
    #    stderr (file): The stderr
    #    cwd (str): The current working directory
    #    env (dict): The environment variables to use while executing the command
    #    flags (:class:`SandboxFlags`): The flags to enable on the sandbox
    #
    # Returns:
    #    (int): The exit code of the executed command
    #
    def chroot(self, rootfs, command, stdin, stdout, stderr, cwd, env, flags):
        def kill_proc():
            if process:
                # First attempt to gracefully terminate
                proc = psutil.Process(process.pid)
                proc.terminate()

                try:
                    proc.wait(20)
                except psutil.TimeoutExpired:
                    utils._kill_process_tree(process.pid)

        def suspend_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGSTOP)

        def resume_proc():
            group_id = os.getpgid(process.pid)
            os.killpg(group_id, signal.SIGCONT)

        try:
            with _signals.suspendable(suspend_proc, resume_proc), _signals.terminator(kill_proc):
                process = subprocess.Popen(
                    command,
                    close_fds=True,
                    cwd=os.path.join(rootfs, cwd.lstrip(os.sep)),
                    env=env,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    # If you try to put gtk dialogs here Tristan (either)
                    # will personally scald you
                    preexec_fn=lambda: (os.chroot(rootfs), os.chdir(cwd)),
                    start_new_session=flags & SandboxFlags.INTERACTIVE
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

                # Return the exit code - see the documentation for
                # os.WEXITSTATUS to see why this is required.
                if os.WIFEXITED(status):
                    code = os.WEXITSTATUS(status)
                else:
                    code = -1

        except subprocess.SubprocessError as e:
            # Exceptions in preexec_fn are simply reported as
            # 'Exception occurred in preexec_fn', turn these into
            # a more readable message.
            if '{}'.format(e) == 'Exception occurred in preexec_fn.':
                raise SandboxError('Could not chroot into {} or chdir into {}. '
                                   'Ensure you are root and that the relevant directory exists.'
                                   .format(rootfs, cwd)) from e
            else:
                raise SandboxError('Could not run command {}: {}'.format(command, e)) from e

        return code

    # create_devices()
    #
    # Create the nodes in /dev/ usually required for builds (null,
    # none, etc.)
    #
    # Args:
    #    rootfs (str): The path of the sysroot to prepare
    #    flags (:class:`.SandboxFlags`): The sandbox flags
    #
    @contextmanager
    def create_devices(self, rootfs, flags):

        devices = []
        # When we are interactive, we'd rather mount /dev due to the
        # sheer number of devices
        if not flags & SandboxFlags.INTERACTIVE:

            for device in Sandbox.DEVICES:
                location = os.path.join(rootfs, device.lstrip(os.sep))
                os.makedirs(os.path.dirname(location), exist_ok=True)
                try:
                    if os.path.exists(location):
                        os.remove(location)

                    devices.append(self.mknod(device, location))
                except OSError as err:
                    if err.errno == 1:
                        raise SandboxError("Permission denied while creating device node: {}.".format(err) +
                                           "BuildStream reqiures root permissions for these setttings.")
                    else:
                        raise

        yield

        for device in devices:
            os.remove(device)

    # mount_dirs()
    #
    # Mount paths required for the command.
    #
    # Args:
    #    rootfs (str): The path of the sysroot to prepare
    #    flags (:class:`.SandboxFlags`): The sandbox flags
    #    stdout (file): The stdout
    #    stderr (file): The stderr
    #
    @contextmanager
    def mount_dirs(self, rootfs, flags, stdout, stderr):

        # FIXME: This should probably keep track of potentially
        #        already existing files a la _sandboxwrap.py:239

        @contextmanager
        def mount_point(point, **kwargs):
            mount_source_overrides = self._get_mount_sources()
            if point in mount_source_overrides:
                mount_source = mount_source_overrides[point]
            else:
                mount_source = self.mount_map.get_mount_source(point)
            mount_point = os.path.join(rootfs, point.lstrip(os.sep))

            with Mounter.bind_mount(mount_point, src=mount_source, stdout=stdout, stderr=stderr, **kwargs):
                yield

        @contextmanager
        def mount_src(src, **kwargs):
            mount_point = os.path.join(rootfs, src.lstrip(os.sep))
            os.makedirs(mount_point, exist_ok=True)

            with Mounter.bind_mount(mount_point, src=src, stdout=stdout, stderr=stderr, **kwargs):
                yield

        with ExitStack() as stack:
            stack.enter_context(self.mount_map.mounted(self))

            stack.enter_context(mount_point('/'))

            if flags & SandboxFlags.INTERACTIVE:
                stack.enter_context(mount_src('/dev'))

            stack.enter_context(mount_src('/tmp'))
            stack.enter_context(mount_src('/proc'))

            for mark in self._get_marked_directories():
                stack.enter_context(mount_point(mark['directory']))

            # Remount root RO if necessary
            if flags & flags & SandboxFlags.ROOT_READ_ONLY:
                root_mount = Mounter.mount(rootfs, stdout=stdout, stderr=stderr, remount=True, ro=True, bind=True)
                # Since the exit stack has already registered a mount
                # for this path, we do not need to register another
                # umount call.
                root_mount.__enter__()

            yield

    # mknod()
    #
    # Create a device node equivalent to the given source node
    #
    # Args:
    #    source (str): Path of the device to mimic (e.g. '/dev/null')
    #    target (str): Location to create the new device in
    #
    # Returns:
    #    target (str): The location of the created node
    #
    def mknod(self, source, target):
        try:
            dev = os.stat(source)
            major = os.major(dev.st_rdev)
            minor = os.minor(dev.st_rdev)

            target_dev = os.makedev(major, minor)

            os.mknod(target, mode=stat.S_IFCHR | dev.st_mode, device=target_dev)

        except PermissionError as e:
            raise SandboxError('Could not create device {}, ensure that you have root permissions: {}')

        except OSError as e:
            raise SandboxError('Could not create device {}: {}'
                               .format(target, e)) from e

        return target
