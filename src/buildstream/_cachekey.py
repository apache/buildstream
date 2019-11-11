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


import hashlib

import ujson


# Internal record of the size of a cache key
_CACHEKEY_SIZE = len(hashlib.sha256().hexdigest())


# Hex digits
_HEX_DIGITS = "0123456789abcdef"


# is_key()
#
# Check if the passed in string *could be* a cache key.  This basically checks
# that the length matches a sha256 hex digest, and that the string does not
# contain any non-hex characters and is fully lower case.
#
# Args:
#    key (str): The string to check
#
# Returns:
#    (bool): Whether or not `key` could be a cache key
#
def is_key(key):
    if len(key) != _CACHEKEY_SIZE:
        return False
    return not any(ch not in _HEX_DIGITS for ch in key)


# generate_key()
#
# Generate an sha256 hex digest from the given value. The value
# can be a simple value or recursive dictionary with lists etc,
# anything simple enough to serialize.
#
# Args:
#    value: A value to get a key for
#
# Returns:
#    (str): An sha256 hex digest of the given value
#
def generate_key(value):
    ustring = ujson.dumps(value, sort_keys=True, escape_forward_slashes=False).encode("utf-8")
    return hashlib.sha256(ustring).hexdigest()
