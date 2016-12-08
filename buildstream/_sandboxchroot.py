# Copyright (C) 2015-2016  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.


# Execute command in a sandbox, using os.chroot().
#
# This backend should work on any POSIX-compliant operating system. It has been
# tested on Linux and Mac OS X. The calling process must be able to use the
# chroot() syscall, which is likely to require 'root' priviliges.
#
# If any 'extra_mounts' are specified, there must be a working 'mount' binary in
# the host system.
#
# The code would be simpler if we just used the 'chroot' program, but it's not
# always practical to do that. First, it may not be installed. Second, we can't
# set the working directory of the program inside the chroot, unless we assume
# that the sandbox contains a shell and we do some hack like running
# `/bin/sh -c "cd foo && command"`. It's better to call the kernel directly.

import contextlib
import multiprocessing
import os
import subprocess
import warnings
import traceback
import sys


# Special value for 'stderr' and 'stdout' parameters to indicate 'capture
# and return the data'.
CAPTURE = subprocess.PIPE

# Special value for 'stderr' parameter to indicate 'forward to stdout'.
STDOUT = subprocess.STDOUT


class SandboxChroot:

    def __init__(self, **kwargs):
        self.stdout = None
        self.stderr = None
        self.fs_root = "/"
        self.cwd = "/"
        self.env = {}
        self._mounts = []

    def set_cwd(self, cwd):
        # Set the CWD for the sandbox
        #
        # Args:
        #       cwd (string): Path to desired working directory when the sandbox
        #                     is entered
        #

        self.cwd = cwd

    def set_env(self, env):
        # Sets the env variables for the sandbox
        #
        # Args:
        #       env (dict): Dictionary of the enviroment variables to use. An empty
        #                   dict will clear all envs
        #
        # Raises:
        #       :class'`TypeError` if env is not a dict.
        #

        if type(env) is dict:
            self.env = env
        else:
            raise TypeError("env is expected to be a dict, not a {}".format(type(env)))

    def set_mounts(self, mnt_list=[], append=False, **kwargs):
        # Set mounts for the sandbox to use
        #
        # Args:
        #       mnt_list (list): List of dicts describing mounts. Dict is in the
        #           format {'src','dest','type','writable'}. Only 'src' and 'dest'
        #           are required.
        #       append (boolean): If set, multiple calls to `setMounts` extends the
        #           list of mounts. Else they are overridden.
        #
        # The mount dict is in the format {'src','dest','type','writable'}.
        #    - src : Path of the mount on the HOST
        #    - dest : Path we wish to mount to on the TARGET
        #    - type :
        #    - writable : Not used in this implementation. All chroot mounts are wr
        #

        mounts = []
        # Process mounts one by one
        for mnt in mnt_list:
            host_dir = mnt.get('src', None)
            target_dir = mnt.get('dest', None)
            mnt_type = mnt.get('type', None)
            writable = None

            # Host dir should be an absolute path
            if host_dir is not None and not os.path.isabs(host_dir):
                host_dir = os.path.join(self.fs_root, host_dir)

            mounts.append((host_dir, target_dir, mnt_type, writable))

        if append:
            self._mounts.extend(mounts)
        else:
            self._mounts = mounts

    def mount(self, source, path, mount_type, mount_options):
        # We depend on the host system's 'mount' program here, which is a
        # little sad. It's possible to call the libc's mount() function
        # directly from Python using the 'ctypes' library, and perhaps we
        # should do that instead.  The 'mount' requires that a source is
        # given even for the special filesystems (e.g. proc, tmpfs), so we
        # use the mount type as the source if the latter is not explicitly
        # given.
        #

        def is_none(value):
            return value in (None, 'none', '')

        argv = ['mount']
        if not is_none(mount_type):
            argv.extend(('-t', mount_type))
        if not is_none(mount_options):
            argv.extend(('-o', mount_options))

        # If this is left empty, mount looks in fstab which will fail
        if not is_none(source):
            argv.append(source)
        else:
            argv.append("none")
        argv.append(path)

        exit, out, err = _run_command(
            argv, stdout=self.stdout, stderr=self.stderr)

        if exit != 0:
            raise RuntimeError(
                "%s failed: %s" % (
                    argv, err.decode('utf-8')))

    def unmount(self, path):
        argv = ['umount', path]
        exit, out, err = _run_command(
            argv, stdout=self.stdout, stderr=self.stderr)

        if exit != 0:
            warnings.warn("%s failed: %s" % (
                argv, err.decode('utf-8')))

    @contextlib.contextmanager
    def mount_all(self, mount_info_list):
        mounted = []

        try:
            for source, mount_point, mount_type, mount_options in mount_info_list:
                # Strip the preceeding '/' from mount_point, because it'll break
                # os.path.join().
                mount_point_no_slash = os.path.relpath(mount_point, start='/')

                path = os.path.join(self.fs_root, mount_point_no_slash)
                if not os.path.exists(path):
                    os.makedirs(path)

                self.mount(source, path, mount_type, mount_options)
                if not mount_options or 'remount' not in mount_options:
                    mounted.append(path)

            yield
        finally:
            for mountpoint in mounted:
                self.unmount(mountpoint)

    def validate_extra_mounts(self, extra_mounts):
        # Validate and fill in default values for 'extra_mounts' setting.
        #

        if extra_mounts is None:
            return []

        new_extra_mounts = []

        for mount_entry in extra_mounts:
            if mount_entry[1] is None:
                raise AssertionError(
                    "Mount point empty in mount entry %s" % str(mount_entry))

            if len(mount_entry) == 3:
                full_mount_entry = list(mount_entry) + ['']
            elif len(mount_entry) == 4:
                full_mount_entry = list(mount_entry)
            else:
                raise AssertionError(
                    "Invalid mount entry in 'extra_mounts': %s" % str(mount_entry))

            # Convert all the entries to strings to prevent type errors later
            # on. None is special cased to the empty string, as str(None) is
            # "None". It's valid for some parameters to be '' in some cases.
            processed_mount_entry = []
            for item in full_mount_entry:
                if item is None:
                    processed_mount_entry.append('')
                else:
                    processed_mount_entry.append(str(item))

            new_extra_mounts.append(processed_mount_entry)

        return new_extra_mounts

    def run(self, command):
        if type(command) == str:
            command = [command]

        extra_mounts = self.validate_extra_mounts(self._mounts)

        pipe_parent, pipe_child = multiprocessing.Pipe()

        with self.mount_all(self.fs_root, extra_mounts):

            # Awful hack to ensure string-escape/unicode-escape are loaded:
            #
            # this ensures that when propagating an exception back from
            # the child process in a chroot, the required string-escape/
            # unicode-escape python modules are already in memory and no
            # attempt to lazy load them in the chroot is made.
            if sys.version_info.major == 2:
                unused = "Some Text".encode('string-escape')
            elif sys.version_info.major == 3:
                unused = "Some Text".encode('unicode-escape')

            process = multiprocessing.Process(
                target=run_command_in_chroot,
                args=(pipe_child, self.stdout, self.stderr, extra_mounts, self.fs_root,
                      command, self.cwd, self.env))
            process.start()
            process.join()

        if process.exitcode == 0:
            exit, out, err = pipe_parent.recv()
            return exit, out, err
        else:
            # Report a new exception including the traceback from the child process
            exception, tb = pipe_parent.recv()
            raise Exception('Received exception from chroot, child process traceback:\n%s\n' % tb)


def _run_command(argv, stdout, stderr, cwd=None, env=None):
    # Wrapper around subprocess.Popen() with common settings.
    #
    # This function blocks until the subprocess has terminated.
    #
    # Unlike the subprocess.Popen() function, if stdout or stderr are None then
    # output is discarded.
    #
    # It then returns a tuple of (exit code, stdout output, stderr output).
    # If stdout was not equal to subprocess.PIPE, stdout will be None. Same for
    # stderr.
    #

    if stdout is None or stderr is None:
        dev_null = open(os.devnull, 'w')
        stdout = stdout or dev_null
        stderr = stderr or dev_null
    else:
        dev_null = None

    try:
        process = subprocess.Popen(
            argv,
            # The default is to share file descriptors from the parent process
            # to the subprocess, which is rarely good for sandboxing.
            close_fds=True,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )

        # The 'out' variable will be None unless subprocess.PIPE was passed as
        # 'stdout' to subprocess.Popen(). Same for 'err' and 'stderr'. If
        # subprocess.PIPE wasn't passed for either it'd be safe to use .wait()
        # instead of .communicate(), but if they were then we must use
        # .communicate() to avoid blocking the subprocess if one of the pipes
        # becomes full. It's safe to use .communicate() in all cases.

        out, err = process.communicate()
    finally:
        if dev_null is not None:
            dev_null.close()

    return process.returncode, out, err


def run_command_in_chroot(pipe, stdout, stderr, extra_mounts, chroot_path,
                          command, cwd, env):
    # This function should be run in a multiprocessing.Process() subprocess,
    # because it calls os.chroot(). There's no 'unchroot()' function! After
    # chrooting, it calls sandboxlib._run_command(), which uses the
    # 'subprocess' module to exec 'command'. This means there are actually
    # two subprocesses, which is not ideal, but it seems to be the simplest
    # implementation.
    #
    # An alternative approach would be to use the 'preexec_fn' feature of
    # subprocess.Popen() to call os.chroot(rootfs_path) and os.chdir(cwd).
    # The Python 3 '_posixsubprocess' module hints in several places that
    # deadlocks can occur when using preexec_fn, and it is very difficult to
    # propagate exceptions from that function, so it seems best to avoid it.

    try:
        # You have most likely got to be the 'root' user in order for this to
        # work.

        try:
            os.chroot(chroot_path)
        except OSError as e:
            raise RuntimeError("Unable to chroot: %s" % e)

        # This is important in case 'cwd' is a relative path.
        os.chdir('/')

        if cwd is not None:
            try:
                os.chdir(cwd)
            except OSError as e:
                raise RuntimeError(
                    "Unable to set current working directory: %s" % e)

        exit, out, err = _run_command(
            command, stdout, stderr, env=env)
        pipe.send([exit, out, err])
        result = 0
    except Exception as e:
        tb = traceback.format_exc()
        pipe.send((e, tb))
        result = 1
    os._exit(result)
