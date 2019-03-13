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
        self._casquota = context.get_casquota()
        self._artifacts = context.artifactcache

    def child_process(self):
        def progress():
            self.send_message('update-cache-size',
                              self._casquota.get_cache_size())

        from ..._cas.cascache import allow_cache_size_write_context
        from ..._cas.cascache import allow_cache_size_write_context_pid
        from ..._cas.cascache import disallow_cache_size_write_context_pid
        allow_cache_size_write_context_pid()
        with allow_cache_size_write_context():
            result = self._casquota.clean(progress)
        disallow_cache_size_write_context_pid()
        return result

    def handle_message(self, message_type, message):
        # Update the cache size in the main process as we go,
        # this provides better feedback in the UI.
        if message_type == 'update-cache-size':
            self._casquota.set_cache_size(message)
            self._casquota.set_cache_size(message, write_to_disk=False)
            from ..._cas.cascache import allow_cache_size_write_context
            with allow_cache_size_write_context():
                self._casquota.set_cache_size(message)
            return True

        return False

    def parent_complete(self, status, result):
        if status == JobStatus.OK:
            from ..._cas.cascache import allow_cache_size_write_context
            with allow_cache_size_write_context():
                self._casquota.set_cache_size(result)

        if self._complete_cb:
            self._complete_cb(status, result)
