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

import sys
from contextlib import contextmanager

from .._exceptions import SandboxError
from .. import utils, _signals


# A class to wrap the `mount` and `umount` system commands
class Mounter(object):
    @classmethod
    def _mount(cls, dest, src=None, mount_type=None,
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
            raise SandboxError('`{}` failed with exit code {}'
                               .format(' '.join(argv), status))

        return dest

    @classmethod
    def _umount(cls, path, stdout=sys.stdout, stderr=sys.stderr):

        cmd = [utils.get_host_tool('umount'), '-R', path]
        status, _ = utils._call(
            cmd,
            terminate=True,
            stdout=stdout,
            stderr=stderr
        )

        if status != 0:
            raise SandboxError('`{}` failed with exit code {}'
                               .format(' '.join(cmd), status))

    # mount()
    #
    # A wrapper for the `mount` command. The device is unmounted when
    # the context is left.
    #
    # Args:
    #     dest (str) - The directory to mount to
    #     src (str) - The directory to mount
    #     stdout (file) - stdout
    #     stderr (file) - stderr
    #     mount_type (str|None) - The mount type (can be omitted or None)
    #     kwargs - Arguments to pass to the mount command, such as `ro=True`
    #
    # Yields:
    #     (str) The path to the destination
    #
    @classmethod
    @contextmanager
    def mount(cls, dest, src=None, stdout=sys.stdout,
              stderr=sys.stderr, mount_type=None, **kwargs):

        def kill_proc():
            cls._umount(dest, stdout, stderr)

        options = ','.join([key for key, val in kwargs.items() if val])

        path = cls._mount(dest, src, mount_type, stdout=stdout, stderr=stderr, options=options)
        try:
            with _signals.terminator(kill_proc):
                yield path
        finally:
            cls._umount(dest, stdout, stderr)

    # bind_mount()
    #
    # Mount a directory to a different location (a hardlink for all
    # intents and purposes). The directory is unmounted when the
    # context is left.
    #
    # Args:
    #     dest (str) - The directory to mount to
    #     src (str) - The directory to mount
    #     stdout (file) - stdout
    #     stderr (file) - stderr
    #     kwargs - Arguments to pass to the mount command, such as `ro=True`
    #
    # Yields:
    #     (str) The path to the destination
    #
    # While this is equivalent to `mount --rbind`, this option may not
    # exist and can be dangerous, requiring careful cleanupIt is
    # recommended to use this function over a manual mount invocation.
    #
    @classmethod
    @contextmanager
    def bind_mount(cls, dest, src=None, stdout=sys.stdout,
                   stderr=sys.stderr, **kwargs):

        def kill_proc():
            cls._umount(dest, stdout, stderr)

        kwargs['rbind'] = True
        options = ','.join([key for key, val in kwargs.items() if val])

        path = cls._mount(dest, src, None, stdout, stderr, options)

        try:
            with _signals.terminator(kill_proc):
                # Make the rbind a slave to avoid unmounting vital devices in
                # /proc
                cls._mount(dest, flags=['--make-rslave'])
                yield path
        finally:
            cls._umount(dest, stdout, stderr)
