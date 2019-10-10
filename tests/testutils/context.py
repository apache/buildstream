#
#  Copyright (C) 2019 Bloomberg Finance LP
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
from unittest.mock import MagicMock

from types import MethodType
from contextlib import contextmanager

from buildstream._context import Context
from buildstream._state import _Task


# Handle messages from the pipeline
def _dummy_message_handler(message, is_silenced):
    pass


@contextmanager
def _get_dummy_task(self, activity_name, *, element_name=None, full_name=None, silent_nested=False):
    yield MagicMock(spec=_Task("state", activity_name, full_name, 0))


# dummy_context()
#
# Context manager to create minimal context for tests.
#
# Args:
#    config (filename): The configuration file, if any
#
@contextmanager
def dummy_context(*, config=None):
    with Context() as context:
        if not config:
            config = os.devnull

        context.load(config=config)

        context.messenger.set_message_handler(_dummy_message_handler)
        context.messenger.simple_task = MethodType(_get_dummy_task, context.messenger)

        yield context
