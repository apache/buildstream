#
#  Copyright (C) 2018 Codethink Limited
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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>

from .._platform import Platform


# SandboxConfig
#
# A container for sandbox configuration data. We want the internals
# of this to be opaque, hence putting it in its own private file.
class SandboxConfig:
    def __init__(self, sandbox_config, platform):
        host_arch = platform.get_host_arch()
        host_os = platform.get_host_os()

        sandbox_config.validate_keys(["build-uid", "build-gid", "build-os", "build-arch"])

        build_os = sandbox_config.get_str("build-os", default=None)
        if build_os:
            self.build_os = build_os.lower()
        else:
            self.build_os = host_os

        build_arch = sandbox_config.get_str("build-arch", default=None)
        if build_arch:
            self.build_arch = Platform.canonicalize_arch(build_arch)
        else:
            self.build_arch = host_arch

        self.build_uid = sandbox_config.get_int("build-uid", None)
        self.build_gid = sandbox_config.get_int("build-gid", None)

    # get_unique_key():
    #
    # This returns the SandboxConfig's contribution
    # to an element's cache key.
    #
    # Returns:
    #    (dict): A dictionary to add to an element's cache key
    #
    def get_unique_key(self):

        unique_key = {"os": self.build_os, "arch": self.build_arch}

        if self.build_uid is not None:
            unique_key["build-uid"] = self.build_uid

        if self.build_gid is not None:
            unique_key["build-gid"] = self.build_gid

        return unique_key
