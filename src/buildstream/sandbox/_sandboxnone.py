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
#  Authors:
#        Angelos Evripiotis <jevripiotis@bloomberg.net>

import pathlib
import pprint
import subprocess

from .._exceptions import SandboxError
from .sandbox import Sandbox


class SandboxNone(Sandbox):

    def __init__(self, *args, **kwargs):
        # TODO: don't require a dict copy.
        kwargs = kwargs.copy()
        kwargs['allow_real_directory'] = True

        super().__init__(*args, **kwargs)

        uid = self._get_config().build_uid
        gid = self._get_config().build_gid
        if uid != 0 or gid != 0:
            raise SandboxError("Chroot sandboxes cannot specify a non-root uid/gid "
                               "({},{} were supplied via config)".format(uid, gid))

        self.mount_map = None

    def _run(self, command, flags, *, cwd, env):

        install_path = pathlib.Path(self.get_directory()) / 'buildstream-install'

        env = env.copy()
        env['BST_INSTALLPATH'] = str(install_path)

        # TODO: figure out what to do with 'flags'.

        # TODO: do this in a robust way.
        if cwd.startswith("/"):
            cwd = cwd[1:]

        # pprint.pprint(env)

        path = pathlib.Path(self.get_directory()) / cwd
        print('run', command, 'in', path)
        result = subprocess.run(command, cwd=path, env=env)

        # out = pathlib.Path(self.get_directory()) / 'buildstream-install'
        # out.mkdir(exist_ok=True)

        return result.returncode
