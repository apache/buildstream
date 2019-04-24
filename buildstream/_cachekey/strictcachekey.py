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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>


from .cachekey import CacheKey
from ..types import _KeyStrength, Consistency


# TODO: DOCSTRINGS
class StrictCacheKey(CacheKey):
    def calculate_keys(self):
        if self._element._get_consistency() == Consistency.INCONSISTENT:
            return

        if not self._calculate_weak_key():
            # Failure when calculating weak key
            # This usually happens when the element is BST_STRICT_REBUILD, and
            # its dependency is an uncached workspace, or pending track.
            return

        if not self._calculate_strict_key():
            # Failure when calculating strict key
            # Usually because a dependency is pending track or is workspaced
            # and not cached
            return

        # Assemble the strict artifact
        self._element._assemble_strict_artifact()

        if self._strong_key is None:
            self._strong_key = self._strict_key

        self._update_strong_cached()

        self._element._check_ready_for_runtime()

    def get_key(self, strength):
        # NOTE: KeyStrength numbers are not sequential
        if strength == _KeyStrength.WEAK:
            return self._weak_key
        elif strength == _KeyStrength.STRICT:
            return self._strict_key
        elif strength == _KeyStrength.STRONG:
            return self._strong_key
        else:
            raise AssertionError("Bad key strength value {}".format(strength))

    def maybe_schedule_assemble(self):
        # XXX: Should _cached_success take a _KeyStrength?
        if (self._weak_key and self._strong_key and
                self._element._is_pending_assembly() and
                self._element._is_required() and
                not self._element._cached_success() and
                not self._element._pull_pending()):
            self._element._schedule_assemble()

    def tracking_done(self):
        # this generator includes this corresponding element
        for element in self._element._reverse_deps_for_update():
            element._calculate_keys()
            element._maybe_schedule_assemble()

    def pull_done(self):
        # Cache keys are already known before this.
        # Element may become cached.
        self._update_strong_cached()

        # If it failed to pull, it should assemble.
        self._element._maybe_schedule_assemble()

    def assemble_done(self):
        # Cache keys are already known before this.
        # Element may become cached.
        self._update_strong_cached()
