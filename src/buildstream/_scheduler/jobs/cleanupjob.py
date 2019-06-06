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
from .job import Job, JobStatus, ChildJob


class CleanupJob(Job):
    def __init__(self, *args, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._complete_cb = complete_cb

        context = self._scheduler.context
        self._casquota = context.get_casquota()

    def handle_message(self, message):
        # Update the cache size in the main process as we go,
        # this provides better feedback in the UI.
        self._casquota.set_cache_size(message, write_to_disk=False)

    def parent_complete(self, status, result):
        if status == JobStatus.OK:
            self._casquota.set_cache_size(result, write_to_disk=False)

        if self._complete_cb:
            self._complete_cb(status, result)

    def create_child_job(self, *args, **kwargs):
        return ChildCleanupJob(*args, casquota=self._scheduler.context.get_casquota(), **kwargs)


class ChildCleanupJob(ChildJob):
    def __init__(self, *args, casquota, **kwargs):
        super().__init__(*args, **kwargs)
        self._casquota = casquota

    def child_process(self):
        def progress():
            self.send_message(self._casquota.get_cache_size())
        return self._casquota.clean(progress)
