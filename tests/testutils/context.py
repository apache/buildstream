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

from types import MethodType
from contextlib import contextmanager

from buildstream._context import Context


# Handle messages from the pipeline
def _dummy_message_handler(message, is_silenced):
    pass


class _DummyTask:
    # Note that unittest.mock.MagicMock doesn't pickle, so we must make our
    # _DummyTask manually here.
    def __init__(self, state, action_name, full_name, elapsed_offset):
        self._state = state
        self.action_name = action_name
        self.full_name = full_name
        self.elapsed_offset = elapsed_offset
        self.current_progress = None
        self.maximum_progress = None

    def set_render_cb(self, callback):
        pass

    def set_current_progress(self, progress):
        pass

    def set_maximum_progress(self, progress):
        pass

    def add_current_progress(self):
        pass

    def add_maximum_progress(self):
        pass


@contextmanager
def _get_dummy_task(self, activity_name, *, element_name=None, full_name=None, silent_nested=False):
    yield _DummyTask("state", activity_name, full_name, 0)


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
