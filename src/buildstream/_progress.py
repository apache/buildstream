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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

import time

class Progress():
    def __init__(self, context, activity_name, *, total=None, unique_id=None):
        self._context = context
        self._activity_name = activity_name
        self._last_reported = time.monotonic()
        self._interval = 3.0 # seconds
        self._count = 0
        self._total = total
        self._unique_id = unique_id

    def add_total(self, count):
        if self._total is None:
            self._total = count
        else:
            self._total += count
        self._check_report_progress()

    def add_progress(self, count):
        self._count += count
        self._check_report_progress()

    def _check_report_progress(self):
        # It would be more efficient to have a time-based poll rather than
        # a regular check whether enough time has passed
        now = time.monotonic()
        if now >= self._last_reported + self._interval:
            self._last_reported = now
            message_text = self._activity_name + ": " + str(self._count)
            if self._total is not None:
                message_text += "/" + str(self._total)
            self._context.report_progress(message_text, self._unique_id)

        
