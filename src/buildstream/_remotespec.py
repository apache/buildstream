#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import os
from typing import Optional, Tuple, List, cast
from urllib.parse import urlparse
import grpc
from grpc import ChannelCredentials, Channel

from ._exceptions import LoadError, RemoteError
from .exceptions import LoadErrorReason
from .types import FastEnum
from .node import MappingNode


# RemoteType():
#
# Defines the different types of remote.
#
class RemoteType(FastEnum):
    INDEX = "index"
    STORAGE = "storage"
    ENDPOINT = "endpoint"
    ALL = "all"

    def __str__(self) -> str:
        if self.name:
            return self.name.lower().replace("_", "-")
        return ""


# RemoteSpecPurpose():
#
# What a RemoteSpec is going to be used for.
#
# This is currently only used to control the behavior
# of RemoteSpec.new_from_string(), after that, a RemoteSpec
# has a `push` attribute which is either True or False.
#
class RemoteSpecPurpose(FastEnum):
    ALL = 0  # Pushing and pulling
    PUSH = 1  # Only pushing
    PULL = 2  # Only pulling


# RemoteSpec():
#
# This data structure holds all of the details required to
# connect to and communicate with the various grpc remote
# services, like the artifact cache, source cache and remote
# execution service.
#
class RemoteSpec:
    def __init__(
        self,
        remote_type: str,
        url: str,
        *,
        push: bool = False,
        server_cert: str = None,
        client_key: str = None,
        client_cert: str = None,
        instance_name: Optional[str] = None,
        spec_node: Optional[MappingNode] = None,
    ) -> None:

        #
        # Public members
        #

        # The remote type
        self.remote_type: str = remote_type

        # Whether we are allowed to push (for asset caches only)
        self.push: bool = push

        # The url of the remote, this may contain a port number
        self.url: str = url

        # The name of the grpc service to talk to at this remote url
        self.instance_name: Optional[str] = instance_name

        # The credentials
        self.server_cert_file: Optional[str] = server_cert
        self.client_key_file: Optional[str] = client_key
        self.client_cert_file: Optional[str] = client_cert

        #
        # Private members
        #

        # The provenance node for error reporting
        self._spec_node: Optional[MappingNode] = spec_node

        # The credentials loaded from disk, and whether they were loaded
        self._server_cert: Optional[bytes] = None
        self._client_key: Optional[bytes] = None
        self._client_cert: Optional[bytes] = None
        self._cred_files_loaded: bool = False

        # The grpc credentials object
        self._credentials: Optional[ChannelCredentials] = None

    #
    # Implement dunder methods to support hashing and
    # comparisons.
    #
    def __eq__(self, other: object) -> bool:
        return hash(self) == hash(other)

    def __hash__(self) -> int:
        return hash(
            (
                self.remote_type,
                self.push,
                self.url,
                self.instance_name,
                self.server_cert_file,
                self.client_key_file,
                self.client_cert_file,
            )
        )

    def __str__(self) -> str:
        string = self.url + "\n"
        string += "push: {} type: {} instance: {}\n".format(self.push, self.remote_type, self.instance_name)
        if self._spec_node:
            provenance = str(self._spec_node.get_provenance())
        else:
            provenance = "command line"
        string += "loaded from: {}".format(provenance)

        return string

    # server_cert()
    #
    @property
    def server_cert(self) -> Optional[bytes]:
        self._load_credential_files()
        return self._server_cert

    # client_key()
    #
    @property
    def client_key(self) -> Optional[bytes]:
        self._load_credential_files()
        return self._client_key

    # client_cert()
    #
    @property
    def client_cert(self) -> Optional[bytes]:
        self._load_credential_files()
        return self._client_cert

    # credentials()
    #
    @property
    def credentials(self) -> ChannelCredentials:
        if not self._credentials:
            self._credentials = grpc.ssl_channel_credentials(
                root_certificates=self.server_cert,
                private_key=self.client_key,
                certificate_chain=self.client_cert,
            )
        return self._credentials

    # open_channel()
    #
    # Opens a gRPC channel based on this spec.
    #
    def open_channel(self) -> Channel:
        url = urlparse(self.url)

        # Assert port number for RE endpoints
        #
        if self.remote_type == RemoteType.ENDPOINT and not url.port:
            message = (
                "Remote execution endpoints must specify the port number, for example: http://buildservice:50051."
            )
            if self._spec_node:
                message = "{}: {}".format(self._spec_node.get_provenance(), message)
            raise RemoteError(message)

        if url.scheme == "http":
            channel = grpc.insecure_channel("{}:{}".format(url.hostname, url.port or 80))
        elif url.scheme == "https":
            channel = grpc.secure_channel("{}:{}".format(url.hostname, url.port or 443), self.credentials)
        else:
            message = "Only 'http' and 'https' protocols are supported, but '{}' was supplied.".format(url.scheme)
            if self._spec_node:
                message = "{}: {}".format(self._spec_node.get_provenance(), message)
            raise RemoteError(message)

        return channel

    # new_from_node():
    #
    # Creates a RemoteSpec() from a YAML loaded node.
    #
    # Args:
    #    spec_node: The configuration node describing the spec.
    #    basedir: The base directory from which to find certificates.
    #    remote_execution: Whether this spec is used for remote execution (some keys are invalid)
    #
    # Returns:
    #    The described RemoteSpec instance.
    #
    # Raises:
    #    LoadError: If the node is malformed.
    #
    @classmethod
    def new_from_node(
        cls, spec_node: MappingNode, basedir: Optional[str] = None, *, remote_execution: bool = False
    ) -> "RemoteSpec":
        server_cert: Optional[str] = None
        client_key: Optional[str] = None
        client_cert: Optional[str] = None
        push: bool = False
        remote_type: str = RemoteType.ENDPOINT

        valid_keys: List[str] = ["url", "instance-name", "auth"]
        if not remote_execution:
            remote_type = cast(str, spec_node.get_enum("type", RemoteType, default=RemoteType.ALL))
            push = spec_node.get_bool("push", default=False)
            valid_keys += ["push", "type"]

        spec_node.validate_keys(valid_keys)

        # FIXME: This explicit error message should not be necessary, instead
        #        we should be able to inform Node.get_str() that an empty string
        #        is not acceptable, and have Node do the work of raising this error.
        #
        url = spec_node.get_str("url")
        if not url:
            provenance = spec_node.get_node("url").get_provenance()
            raise LoadError("{}: empty artifact cache URL".format(provenance), LoadErrorReason.INVALID_DATA)

        instance_name = spec_node.get_str("instance-name", default=None)

        auth_node = spec_node.get_mapping("auth", None)
        if auth_node:
            server_cert, client_key, client_cert = cls._parse_auth(auth_node, basedir)

        return cls(
            remote_type,
            url,
            push=push,
            server_cert=server_cert,
            client_key=client_key,
            client_cert=client_cert,
            instance_name=instance_name,
            spec_node=spec_node,
        )

    # new_from_string():
    #
    # Creates a RemoteSpec() from a string, used to parse CLI parameters
    #
    # If certificates are passed, they are interpreted as relative to the
    # current working directory.
    #
    # Args:
    #    string: The user provided string
    #    purpose: The purpose this RemoteSpec is intended for (RemoteSpecPurpose)
    #
    # Returns:
    #    The described RemoteSpec instance.
    #
    # Raises:
    #    RemoteError: In case parsing the string fails
    #
    @classmethod
    def new_from_string(cls, string: str, purpose: int = RemoteSpecPurpose.ALL) -> "RemoteSpec":
        url: Optional[str] = None
        instance_name: Optional[str] = None
        remote_type: str = RemoteType.ALL
        push: bool = True
        server_cert: Optional[str] = None
        client_key: Optional[str] = None
        client_cert: Optional[str] = None

        if purpose == RemoteSpecPurpose.PULL:
            push = False

        split = string.split(",")
        if len(split) > 1:
            for split_string in split:
                subsplit = split_string.split("=")

                if len(subsplit) != 2:
                    raise RemoteError(
                        "Invalid format '{}' found in remote specification: {}".format(split_string, string)
                    )

                key: str = subsplit[0]
                val: str = subsplit[1]

                if key == "url":
                    url = val
                elif key == "instance-name":
                    instance_name = val
                elif key == "type":
                    remote_type = val
                    if remote_type not in [RemoteType.INDEX, RemoteType.STORAGE, RemoteType.ALL]:
                        raise RemoteError(
                            "Value for remote 'type' must be one of: {}".format(
                                ", ".join([RemoteType.INDEX, RemoteType.STORAGE, RemoteType.ALL])
                            )
                        )
                elif key == "push":

                    # Provide a sensible error for `bst artifact push --remote url=http://pony.com,push=False ...`
                    if purpose != RemoteSpecPurpose.ALL:
                        raise RemoteError("The 'push' key is invalid and assumed to be {}".format(push))

                    if val in ("True", "true"):
                        push = True
                    elif val in ("False", "false"):
                        push = False
                    else:
                        raise RemoteError("Value for 'push' must be 'True' or 'False'")
                elif key == "server-cert":
                    server_cert = cls._resolve_path(val, os.getcwd())
                elif key == "client-key":
                    client_key = cls._resolve_path(val, os.getcwd())
                elif key == "client-cert":
                    client_cert = cls._resolve_path(val, os.getcwd())
                else:
                    raise RemoteError("Unexpected key '{}' encountered".format(key))
        else:
            # No commas, only the URL was specified
            url = string

        if not url:
            raise RemoteError("No URL specified in remote")

        return cls(
            remote_type,
            url,
            push=push,
            server_cert=server_cert,
            client_key=client_key,
            client_cert=client_cert,
            instance_name=instance_name,
        )

    # _resolve_path()
    #
    # Resolve a path relative to the base directory
    #
    # Args:
    #    path: The path
    #    basedir: The base directory
    #
    # Returns:
    #    The resolved path
    #
    @classmethod
    def _resolve_path(cls, path: str, basedir: Optional[str]) -> str:
        path = os.path.expanduser(path)
        if basedir:
            path = os.path.join(basedir, path)
        return path

    # _parse_auth():
    #
    # Parse the "auth" data
    #
    # Args:
    #    auth_node: The auth node
    #    basedir: The base directory which cert files are relative to, or None
    #
    # Returns:
    #    A 3 tuple containing the filenames for the server-cert,
    #    the client-key and the client-cert
    #
    @classmethod
    def _parse_auth(
        cls, auth_node: MappingNode, basedir: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:

        auth_keys = ["server-cert", "client-key", "client-cert"]
        auth_values = {}
        auth_node.validate_keys(auth_keys)

        for key in auth_keys:
            value = auth_node.get_str(key, None)
            if value:
                value = cls._resolve_path(value, basedir)
            auth_values[key] = value

        server_cert = auth_values["server-cert"]
        client_key = auth_values["client-key"]
        client_cert = auth_values["client-cert"]

        if client_key and not client_cert:
            provenance = auth_node.get_node("client-key").get_provenance()
            raise LoadError(
                "{}: 'client-key' was specified without 'client-cert'".format(provenance), LoadErrorReason.INVALID_DATA
            )

        if client_cert and not client_key:
            provenance = auth_node.get_node("client-cert").get_provenance()
            raise LoadError(
                "{}: 'client-cert' was specified without 'client-key'".format(provenance), LoadErrorReason.INVALID_DATA
            )

        return server_cert, client_key, client_cert

    # _load_credential_files():
    #
    # A helper method to load the credentials files, ignoring any input
    # arguments that are None.
    #
    def _load_credential_files(self) -> None:
        def maybe_read_file(filename: Optional[str]) -> Optional[bytes]:
            if filename:
                try:
                    with open(filename, "rb") as f:
                        return f.read()
                except IOError as e:
                    message = "Failed to load credentials file: {}".format(filename)
                    if self._spec_node:
                        message = "{}: {}".format(self._spec_node.get_provenance(), message)
                    raise RemoteError(message, detail=str(e), reason="load-remote-creds-failed") from e
            return None

        if not self._cred_files_loaded:
            self._server_cert = maybe_read_file(self.server_cert_file)
            self._client_key = maybe_read_file(self.client_key_file)
            self._client_cert = maybe_read_file(self.client_cert_file)
            self._cred_files_loaded = True


# RemoteExecutionSpec():
#
# This data structure holds all of the details required to
# connect to a remote execution cluster, it is essentially
# comprised of 3 RemoteSpec objects which are used to
# communicate with various components of an RE build cluster.
#
class RemoteExecutionSpec:
    def __init__(
        self, exec_spec: RemoteSpec, storage_spec: Optional[RemoteSpec], action_spec: Optional[RemoteSpec]
    ) -> None:
        self.exec_spec: RemoteSpec = exec_spec
        self.storage_spec: Optional[RemoteSpec] = storage_spec
        self.action_spec: Optional[RemoteSpec] = action_spec

    # new_from_node():
    #
    # Creates a RemoteExecutionSpec() from a YAML loaded node.
    #
    # Args:
    #    node: The node to parse
    #    basedir: The base directory from which to find certificates.
    #
    # Returns:
    #    The described RemoteSpec instance.
    #
    # Raises:
    #    LoadError: If the node is malformed.
    #
    @classmethod
    def new_from_node(
        cls, node: MappingNode, basedir: Optional[str] = None, *, remote_cache: bool = False
    ) -> "RemoteExecutionSpec":
        node.validate_keys(["execution-service", "storage-service", "action-cache-service"])

        exec_node = node.get_mapping("execution-service")
        storage_node = node.get_mapping("storage-service", default=None)
        if not storage_node and not remote_cache:
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Remote execution requires 'storage-service' to be specified in the 'remote-execution' section if not already specified globally in the 'cache' section".format(
                    provenance
                ),
                LoadErrorReason.INVALID_DATA,
            )
        action_node = node.get_mapping("action-cache-service", default=None)

        exec_spec = RemoteSpec.new_from_node(exec_node, basedir, remote_execution=True)

        storage_spec: Optional[RemoteSpec]
        if storage_node:
            storage_spec = RemoteSpec.new_from_node(storage_node, basedir, remote_execution=True)
        else:
            storage_spec = None

        action_spec: Optional[RemoteSpec]
        if action_node:
            action_spec = RemoteSpec.new_from_node(action_node, basedir, remote_execution=True)
        else:
            action_spec = None

        return cls(exec_spec, storage_spec, action_spec)
