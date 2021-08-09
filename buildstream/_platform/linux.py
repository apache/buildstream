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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import subprocess

from .. import _site
from .. import utils
from ..sandbox import SandboxBwrap

from . import Platform


class Linux(Platform):

    def __init__(self):

        super().__init__()

        self._uid = os.geteuid()
        self._gid = os.getegid()

        self._die_with_parent_available = _site.check_bwrap_version(0, 1, 8)
        self._user_ns_available = self._check_user_ns_available()

    def create_sandbox(self, *args, **kwargs):
        # Inform the bubblewrap sandbox as to whether it can use user namespaces or not
        kwargs['user_ns_available'] = self._user_ns_available
        kwargs['die_with_parent_available'] = self._die_with_parent_available
        return SandboxBwrap(*args, **kwargs)

    def check_sandbox_config(self, config):
        if self._user_ns_available:
            # User namespace support allows arbitrary build UID/GID settings.
            return True
        else:
            # Without user namespace support, the UID/GID in the sandbox
            # will match the host UID/GID.
            return config.build_uid == self._uid and config.build_gid == self._gid

    ################################################
    #              Private Methods                 #
    ################################################
    def _check_user_ns_available(self):

        # Here, lets check if bwrap is able to create user namespaces,
        # issue a warning if it's not available, and save the state
        # locally so that we can inform the sandbox to not try it
        # later on.
        bwrap = utils.get_host_tool('bwrap')
        whoami = utils.get_host_tool('whoami')
        try:
            output = subprocess.check_output([
                bwrap,
                '--ro-bind', '/', '/',
                '--unshare-user',
                '--uid', '0', '--gid', '0',
                whoami,
            ])
            output = output.decode('UTF-8').strip()
        except subprocess.CalledProcessError:
            output = ''

        return output == 'root'
