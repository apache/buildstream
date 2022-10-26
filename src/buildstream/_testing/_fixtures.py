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

# pylint: disable=redefined-outer-name

import time

import psutil
import pytest


# Number of seconds to wait for background threads to exit.
_AWAIT_THREADS_TIMEOUT_SECONDS = 5


def has_no_unexpected_background_threads(expected_num_threads):
    # Use psutil as threading.active_count() doesn't include gRPC threads.
    #
    # If background gRPC threads are lingering, there is a good chance that
    # this is due to BuildStream failing to close an open grpc channel.
    #
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
