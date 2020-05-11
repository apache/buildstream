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

import os
from collections import namedtuple
from urllib.parse import urlparse

import grpc

from ._exceptions import LoadError, ImplError, RemoteError
from .exceptions import LoadErrorReason
from .types import FastEnum


# RemoteType():
#
# Defines the different types of remote.
#
class RemoteType(FastEnum):
    INDEX = "index"
    STORAGE = "storage"
    ALL = "all"

    def __str__(self):
        return self.name.lower().replace("_", "-")


# RemoteSpec():
#
# Defines the basic structure of a remote specification.
#
class RemoteSpec(namedtuple("RemoteSpec", "url push server_cert client_key client_cert instance_name type")):

    # new_from_config_node
    #
    # Creates a RemoteSpec() from a YAML loaded node.
    #
    # Args:
    #    spec_node (MappingNode): The configuration node describing the spec.
    #    basedir (str): The base directory from which to find certificates.
    #
    # Returns:
    #    (RemoteSpec) - The described RemoteSpec instance.
    #
    # Raises:
    #    LoadError: If the node is malformed.
    #
    @classmethod
    def new_from_config_node(cls, spec_node, basedir=None):
        spec_node.validate_keys(["url", "push", "server-cert", "client-key", "client-cert", "instance-name", "type"])

        url = spec_node.get_str("url")
        if not url:
            provenance = spec_node.get_node("url").get_provenance()
            raise LoadError("{}: empty artifact cache URL".format(provenance), LoadErrorReason.INVALID_DATA)

        push = spec_node.get_bool("push", default=False)
        instance_name = spec_node.get_str("instance-name", default=None)

        def parse_cert(key):
            cert = spec_node.get_str(key, default=None)
            if cert:
                cert = os.path.expanduser(cert)

                if basedir:
                    cert = os.path.join(basedir, cert)

            return cert

        cert_keys = ("server-cert", "client-key", "client-cert")
        server_cert, client_key, client_cert = tuple(parse_cert(key) for key in cert_keys)

        if client_key and not client_cert:
            provenance = spec_node.get_node("client-key").get_provenance()
            raise LoadError(
                "{}: 'client-key' was specified without 'client-cert'".format(provenance), LoadErrorReason.INVALID_DATA
            )

        if client_cert and not client_key:
            provenance = spec_node.get_node("client-cert").get_provenance()
            raise LoadError(
                "{}: 'client-cert' was specified without 'client-key'".format(provenance), LoadErrorReason.INVALID_DATA
            )

        type_ = spec_node.get_enum("type", RemoteType, default=RemoteType.ALL)

        return cls(url, push, server_cert, client_key, client_cert, instance_name, type_)


# FIXME: This can be made much nicer in python 3.7 through the use of
# defaults - or hell, by replacing it all with a typing.NamedTuple
#
# Note that defaults are specified from the right, and ommitted values
# are considered mandatory.
#
# Disable type-checking since "Callable[...] has no attributes __defaults__"
RemoteSpec.__new__.__defaults__ = (  # type: ignore
    # mandatory          # url            - The url of the remote
    # mandatory          # push           - Whether the remote should be used for pushing
    None,  # server_cert    - The server certificate
    None,  # client_key     - The (private) client key
    None,  # client_cert    - The (public) client certificate
    None,  # instance_name  - The (grpc) instance name of the remote
    RemoteType.ALL,  # type           - The type of the remote (index, storage, both)
)


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
        self._initialized = False

        self.channel = None

        self.server_cert = None
        self.client_key = None
        self.client_cert = None

        self.instance_name = spec.instance_name
        self.push = spec.push
        self.url = spec.url

    # init():
    #
    # Initialize the given remote. This function must be called before
    # any communication is performed, since such will otherwise fail.
    #
    def init(self):
        if self._initialized:
            return

        # Set up the communcation channel
        url = urlparse(self.spec.url)
        if url.scheme == "http":
            port = url.port or 80
            self.channel = grpc.insecure_channel("{}:{}".format(url.hostname, port))
        elif url.scheme == "https":
            port = url.port or 443
            try:
                server_cert, client_key, client_cert = _read_files(
                    self.spec.server_cert, self.spec.client_key, self.spec.client_cert
                )
            except FileNotFoundError as e:
                raise RemoteError("Could not read certificates: {}".format(e)) from e
            self.server_cert = server_cert
            self.client_key = client_key
            self.client_cert = client_cert
            credentials = grpc.ssl_channel_credentials(
                root_certificates=self.server_cert, private_key=self.client_key, certificate_chain=self.client_cert
            )
            self.channel = grpc.secure_channel("{}:{}".format(url.hostname, port), credentials)
        else:
            raise RemoteError("Unsupported URL: {}".format(self.spec.url))

        self._configure_protocols()

        self._initialized = True

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, traceback):
        self.close()
        return False

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None

        self._initialized = False

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

    def __str__(self):
        return self.url


# _read_files():
#
# A helper method to read a bunch of files, ignoring any input
# arguments that are None.
#
# Args:
#    files (Iterable[str|None]): A list of files to read. Nones are passed back.
#
# Returns:
#    Generator[str|None, None, None] - Strings read from those files.
#
def _read_files(*files):
    def read_file(f):
        if f:
            with open(f, "rb") as data:
                return data.read()
        return None

    return (read_file(f) for f in files)
