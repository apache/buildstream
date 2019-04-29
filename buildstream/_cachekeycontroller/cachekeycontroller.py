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


from ..types import _KeyStrength, Scope
from .._exceptions import ImplError
from .. import _cachekey


# CacheKeyController()
#
# The CacheKeyController is an object that handles cache key generation
# and ownership. It is a base class that has implementations for specific use-cases.
class CacheKeyController():
    def __init__(self):
        self._weak_key = None
        self._strong_key = None

    ####################
    # Abstract Methods #
    ####################

    # calculate_strong_key()
    #
    # Calculates the strong cache key
    #
    # args:
    #    element (Element): the element object
    #
    # returns:
    #    (str): The key generated, or None
    #
    def calculate_strong_key(self, element):
        raise ImplError("CacheKeyController does not implement calculate_strong_key")

    ##################
    # Public Methods #
    ##################

    # calculate_weak_key()
    #
    # Calculates the weak cache key.
    # There are two ways that a weak cache key is built, thanks to
    # `Element.BST_STRICT_REBUILD`.
    # Without `BST_STRICT_REBUILD`, the weak cache key only includes the names of
    # the element's direct dependencies.
    # With `BST_STRICT_REBUILD`, the key changes if any of the build-dependencies
    # have changed.
    #
    # args:
    #    element (Element): the element object
    #
    # returns:
    #    (str): The key generated, or None
    #
    def calculate_weak_key(self, element):
        if self._weak_key is None:
            if element.BST_STRICT_REBUILD:
                dependencies = [
                    e._get_cache_key(strength=_KeyStrength.WEAK)
                    for e in element.dependencies(Scope.BUILD)
                ]
            else:
                dependencies = [
                    e.name for e in element.dependencies(Scope.BUILD, recurse=False)
                ]

            self._weak_key = self._calculate_cache_key(element, dependencies)

        return self._weak_key

    # get_key()
    #
    # Returns the cache key corresponding to a given key strength
    #
    # args:
    #    strength (_KeyStrength): The key strength, either WEAK or STRONG
    #
    # returns:
    #    (str): The key for a given strength
    #
    def get_key(self, strength):
        if strength == _KeyStrength.WEAK:
            return self._weak_key
        elif strength == _KeyStrength.STRONG:
            return self._strong_key
        else:
            raise AssertionError("Unexpected key strength '{}'".format(strength))

    # clear_keys()
    #
    # Erases all stored cache keys
    #
    def clear_keys(self):
        self._weak_key = None
        self._strong_key = None

    ###################
    # Private methods #
    ###################

    # _calculate_cache_key()
    #
    # Calculates a cache key using metadata provided from an element,
    # and a given list of dependencies.
    #
    # Args:
    #    element (Element): The element
    #    dependencies (list): The dependencies to generate a key with
    #
    # Returns:
    #    (str): The cache key given the element and dependencies,
    #           or None if dependencies are missing
    #
    def _calculate_cache_key(self, element, dependencies):
        # No cache keys for dependencies which have no cache keys
        if None in dependencies:
            return None

        cache_key_dict = element._get_cache_key_dict()
        cache_key_dict['dependencies'] = dependencies
        return _cachekey.generate_key(cache_key_dict)
