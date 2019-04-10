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

# The API version.
#
# This is encoded into BuildStream so that we can perform
# checks in advance of a release.
#
# Rules for updating the versions:
#
#    BST_API_VERSION_MAJOR
#    ~~~~~~~~~~~~~~~~~~~~~
#    This indicates the main API version, it should only ever
#    be incremented if we break API again and release BuildStream 3.
#
#    BST_API_VERSION_MINOR
#    ~~~~~~~~~~~~~~~~~~~~~
#    This should be incremented to the next even number in the master
#    branch directly after releasing a new stable minor point release.
#
#    I.e. after releasing BuildStream 2.0, BST_API_VERSION_MINOR should
#    be set to 2 in the master branch where we will create development
#    snapshots of 2.1, leading up to the next feature adding release
#    of 2.2.
#
BST_API_VERSION_MAJOR = 2
BST_API_VERSION_MINOR = 0


# The base BuildStream format version
#
# This version is bumped whenever enhancements are made
# to the `project.conf` format or the core element format.
#
BST_FORMAT_VERSION = 23


# The base BuildStream artifact version
#
# The artifact version changes whenever the cache key
# calculation algorithm changes in an incompatible way
# or if buildstream was changed in a way which can cause
# the same cache key to produce something that is no longer
# the same.
BST_CORE_ARTIFACT_VERSION = 8
