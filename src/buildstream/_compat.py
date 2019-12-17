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

# This module contains some patches to make it easier to handle different
# python versions. Patches can be removed once we decide a specific version
# does not need to be supported anymore.

import sys

# Python < 3.7
if sys.version_info[:2] < (3, 7):
    # multiprocessing.Process got a 'close' method on python3.7
    # A no-op is fine for previous versions
    import multiprocessing
    def _close(self):
        pass

    multiprocessing.Process.close = _close
