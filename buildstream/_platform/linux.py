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

from .. import utils
from .._sandboxbwrap import SandboxBwrap
from .._artifactcache.ostreecache import OSTreeCache

from . import Platform


class Linux(Platform):

    def __init__(self, context, system_platform=sys.platform):

        super().__init__(context, system_platform)
        self._artifact_cache = OSTreeCache(context)

    @property
    def artifactcache(self):
        return self._artifact_cache

    def create_sandbox(self, *args, **kwargs):
        return SandboxBwrap(*args, **kwargs)

    def stage_to_sandbox(self, artifact, sandbox, path=None, files=None):

        basedir = sandbox.get_directory()
        stagedir = basedir if path is None else os.path.join(basedir, path.lstrip(os.sep))

        return utils.link_files(artifact, stagedir, files=files)
