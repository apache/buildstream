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
from .job import Job, JobStatus


class CleanupJob(Job):
    def __init__(self, *args, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._complete_cb = complete_cb

        context = self._scheduler.context
        self._artifacts = context.artifactcache

    def child_process(self):
        def progress():
            self.send_message('update-cache-size',
                              self._artifacts.get_cache_size())
        return self._artifacts.clean(progress)

    def handle_message(self, message_type, message):

        # Update the cache size in the main process as we go,
        # this provides better feedback in the UI.
        if message_type == 'update-cache-size':
            self._artifacts.set_cache_size(message)
            return True

        return False

    def parent_complete(self, status, result):
        if status == JobStatus.OK:
            self._artifacts.set_cache_size(result)

        if self._complete_cb:
            self._complete_cb(status, result)
