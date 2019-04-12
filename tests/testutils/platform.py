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
    result = platform.uname()

    if system is not None:
        result = result._replace(system=system)
    if machine is not None:
        result = result._replace(machine=machine)

    def override_func():
        return result

    platform.uname = override_func
    try:
        yield
    finally:
        platform.uname = orig_func
