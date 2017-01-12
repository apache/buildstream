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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os


# Types of status messages.
#
class MessageType():
    DEBUG = "debug"        # Debugging message
    STATUS = "status"      # Status message
    WARN = "warning"       # Warning messages
    ERROR = "error"        # Error messages

    # The following types are timed, SUCCESS/FAIL have timestamps
    START = "start"        # Status start message
    SUCCESS = "success"    # Successful status complete message
    FAIL = "failure"       # Failing status complete message


# Message object
#
class Message():
    def __init__(self, unique_id, message_type, message,
                 detail=None,
                 elapsed=None):
        self.pid = os.getpid()
        self.unique_id = unique_id
        self.message_type = message_type
        self.message = message
        self.detail = detail
        self.elapsed = elapsed

        if message_type in (MessageType.SUCCESS, MessageType.FAIL):
            assert(elapsed is not None)
