#
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#         Will Salmon <will.salmon@codethink.co.uk>

import time


def wait_for_cache_granularity():
    # This isn't called very often so has minimal impact on test runtime.
    # If this changes it may be worth while adding a more sophisticated approach.
    """
    Mitigate the coarse granularity of the gitlab runners mtime

    This function waits for the mtime to increment so that the cache can sort by mtime and
    get the most recent results.
    """
    time.sleep(1.1)
