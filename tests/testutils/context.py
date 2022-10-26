#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

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
