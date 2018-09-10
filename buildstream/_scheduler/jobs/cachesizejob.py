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
#  Author:
#        Tristan Daniël Maat <tristan.maat@codethink.co.uk>
#
from .job import Job
from ..._platform import Platform


class CacheSizeJob(Job):
    def __init__(self, *args, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._complete_cb = complete_cb

        platform = Platform.get_platform()
        self._artifacts = platform.artifactcache

    def child_process(self):
        return self._artifacts.compute_cache_size()

    def parent_complete(self, success, result):
        if success:
            self._artifacts.set_cache_size(result)

            if self._complete_cb:
                self._complete_cb(result)

    def child_process_data(self):
        return {}
