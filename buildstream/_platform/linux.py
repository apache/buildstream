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
import shutil
import subprocess

from .. import utils
from ..sandbox import SandboxDummy, SandboxBuildBox

from . import Platform


class Linux(Platform):

    def __init__(self):

        super().__init__()

        self._uid = os.geteuid()
        self._gid = os.getegid()

        self._have_fuse = os.path.exists("/dev/fuse")

        bwrap_version = self._get_bwrap_version()

        if bwrap_version is None:
            self._bwrap_exists = False
            self._have_good_bwrap = False
            self._die_with_parent_available = False
        else:
            self._bwrap_exists = True
            self._have_good_bwrap = (0, 1, 2) <= bwrap_version
            self._die_with_parent_available = (0, 1, 8) <= bwrap_version

        self._local_sandbox_available = self._have_fuse and self._have_good_bwrap

        if self._local_sandbox_available:
            self._user_ns_available = self._check_user_ns_available()
        else:
            self._user_ns_available = False

    def create_sandbox(self, *args, **kwargs):
        if not self._local_sandbox_available:
            return self._create_dummy_sandbox(*args, **kwargs)
        else:
            # return self._create_bwrap_sandbox(*args, **kwargs)
            return SandboxBuildBox(*args, **kwargs)

    def check_sandbox_config(self, config):
        if not self._local_sandbox_available:
            # Accept all sandbox configs as it's irrelevant with the dummy sandbox (no Sandbox.run).
            return True

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

    def _create_dummy_sandbox(self, *args, **kwargs):
        reasons = []
        if not self._have_fuse:
            reasons.append("FUSE is unavailable")
        if not self._have_good_bwrap:
            if self._bwrap_exists:
                reasons.append("`bwrap` is too old (bst needs at least 0.1.2)")
            else:
                reasons.append("`bwrap` executable not found")

        kwargs['dummy_reason'] = " and ".join(reasons)
        return SandboxDummy(*args, **kwargs)

    def _create_bwrap_sandbox(self, *args, **kwargs):
        from ..sandbox._sandboxbwrap import SandboxBwrap
        # Inform the bubblewrap sandbox as to whether it can use user namespaces or not
        kwargs['user_ns_available'] = self._user_ns_available
        kwargs['die_with_parent_available'] = self._die_with_parent_available
        return SandboxBwrap(*args, **kwargs)

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

    def _get_bwrap_version(self):
        # Get the current bwrap version
        #
        # returns None if no bwrap was found
        # otherwise returns a tuple of 3 int: major, minor, patch
        bwrap_path = shutil.which('bwrap')

        if not bwrap_path:
            return None

        cmd = [bwrap_path, "--version"]
        try:
            version = str(subprocess.check_output(cmd).split()[1], "utf-8")
        except subprocess.CalledProcessError:
            return None

        return tuple(int(x) for x in version.split("."))
