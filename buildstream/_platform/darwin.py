#
#  Copyright (C) 2017 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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

import os
import resource

from .._exceptions import PlatformError
from ..sandbox import SandboxDummy

from . import Platform


class Darwin(Platform):

    # This value comes from OPEN_MAX in syslimits.h
    OPEN_MAX = 10240

    def __init__(self, context):

        super().__init__(context)

    @property
    def artifactcache(self):
        return self._artifact_cache

    def create_sandbox(self, *args, **kwargs):
        return SandboxDummy(*args, **kwargs)

    def get_cpu_count(self, cap=None):
        if cap < os.cpu_count():
            return cap
        else:
            return os.cpu_count()

    def set_resource_limits(self, soft_limit=OPEN_MAX, hard_limit=None):
        super().set_resource_limits(soft_limit)
