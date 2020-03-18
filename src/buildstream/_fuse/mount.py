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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import signal
import time
import sys

from contextlib import contextmanager
from multiprocessing import Process
from .fuse import FUSE

from .._exceptions import ImplError
from .. import _signals, utils


# Just a custom exception to raise here, for identifying possible
# bugs with a fuse layer implementation
#
class FuseMountError(Exception):
    pass


# This is a convenience class which takes care of synchronizing the
# startup of FUSE and shutting it down.
#
# The implementations / subclasses should:
#
#   - Overload the instance initializer to add any parameters
#     needed for their fuse Operations implementation
#
#   - Implement create_operations() to create the Operations
#     instance on behalf of the superclass, using any additional
#     parameters collected in the initializer.
#
# Mount objects can be treated as contextmanagers, the volume
# will be mounted during the context.
#
# UGLY CODE NOTE:
#
#   This is a horrible little piece of code. The problem we face
#   here is that the highlevel libfuse API has fuse_main(), which
#   will either block in the foreground, or become a full daemon.
#
#   With the daemon approach, we know that the fuse is mounted right
#   away when fuse_main() returns, then the daemon will go and handle
#   requests on its own, but then we have no way to shut down the
#   daemon.
#
#   With the blocking approach, we still have it as a child process
#   so we can tell it to gracefully terminate; but it's impossible
#   to know when the mount is done, there is no callback for that
#
#   The solution we use here without digging too deep into the
#   low level fuse API, is to start a child process which will
#   run the fuse loop in foreground, and we block the parent
#   process until the volume is mounted with a busy loop with timeouts.
#
class Mount():

    # These are not really class data, they are
    # just here for the sake of having None setup instead
    # of missing attributes, since we do not provide any
    # initializer and leave the initializer to the subclass.
    #
    __mountpoint = None
    __operations = None
    __process = None
    __logfile = None

    ################################################
    #               User Facing API                #
    ################################################

    def __init__(self, fuse_mount_options=None):
        self._fuse_mount_options = {} if fuse_mount_options is None else fuse_mount_options

    # _mount():
    #
    # Mount a fuse subclass implementation.
    #
    # Args:
    #    (str): Location to mount this fuse fs
    #
    def _mount(self, mountpoint):

        assert self.__process is None

        self.__mountpoint = mountpoint
        self.__process = Process(target=self.__run_fuse, args=(self.__logfile.name,))

        # Ensure the child process does not inherit our signal handlers, if the
        # child wants to handle a signal then it will first set its own
        # handler, and then unblock it.
        with _signals.blocked([signal.SIGTERM, signal.SIGTSTP, signal.SIGINT], ignore=False):
            self.__process.start()

        while not os.path.ismount(mountpoint):
            if not self.__process.is_alive():
                self.__logfile.seek(0)
                stderr = self.__logfile.read()
                raise FuseMountError("Unable to mount {}: {}".format(mountpoint, stderr.decode().strip()))

            time.sleep(1 / 100)

    # _unmount():
    #
    # Unmount a fuse subclass implementation.
    #
    def _unmount(self):

        # Terminate child process and join
        if self.__process is not None:
            self.__process.terminate()
            self.__process.join()

            # Report an error if ever the underlying operations crashed for some reason.
            if self.__process.exitcode != 0:
                self.__logfile.seek(0)
                stderr = self.__logfile.read()

                raise FuseMountError("{} reported exit code {} when unmounting: {}"
                                     .format(type(self).__name__, self.__process.exitcode, stderr))

        self.__mountpoint = None
        self.__process = None

    # mounted():
    #
    # A context manager to run a code block with this fuse Mount
    # mounted, this will take care of automatically unmounting
    # in the case that the calling process is terminated.
    #
    # Args:
    #    (str): Location to mount this fuse fs
    #
    @contextmanager
    def mounted(self, mountpoint):

        with utils._tempnamedfile() as logfile:
            self.__logfile = logfile

            self._mount(mountpoint)
            try:
                with _signals.terminator(self._unmount):
                    yield
            finally:
                self._unmount()

        self.__logfile = None

    ################################################
    #               Abstract Methods               #
    ################################################

    # create_operations():
    #
    # Create an Operations class (from fusepy) and return it
    #
    # Returns:
    #    (Operations): A FUSE Operations implementation
    def create_operations(self):
        raise ImplError("Mount subclass '{}' did not implement create_operations()"
                        .format(type(self).__name__))

    ################################################
    #                Child Process                 #
    ################################################
    def __run_fuse(self, filename):
        # Override stdout/stderr to the file given as a pointer, that way our parent process can get our output
        out = open(filename, "w")
        os.dup2(out.fileno(), sys.stdout.fileno())
        os.dup2(out.fileno(), sys.stderr.fileno())

        # First become session leader while signals are still blocked
        #
        # Then reset the SIGTERM handler to the default and finally
        # unblock SIGTERM.
        #
        os.setsid()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, [signal.SIGTERM])

        # Ask the subclass to give us an Operations object
        #
        self.__operations = self.create_operations()  # pylint: disable=assignment-from-no-return

        # Run fuse in foreground in this child process, internally libfuse
        # will handle SIGTERM and gracefully exit its own little main loop.
        #
        try:
            FUSE(self.__operations, self.__mountpoint, nothreads=True, foreground=True,
                 **self._fuse_mount_options)
        except RuntimeError as exc:
            # FUSE will throw a RuntimeError with the exit code of libfuse as args[0]
            sys.exit(exc.args[0])

        # Explicit 0 exit code, if the operations crashed for some reason, the exit
        # code will not be 0, and we want to know about it.
        #
        sys.exit(0)
