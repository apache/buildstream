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

# pylint: disable=redefined-outer-name

import time

import psutil
import pytest

from buildstream import node, DownloadableFileSource


# Number of seconds to wait for background threads to exit.
_AWAIT_THREADS_TIMEOUT_SECONDS = 5


def has_no_unexpected_background_threads(expected_num_threads):
    # Use psutil as threading.active_count() doesn't include gRPC threads.
    process = psutil.Process()

    wait = 0.1
    for _ in range(0, int(_AWAIT_THREADS_TIMEOUT_SECONDS / wait)):
        if process.num_threads() == expected_num_threads:
            return True
        time.sleep(wait)

    return False


@pytest.fixture(autouse=True, scope="session")
def default_thread_number():
    # xdist/execnet has its own helper thread.
    return psutil.Process().num_threads()


# Catch tests that don't shut down background threads, which could then lead
# to other tests hanging when BuildStream uses fork().
@pytest.fixture(autouse=True)
def thread_check(default_thread_number):
    assert has_no_unexpected_background_threads(default_thread_number)
    yield
    assert has_no_unexpected_background_threads(default_thread_number)


# Reset global state in node.pyx to improve test isolation
@pytest.fixture(autouse=True)
def reset_global_node_state():
    node._reset_global_state()
    DownloadableFileSource._reset_url_opener()
