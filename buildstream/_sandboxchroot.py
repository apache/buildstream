#!/usr/bin/env python3
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
import shutil
import subprocess
from contextlib import contextmanager, ExitStack

from . import utils
from . import ElementError
from . import Sandbox, SandboxFlags


# A class to wrap the `mount` and `umount` commands
class Mount():
    def __init__(self, platform):
        self.platform = platform

    def _mount(self, dest, src=None, mount_type=None,
               stdout=sys.stdout, stderr=sys.stderr, options=None,
               flags=None):

        argv = [utils.get_host_tool('mount')]
        if mount_type:
            argv.extend(['-t', mount_type])
        if options:
            argv.extend(['-o', options])
        if flags:
            argv.extend(flags)

        if src is not None:
            argv += [src]
        argv += [dest]

        status, _ = utils._call(
            argv,
            terminate=True,
            stdout=stdout,
            stderr=stderr
        )

        if status != 0:
            raise ElementError('`{}` failed with exit code {}'
                               .format(' '.join(argv), status))

        return dest

    def _umount(self, path, stdout=sys.stdout, stderr=sys.stderr):

        cmd = [utils.get_host_tool('umount'), '-R', path]
        status, _ = utils._call(
            cmd,
            terminate=True,
            stdout=stdout,
            stderr=stderr
        )

        if status != 0:
            raise ElementError('`{}` failed with exit code {}'
                               .format(' '.join(cmd), status))

    # mount()
    #
    # A wrapper for the `mount` command. The device is unmounted when
    # the context is left.
    #
    # Args:
    #     src (str) - The directory to mount
    #     dest (str) - The directory to mount to
    #     mount_type (str|None) - The mount type (can be omitted or None)
    #     kwargs - Arguments to pass to the mount command, such as `ro=True`
    #
    # Yields:
    #     (str) The path to the destination
    #
    @contextmanager
    def mount(self, dest, src=None, mount_type=None,
              stdout=sys.stdout, stderr=sys.stderr, **kwargs):

        options = ','.join([key for key, val in kwargs.items() if val])

        yield self._mount(dest, src, mount_type, stdout=stdout, stderr=stderr, options=options)

        self._umount(dest, stdout, stderr)

    # bind_mount()
    #
    # Mount a directory to a different location (a hardlink for all
    # intents and purposes). The directory is unmounted when the
    # context is left.
    #
    # Args:
    #     src (str) - The directory to mount
    #     dest (str) - The directory to mount to
    #     kwargs - Arguments to pass to the mount command, such as `ro=True`
    #
    # Yields:
    #     (str) The path to the destination
    #
    # While this is equivalent to `mount --rbind`, this option may not
    # exist and can be dangerous, requiring careful cleanupIt is
    # recommended to use this function over a manual mount invocation.
    #
    @contextmanager
    def bind_mount(self, dest, src=None, stdout=sys.stdout, stderr=sys.stderr,
                   **kwargs):

        kwargs['rbind'] = True
        options = ','.join([key for key, val in kwargs.items() if val])

        path = self._mount(dest, src, None, stdout, stderr, options)

        # Make the rbind a slave to avoid unmounting vital devices in
        # /proc
        self._mount(dest, flags=['--make-rslave'])

        yield path

        self._umount(dest, stdout, stderr)


class SandboxChroot(Sandbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.platform = self._get_context()._platform
        self.mount = Mount(self.platform)

    def run(self, command, flags, cwd=None, env=None):

        # Default settings
        if cwd is None:
            cwd = self._get_work_directory()

        if cwd is None:
            cwd = '/'

        if env is None:
            env = self._get_environment()

        # Command must be a list
        if isinstance(command, str):
            command = [command]

        stdout, stderr = self._get_output()

        # Create a chroot directory and run the command inside it
        with ExitStack() as stack:
            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin
                status = self.run_in_interactive_sandbox(command, env, flags, cwd)
            else:
                stdin = stack.enter_context(open(os.devnull, 'r'))
                status = self.run_in_sandbox(command, stdin, stdout,
                                             stderr, cwd, env, flags)

        return status

    # run_in_sandbox()
    #
    # A helper function to pass the command to the chroot.
    #
    # Args:
    #    command (list): The command to execute in the chroot
    #    stdin (file): The stdin
    #    stdout (file): The stdout
    #    stderr (file): The stderr
    #    interactive (bool): Whether the sandbox should be run interactively
    #    cwd (str): The current working directory
    #    env (dict): The environment variables to use while executing the command
    #
    # Returns:
    #    (int): The exit code of the executed command
    #
    def run_in_sandbox(self, command, stdin, stdout, stderr, cwd, env, flags):
        # Hack to ensure a module required for exception handling is
        # not loaded in the chroot.
        #
        # Propagates from here:
        # https://github.com/CodethinkLabs/sandboxlib/blob/7e2a551189b5ffb7a0124db63964bdec69ead3e8/sandboxlib/chroot.py#L231
        _ = "Some Text".encode('unicode-escape')

        with ExitStack() as stack:
            stack.enter_context(self.create_devices(flags))
            stack.enter_context(self.mount_dirs(flags, stdout, stderr))

            try:
                code, _ = utils._call(
                    command,
                    terminate=True,
                    close_fds=True,
                    cwd=os.path.join(self.get_directory(), cwd.lstrip(os.sep)),
                    env=env,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    # If you try to put gtk dialogs here Tristan (either)
                    # will personally scald you
                    preexec_fn=lambda: (os.chroot(self.get_directory()), os.chdir(cwd)),
                    start_new_session=flags & SandboxFlags.INTERACTIVE
                )
            except subprocess.SubprocessError as e:
                # Exceptions in preexec_fn are simply reported as
                # 'Exception occurred in preexec_fn', turn these into
                # a more readable message.
                if '{}'.format(e) == 'Exception occurred in preexec_fn.':
                    raise ElementError('Could not chroot into {} or chdir into {}. '
                                       'Ensure you are root and that the relevant directory exists.'
                                       .format(self.get_directory(), cwd)) from e
                else:
                    raise ElementError('Could not run command {}: {}'.format(command, e)) from e

        if code != 0:
            raise ElementError("{} failed with exit code {}".format(command, code))

        return code

    # run_in_interactive_sandbox()
    #
    # Run an interactive command.
    #
    #
    # Args:
    #    command (list): The command to execute in the chroot
    #    stdin (file): The stdin
    #    stdout (file): The stdout
    #    stderr (file): The stderr
    #    interactive (bool): Whether the sandbox should be run interactively
    #    cwd (str): The current working directory
    #    env (dict): The environment variables to use while executing the command
    #
    # Returns:
    #    (int): The exit code of the executed command
    #
    # The method is similar to SandboxChroot.run_in_sandbox(), but
    # does not create a subprocess to allow the interactive session to
    # communicate with the frontend. It foregoes changing into `cwd`
    # since this is less important in an interactive session.
    #
    def run_in_interactive_sandbox(self, command, env, flags, cwd):

        with ExitStack() as stack:
            stack.enter_context(self.create_devices(flags))
            stack.enter_context(self.mount_dirs(flags, sys.stdout, sys.stderr))

            process = subprocess.Popen(
                command,
                cwd=os.path.join(self.get_directory(), cwd.lstrip(os.sep)),
                close_fds=True,
                preexec_fn=lambda: (os.chroot(self.get_directory()), os.chdir(cwd)),
                env=env
            )
            process.communicate()

        return process.poll()

    # create_devices()
    #
    # Create the nodes in /dev/ usually required for builds (null,
    # none, etc.)
    #
    # Args:
    #    flags (:class:`.SandboxFlags`): The sandbox flags
    #
    @contextmanager
    def create_devices(self, flags):

        devices = []
        # When we are interactive, we'd rather mount /dev due to the
        # sheer number of devices
        if not flags & SandboxFlags.INTERACTIVE:
            os.makedirs('/dev/', exist_ok=True)

            for device in Sandbox.DEVICES:
                location = os.path.join(self.get_directory(), device.lstrip(os.sep))
                os.makedirs(os.path.dirname(location), exist_ok=True)
                try:
                    # If the image already contains a device, remove
                    # it, since the device numbers may be different on
                    # different systems.
                    os.remove(location)

                    devices.append(self.mknod(device, location))
                except OSError as err:
                    if err.errno == 1:
                        raise ElementError("Permission denied while creating device node: {}.".format(err) +
                                           "BuildStream reqiures root permissions for these setttings.")

        yield

        for device in devices:
            os.remove(device)

    # mount()
    #
    # Mount paths required for the command.
    #
    # Args:
    #    flags (:class:`.SandboxFlags`): The sandbox flags
    #
    @contextmanager
    def mount_dirs(self, flags, stdout, stderr):

        # FIXME: This should probably keep track of potentially
        #        already existing files a la _sandboxwrap.py:239

        # To successfully mount the sysroot RO, we need to:
        #   - Mount / RO first since solaris can't remount a bind mount
        #     - Create missing directories and mount points
        #     - Move marked directories to a scratch directory to keep their RW state
        #     - Mount / RO
        #   - Mount marked directories RW
        #   - Mount system directories (/dev, /proc/, /tmp, ...)
        #
        #   - execute command
        #
        #   - Unmount system and marked directories
        #   - Unmount /

        # Create missing system directories
        if flags & SandboxFlags.INTERACTIVE:
            # We mount /dev in interactive sandboxes to give the
            # user a working console
            dev_src, dev_point = self.get_mount_location('/dev/', '/dev/')

        proc_src, proc_point = self.get_mount_location('/proc/', '/proc/')
        tmp_src, tmp_point = self.get_mount_location('/tmp', '/tmp')

        marked_directories = self._get_marked_directories()
        marked_locations = []

        for mark in marked_directories:
            host_location = os.path.join(self.get_directory(),
                                         mark['directory'].lstrip(os.sep))
            scratch_location = os.path.join(self._get_scratch_directory(),
                                            mark['directory'].lstrip(os.sep))

            # On the first invocation, move the marked directories to
            # the scratch directory to allow mounting them read-write

            # Create the host location if it does not exist yet
            os.makedirs(host_location, exist_ok=True)

            # Move marked directories before mounting / RO
            shutil.move(host_location, scratch_location)

            # Record the mount locations
            marked_locations.append(self.get_mount_location(scratch_location, mark['directory']))

        with ExitStack() as stack:
            # / mount
            root_mount = self.mount.bind_mount(self.get_directory(), self.get_directory(),
                                               stdout, stderr,
                                               ro=flags & SandboxFlags.ROOT_READ_ONLY)
            # Since / needs to be unmounted after and before
            # everything else has been unmounted, manually enter/exit
            # the context.
            root_mount.__enter__()

            # System mounts
            if flags & SandboxFlags.INTERACTIVE:
                stack.enter_context(self.mount.bind_mount(dev_point, dev_src, stdout, stderr))

            stack.enter_context(self.mount.mount(proc_point, proc_src, 'proc', stdout, stderr, ro=True))
            stack.enter_context(self.mount.bind_mount(tmp_point, tmp_src, stdout, stderr))

            # Mark mounts
            for src, point in marked_locations:
                stack.enter_context(self.mount.bind_mount(point, src, stdout, stderr))

            yield

        root_mount.__exit__(None, None, None)

        # Move back mark mounts
        for src, point in marked_locations:
            shutil.rmtree(point)
            shutil.move(src, point)

    # get_mount_location()
    #
    # Return a tuple that indicates the locations to mount a host
    # directory to and from to mount it to the corresponding path in
    # the chroot.
    #
    # Args:
    #     host_dir (str): The path to the host dir to mount.
    #     chroot_dir (str): The dir in the chroot to mount it to.
    #
    # Returns:
    #     (str, str) - (source, point)
    #
    def get_mount_location(self, host_dir, chroot_dir):
        point = os.path.join(self.get_directory(), chroot_dir.lstrip(os.sep))

        os.makedirs(host_dir, exist_ok=True)
        os.makedirs(point, exist_ok=True)

        return (host_dir, point)

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
            raise ElementError('Could not create device {}, ensure that you have root permissions: {}')

        except OSError as e:
            raise ElementError('Could not create device {}: {}'
                               .format(target, e)) from e

        return target
