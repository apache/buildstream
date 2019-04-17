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

from .. import _yaml
from .._exceptions import ImplError
from ..types import _KeyStrength, Scope

# Internal record of the size of a cache key
_CACHEKEY_SIZE = len(hashlib.sha256().hexdigest())


# Hex digits
_HEX_DIGITS = "0123456789abcdef"


# TODO: DOCSTRINGS
class CacheKey():
    def __init__(self, element):
        self._element = element
        self._weak_key = None
        self._strict_key = None
        self._strong_key = None
        self._weak_cached = None
        # TODO: Understand why there's no __strict_cached
        self._strong_cached = None

    # ABSTRACT METHODS
    def calculate_keys(self):
        raise ImplError("CacheKey does not implement calculate_keys()")

    def get_key(self, strength):
        raise ImplError("CacheKey does not implement get_key()")

    def maybe_schedule_assemble(self):
        raise ImplError("CacheKey does not implement maybe_schedule_assemble()")

    def is_cached(self, strength):
        raise ImplError("CacheKey does not implement is_cached()")

    def tracking_done(self):
        raise ImplError("CacheKey does not implement tracking_done()")

    def pull_done(self):
        raise ImplError("CacheKey does not implement pull_done()")

    def assemble_done(self):
        raise ImplError("CacheKey does not implement assemble_done()")

    # PRIVATE METHODS

    def _update_weak_cached(self):
        if self._weak_key and not self._weak_cached:
            self._weak_cached = self._element._is_key_cached(self._weak_key)

    def _update_strong_cached(self):
        if self._strict_key and not self._strong_cached:
            self._strong_cached = self._element._is_key_cached(self._strict_key)

    # Set the weak key
    def _calculate_weak_key(self):
        if self._weak_key is None:
            if self._element.BST_STRICT_REBUILD:
                deps = [e._get_cache_key(strength=_KeyStrength.WEAK)
                        for e in self._element.dependencies(Scope.BUILD)]
            else:
                deps = [e.name for e in self._element.dependencies(Scope.BUILD, recurse=False)]

            # XXX: Perhaps it would be better to move all cache key calculation
            #      into CacheKey, and have Element use a function to generate
            #      the cache_key_dict. Generate, rather than store internally,
            #      because workspaces could have a different cache_key_dict after
            #      building.
            self._weak_key = self._element._calculate_cache_key(deps)

        if self._weak_key is None:
            return False

        return True

    # Set the strict key
    def _calculate_strict_key(self):
        if self._strict_key is None:
            deps = [e._get_cache_key(strength=_KeyStrength.STRICT)
                    for e in self._element.dependencies(Scope.BUILD)]
            self._strict_key = self._element._calculate_cache_key(deps)

        if self._strict_key is None:
            return False

        return True


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
    ordered = _yaml.node_sanitize(value)
    ustring = ujson.dumps(ordered, sort_keys=True, escape_forward_slashes=False).encode('utf-8')
    return hashlib.sha256(ustring).hexdigest()
