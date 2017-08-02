#!/usr/bin/env python3
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
import sys
import pathlib

from .. import utils
from .. import PlatformError
from .._sandboxchroot import SandboxChroot
from .._artifactcache.tarcache import TarCache

from . import Platform


class Unix(Platform):

    def __init__(self, context, system_platform=sys.platform):

        super().__init__(context, system_platform)
        self._artifact_cache = TarCache(context)

        # Not necessarily 100% reliable, but we want to fail early.
        if os.geteuid() != 0:
            raise PlatformError("Root privileges are required to run without bubblewrap.")

    @property
    def artifactcache(self):
        return self._artifact_cache

    def create_sandbox(self, *args, **kwargs):
        return SandboxChroot(*args, **kwargs)

    def stage_to_sandbox(self, artifact, sandbox, path=None, files=None):

        basedir = sandbox.get_directory()
        stagedir = basedir if path is None else os.path.join(basedir, path.lstrip(os.sep))

        can_hardlink = True

        # If the staged path is in a path that is marked RW, we cannot
        # hardlink, since we would risk modifying this staged artifact
        pathlib_path = pathlib.PurePath(stagedir)
        marked_directories = sandbox._get_marked_directories()
        for marked_dir in marked_directories:
            pathlib_marked_dir = pathlib.PurePath(marked_dir['directory'])

            if pathlib_marked_dir in pathlib_path.parents:
                can_hardlink = False
                break

        # We must also ensure that / is read-only, since otherwise the
        # artifact may also be modified.
        #
        # / can currently only be read-write if the element is a
        # script element and explicitly sets root to read-write, or if
        # it is a build element and runs integration commands.
        can_hardlink = can_hardlink and sandbox.always_ro

        if not can_hardlink:
            sandbox._warn("Copying instead of hardlinking")

        if can_hardlink:
            return utils.link_files(artifact, stagedir, files=files)
        else:
            return utils.copy_files(artifact, stagedir, files=files)
