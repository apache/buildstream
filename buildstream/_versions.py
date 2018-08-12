#
#  Copyright (C) 2018 Codethink Limited
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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>


# The base BuildStream format version
#
# This version is bumped whenever enhancements are made
# to the `project.conf` format or the core element format.
#
BST_FORMAT_VERSION = 12


# The base BuildStream artifact version
#
# The artifact version changes whenever the cache key
# calculation algorithm changes in an incompatible way
# or if buildstream was changed in a way which can cause
# the same cache key to produce something that is no longer
# the same.

BST_CORE_ARTIFACT_VERSION = ('bst-1.2', 3)
