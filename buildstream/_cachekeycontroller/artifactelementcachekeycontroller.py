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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Jonathan Maw <jonathan.maw@codethink.co.uk>


from .cachekeycontroller import CacheKeyController


# ArtifactElementCacheKeyController()
#
# The ArtifactElementCacheKeyController is an object that handles the
# "calculation" of cache keys for ArtifactElements, where the cache key
# is predefined and doesn't need to be calculated.
#
# When the ArtifactElement has been refactored away, this can be removed, too.
class ArtifactElementCacheKeyController(CacheKeyController):
    def __init__(self, key):
        super().__init__()
        # Can't set the weak and strong keys now, or the Element won't
        # generate Artifacts in _update_state
        self.__key = key

    def calculate_strong_key(self, element):
        self._strong_key = self.__key
        return self._strong_key

    def calculate_weak_key(self, element):
        self._weak_key = self.__key
        return self._weak_key
