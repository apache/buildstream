import os
import pwd
import sys
import stat
import subprocess
from pathlib import Path
from contextlib import ExitStack, contextmanager

from .. import utils
from . import SandboxFlags
from ._mount import MountMap
from .._exceptions import SandboxError
from ._sandboxchroot import SandboxChroot
from .._message import Message, MessageType


# The sandbox directory needs to fulfill a few criteria:
#   - Its parents must be owned by root
#   - It and its children must be owned by the user defined in the
#     configuration file
#   - Neither it nor its parents must be more permissive than 755
#   - It cannot be in a directory mounted into the sandbox (duh)
#
# If we allow the user to specify this location (we probably should),
# those criteria would be nice to check for before sandbox execution.
# Although userchroot itself checks for some, the error messages are
# not particularly helpful.
#
SANDBOX_DIR = '/usr/local/sandboxes'


def assert_userchroot_configuration():
    configured = False
    user = pwd.getpwuid(os.getuid())[0]
    userchroot = utils.get_host_tool('userchroot')
    config = Path(userchroot).parents[1].joinpath('etc/userchroot.conf')

    if config.exists():
        with open(config, 'r') as configf:
            for line in configf:
                if line.rstrip() == '{}:{}'.format(user, SANDBOX_DIR):
                    configured = True
                    break

    if not configured:
        raise SandboxError("'userchroot' is not configured correctly. "
                           "Please add '{}:{}' to '{}'"
                           .format(user, SANDBOX_DIR, config))


class SandboxUserChroot(SandboxChroot):
    def run(self, command, flags, *, cwd=None, env=None):
        # Ensure sandbox default configuration
        if cwd is None:
            cwd = self._get_work_directory() or '/'

        if env is None:
            env = self._get_environment()

        if isinstance(command, str):
            command = [command]

        stdout, stderr = self._get_output()

        # Create the mount map, this will tell us where
        # each mount point needs to be mounted from and to
        self.mount_map = MountMap(self, True)

        # Make sure userchroot is configured correctly
        assert_userchroot_configuration()

        with ExitStack() as stack:
            # Create sysroot
            try:
                os.makedirs(SANDBOX_DIR, exist_ok=True)
                rootfs = stack.enter_context(utils._tempdir(dir=SANDBOX_DIR))
            except PermissionError as e:
                raise SandboxError('Could not create sysroot in {}: {}'
                                   .format(SANDBOX_DIR, e)) from e

            stack.enter_context(self.stage_sysroot(rootfs, flags, stdout, stderr))

            # Chroot!
            if flags & SandboxFlags.INTERACTIVE:
                stdin = sys.stdin
            else:
                stdin = stack.enter_context(open(os.devnull, 'r'))

            status = self.chroot(rootfs, command, stdin, stdout, stderr,
                                 cwd, env, flags)
        return status

    def chroot(self, rootfs, command, stdin, stdout, stderr, cwd, env,
               flags):
        # Create a script in the root directory of the sysroot to
        # execute the given commands.
        script = "\n".join(["#!/bin/sh"] + command)
        scriptpath = os.path.join(rootfs, 'buildstream-run.sh')

        with open(scriptpath, 'w') as scriptfile:
            scriptfile.write(script)
        perms = os.stat(scriptpath).st_mode
        os.chmod(scriptpath, perms & stat.S_IXUSR)

        # Execute the script with userchroot
        try:
            command = [utils.get_host_tool('userchroot'),
                       rootfs,
                       '--install-devices',
                       '/buildstream-run.sh']
            return self.popen(command,
                              env=env,
                              stdin=stdin,
                              stdout=stdout,
                              stderr=stderr,
                              cwd=os.path.join(rootfs, cwd.lstrip(os.sep)),
                              start_new_session=flags & SandboxFlags.INTERACTIVE)

        except subprocess.SubprocessError as e:
            raise SandboxError('Could not run command {}: {}'.format(command, e)) from e

    # mount_dirs()
    #
    # Since we aren't root we can't arbitrarily mount directories. Yet
    # we *require* our FUSE filesystem for at least some operations.
    #
    # FUSE can be mounted by users, therefore this mount function
    # attempts to safely mount our FUSE system on top of a copy of our
    # sandbox files.
    #
    # This *does* mean that this platform is significantly slower than
    # others, unfortunately...
    #
    @contextmanager
    def stage_sysroot(self, rootfs, flags, stdout, stderr):
        def mount(d):
            overrides = self._get_mount_sources()

            if d in overrides:
                src = overrides[d]
            else:
                src = self.mount_map.get_mount_source(d)

            dst = os.path.join(rootfs, d.lstrip(os.sep))

            self.info('Mounting {} to {}'.format(src, dst))

        with self.mount_map.mounted(rootfs):
            yield

            mount('/')

            for mark in self._get_marked_directories():
                mount(mark['directory'])

    def info(self, message):
        msg = Message('sandbox', MessageType.INFO, message)
        self._get_context()._message(msg)
