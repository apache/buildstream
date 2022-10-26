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
#  Authors:
#        Jim MacArthur <jim.macarthur@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#

from typing import TYPE_CHECKING, Dict, Optional, Union
from .._platform import Platform

if TYPE_CHECKING:
    from ..node import Node, MappingNode


# SandboxConfig
#
# The Sandbox configuration parameters, this object carries configuration
# required to instantiate the correct type of sandbox, and assert that
# the local or remote worker sandbox has the capabilities required.
#
# Args:
#    build_os: The build OS name
#    build_arch: A canonical machine architecture name, as defined by Platform.canonicalize_arch()
#    build_uid: The UID for the sandbox process
#    build_gid: The GID for the sandbox process
#
# If the build_uid or build_gid is unspecified, then the underlying sandbox implementation
# does not guarantee what UID/GID will be used, but generally UID/GID 0 will be used in a
# sandbox implementation which supports UID/GID control.
#
# If the build_uid or build_gid is specified, then the UID/GID is guaranteed to match
# the specified UID/GID, if the underlying sandbox implementation does not support UID/GID
# control, then an error will be raised when attempting to configure the sandbox.
#
class SandboxConfig:
    def __init__(
        self, *, build_os: str, build_arch: str, build_uid: Optional[int] = None, build_gid: Optional[int] = None
    ):
        self.build_os = build_os
        self.build_arch = build_arch
        self.build_uid = build_uid
        self.build_gid = build_gid

    # to_dict():
    #
    # Represent the SandboxConfig as a dictionary.
    #
    # This dictionary will be stored in the corresponding artifact
    # whenever an artifact is cached. When loading an element from
    # an artifact, then this dict will be loaded as a MappingNode
    # and interpreted by SandboxConfig.new_from_node().
    #
    # This function is also used to contribute to the owning element's cache key.
    #
    # Returns:
    #    A dictionary representation of this SandboxConfig
    #
    def to_dict(self) -> Dict[str, Union[str, int]]:

        # Assign mandatory portions of the sandbox configuration
        #
        # /!\ No additional mandatory members can ever be added to
        #     the sandbox configuration, as that would result in
        #     breaking cache key stability.
        #
        sandbox_dict: Dict[str, Union[str, int]] = {"build-os": self.build_os, "build-arch": self.build_arch}

        # Assign optional portions of the sandbox configuration
        #
        # /!\ In order to preserve cache key stability, these attributes
        #     are only ever added to the dictionary if they have been
        #     explicitly set, unset values must not affect the dictionary.
        #
        if self.build_uid is not None:
            sandbox_dict["build-uid"] = self.build_uid
        if self.build_gid is not None:
            sandbox_dict["build-gid"] = self.build_gid

        return sandbox_dict

    # new_from_node():
    #
    # Instantiate a new SandboxConfig from YAML configuration.
    #
    # If the Platform is specified, then we expect to be loading
    # from project definitions, and some defaults will be derived
    # from the Platform. Otherwise, we expect to be loading from
    # a cached artifact, and values are expected to exist on the
    # given node.
    #
    # Args:
    #    config: The YAML configuration node
    #    platform: The host Platform instance, or None
    #
    # Returns:
    #    A new SandboxConfig instance
    #
    @classmethod
    def new_from_node(cls, config: "MappingNode[Node]", *, platform: Optional[Platform] = None) -> "SandboxConfig":
        config.validate_keys(["build-uid", "build-gid", "build-os", "build-arch"])

        build_os: str
        build_arch: str

        if platform:
            tmp = config.get_str("build-os", None)
            if tmp:
                build_os = tmp.lower()
            else:
                build_os = platform.get_host_os()

            tmp = config.get_str("build-arch", None)
            if tmp:
                build_arch = Platform.canonicalize_arch(tmp)
            else:
                build_arch = platform.get_host_arch()
        else:
            build_os = config.get_str("build-os")
            build_arch = config.get_str("build-arch")

        build_uid = config.get_int("build-uid", None)
        build_gid = config.get_int("build-gid", None)

        return cls(build_os=build_os, build_arch=build_arch, build_uid=build_uid, build_gid=build_gid)
