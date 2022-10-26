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
#
#  Authors:
#        Angelos Evripiotis <jevripiotis@bloomberg.net>

import collections
from contextlib import contextmanager
import platform


# override_platform_uname()
#
# Context manager to override the reported value of `platform.uname()`.
#
# Args:
#   system (str): Optional str to replace the 1st entry of uname with.
#   machine (str): Optional str to replace the 5th entry of uname with.
#
@contextmanager
def override_platform_uname(*, system=None, machine=None):
    orig_func = platform.uname
    orig_system, node, release, version, orig_machine, processor = platform.uname()

    system = system or orig_system
    machine = machine or orig_machine

    def override_func():
        # NOTE:
        #  1. We can't use `_replace` here because of this bug in
        #     Python 3.9.0 - https://bugs.python.org/issue42163.
        #  2. We need to create a new subclass because the constructor of
        #     `platform.uname_result` doesn't share the same interface between
        #     Python 3.8 and 3.9.
        uname_result = collections.namedtuple("uname_result", "system node release version machine processor")
        return uname_result(system, node, release, version, machine, processor)

    platform.uname = override_func
    try:
        yield
    finally:
        platform.uname = orig_func
