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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import datetime
import os


# Types of status messages.
#
class MessageType():
    DEBUG = "debug"        # Debugging message
    STATUS = "status"      # Status message, verbose details
    INFO = "info"          # Informative messages
    WARN = "warning"       # Warning messages
    ERROR = "error"        # Error messages
    BUG = "bug"            # An unhandled exception was raised in a plugin
    LOG = "log"            # Messages for log files _only_, never in the frontend

    # Timed Messages: SUCCESS and FAIL have duration timestamps
    START = "start"        # Status start message
    SUCCESS = "success"    # Successful status complete message
    FAIL = "failure"       # Failing status complete message
    SKIPPED = "skipped"


# Messages which should be reported regardless of whether
# they are currently silenced or not
unconditional_messages = [
    MessageType.INFO,
    MessageType.WARN,
    MessageType.FAIL,
    MessageType.ERROR,
    MessageType.BUG
]


# Message object
#
class Message():

    def __init__(self, unique_id, message_type, message,
                 task_id=None,
                 detail=None,
                 action_name=None,
                 elapsed=None,
                 depth=None,
                 logfile=None,
                 sandbox=None,
                 scheduler=False):
        self.message_type = message_type  # Message type
        self.message = message            # The message string
        self.detail = detail              # An additional detail string
        self.action_name = action_name    # Name of the task queue (fetch, refresh, build, etc)
        self.elapsed = elapsed            # The elapsed time, in timed messages
        self.depth = depth                # The depth of a timed message
        self.logfile = logfile            # The log file path where commands took place
        self.sandbox = sandbox            # The sandbox directory where an error occurred (if any)
        self.pid = os.getpid()            # The process pid
        self.unique_id = unique_id        # The plugin object ID issueing the message
        self.task_id = task_id            # The plugin object ID of the task
        self.scheduler = scheduler        # Whether this is a scheduler level message
        self.creation_time = datetime.datetime.now()
        if message_type in (MessageType.SUCCESS, MessageType.FAIL):
            assert elapsed is not None
