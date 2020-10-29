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
