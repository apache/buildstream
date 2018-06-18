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
import os


# SandboxConfig
#
# A container for sandbox configuration data. We want the internals
# of this to be opaque, hence putting it in its own private file.
class SandboxConfig():
    def __init__(self, build_uid, build_gid):
        self.build_uid = build_uid
        self.build_gid = build_gid

    # get_unique_key():
    #
    # This returns the SandboxConfig's contribution
    # to an element's cache key.
    #
    # Returns:
    #    (dict): A dictionary to add to an element's cache key
    #
    def get_unique_key(self):

        # Currently operating system and machine architecture
        # are not configurable and we have no sandbox implementation
        # which can conform to such configurations.
        #
        # However this should be the right place to support
        # such configurations in the future.
        #
        operating_system, _, _, _, machine_arch = os.uname()
        unique_key = {
            'os': operating_system,
            'arch': machine_arch
        }

        # Avoid breaking cache key calculation with
        # the addition of configurabuild build uid/gid
        if self.build_uid != 0:
            unique_key['build-uid'] = self.build_uid

        if self.build_gid != 0:
            unique_key['build-gid'] = self.build_gid

        return unique_key
