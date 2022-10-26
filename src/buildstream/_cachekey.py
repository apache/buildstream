#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
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
