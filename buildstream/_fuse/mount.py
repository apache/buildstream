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
from .. import _signals


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
#   requests on it's own, but then we have no way to shut down the
#   daemon.
#
#   With the blocking approach, we still have it as a child process
#   so we can tell it to gracefully terminate; but it's impossible
#   to know when the mount is done, there is no callback for that
#
#   The solution we use here without digging too deep into the
#   low level fuse API, is to fork a child process which will
#   fun the fuse loop in foreground, and we block the parent
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

    ################################################
    #               User Facing API                #
    ################################################

    # mount():
    #
    # User facing API for mounting a fuse subclass implementation
    #
    # Args:
    #    (str): Location to mount this fuse fs
    #
    def mount(self, mountpoint):

        assert self.__process is None

        self.__mountpoint = mountpoint
        self.__process = Process(target=self.__run_fuse)

        # Ensure the child fork() does not inherit our signal handlers, if the
        # child wants to handle a signal then it will first set it's own
        # handler, and then unblock it.
        with _signals.blocked([signal.SIGTERM, signal.SIGTSTP, signal.SIGINT], ignore=False):
            self.__process.start()

        # This is horrible, we're going to wait until mountpoint is mounted and that's it.
        while not os.path.ismount(mountpoint):
            time.sleep(1 / 100)

    # unmount():
    #
    # User facing API for unmounting a fuse subclass implementation
    #
    def unmount(self):

        # Terminate child process and join
        if self.__process is not None:
            self.__process.terminate()
            self.__process.join()

            # Report an error if ever the underlying operations crashed for some reason.
            if self.__process.exitcode != 0:
                raise FuseMountError("{} reported exit code {} when unmounting"
                                     .format(type(self).__name__, self.__process.exitcode))

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

        self.mount(mountpoint)
        try:
            with _signals.terminator(self.unmount):
                yield
        finally:
            self.unmount()

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
    def __run_fuse(self):

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
        self.__operations = self.create_operations()

        # Run fuse in foreground in this child process, internally libfuse
        # will handle SIGTERM and gracefully exit it's own little main loop.
        #
        FUSE(self.__operations, self.__mountpoint, nothreads=True, foreground=True, nonempty=True)

        # Explicit 0 exit code, if the operations crashed for some reason, the exit
        # code will not be 0, and we want to know about it.
        #
        sys.exit(0)
