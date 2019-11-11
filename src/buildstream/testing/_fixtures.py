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

import psutil
import pytest

from buildstream import node, utils

# Catch tests that don't shut down background threads, which could then lead
# to other tests hanging when BuildStream uses fork().
@pytest.fixture(autouse=True)
def thread_check():
    # xdist/execnet has its own helper thread.
    # Ignore that for `utils._is_single_threaded` checks.
    utils._INITIAL_NUM_THREADS_IN_MAIN_PROCESS = psutil.Process().num_threads()

    yield
    assert utils._is_single_threaded()


# Reset global state in node.pyx to improve test isolation
@pytest.fixture(autouse=True)
def reset_global_node_state():
    node._reset_global_state()
