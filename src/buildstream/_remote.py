#
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

import threading

import grpc

from ._exceptions import ImplError, RemoteError


# BaseRemote():
#
# Provides the basic functionality required to set up remote
# interaction via GRPC. In particular, this will set up a
# grpc.insecure_channel, or a grpc.secure_channel, based on the given
# spec.
#
# Customization for the particular protocol is expected to be
# performed in children.
#
class BaseRemote:
    key_name = None

    def __init__(self, spec):
        self.spec = spec
        self.channel = None
        self._initialized = False
        self._lock = threading.Lock()

    ####################################################
    #                 Dunder methods                   #
    ####################################################
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, traceback):
        self.close()
        return False

    def __str__(self):
        return self.spec.url

    ####################################################
    #                   Remote API                     #
    ####################################################

    # init():
    #
    # Initialize the given remote. This function must be called before
    # any communication is performed, since such will otherwise fail.
    #
    def init(self):
        with self._lock:
            if self._initialized:
                return

            self.channel = self.spec.open_channel()
            self._configure_protocols()
            self._initialized = True

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None

        self._initialized = False

    # check():
    #
    # Check if the remote is functional and has all the required
    # capabilities. This should be used somewhat like an assertion,
    # expecting a RemoteError.
    #
    # Note that this method runs the calls on a separate process, so
    # that we can use grpc calls even if we are on the main process.
    #
    # Raises:
    #     RemoteError: If the grpc call fails.
    #
    def check(self):
        try:
            self.init()
            self._check()
        except grpc.RpcError as e:
            # str(e) is too verbose for errors reported to the user
            raise RemoteError("{}: {}".format(e.code().name, e.details()))
        finally:
            self.close()

    ####################################################
    #                Abstract methods                  #
    ####################################################

    # _check():
    #
    # Check if this remote provides everything required for the
    # particular kind of remote. This is expected to be called as part
    # of check(), and must be called in a non-main process.
    #
    # Raises:
    #    RemoteError: when the remote isn't compatible or another error happened.
    #
    def _check(self):
        pass

    # _configure_protocols():
    #
    # An abstract method to configure remote-specific protocols. This
    # is *not* done as super().init() because we want to be able to
    # set self._initialized *after* initialization completes in the
    # parent class.
    #
    # This method should *never* be called outside of init().
    #
    def _configure_protocols(self):
        raise ImplError("An implementation of a Remote must configure its protocols.")
