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
from ..._message import Message, MessageType


class CacheSizeJob(Job):
    def __init__(self, *args, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._complete_cb = complete_cb
        self._cache = Platform._instance.artifactcache

    def _child_process(self):
        return self._cache.calculate_cache_size()

    def _parent_complete(self, success, result):
        self._cache._set_cache_size(result)
        if self._complete_cb:
            self._complete_cb(result)

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
        with open(self._logfile, 'a+') as log:
            INDENT = "    "
            EMPTYTIME = "--:--:--"

            template = "[{timecode: <8}] {type: <7} {name: <15}: {message}"
            detail = ''
            if message.detail is not None:
                template += "\n\n{detail}"
                detail = message.detail.rstrip('\n')
                detail = INDENT + INDENT.join(detail.splitlines(True))

            timecode = EMPTYTIME
            if message.message_type in (MessageType.SUCCESS, MessageType.FAIL):
                hours, remainder = divmod(int(message.elapsed.total_seconds()), 60**2)
                minutes, seconds = divmod(remainder, 60)
                timecode = "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)

            message_text = template.format(timecode=timecode,
                                           type=message.message_type.upper(),
                                           name='cache_size',
                                           message=message.message,
                                           detail=detail)

            log.write('{}\n'.format(message_text))
            log.flush()

        return message

    def _child_process_data(self):
        return {}
