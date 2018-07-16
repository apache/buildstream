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
import os
from contextlib import contextmanager

from .job import Job
from ..._platform import Platform
from ..._message import Message


class CleanupJob(Job):
    def __init__(self, *args, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._complete_cb = complete_cb
        self._cache = Platform._instance.artifactcache

    def _child_process(self):
        return self._cache.clean()

    def _parent_complete(self, success, result):
        self._cache._set_cache_size(result)
        if self._complete_cb:
            self._complete_cb()

    @contextmanager
    def _child_logging_enabled(self, logfile):
        self._logfile = logfile.format(pid=os.getpid())
        yield self._logfile
        self._logfile = None

    # _message():
    #
    # Sends a message to the frontend
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self._scheduler.context.message(Message(None, message_type, message, **args))

    def _child_log(self, message):
        message.action_name = self.action_name

        with open(self._logfile, 'a+') as log:
            message_text = self._format_frontend_message(message, '[cleanup]')
            log.write('{}\n'.format(message_text))
            log.flush()

        return message

    def _child_process_data(self):
        return {}
