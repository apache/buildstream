#
#  Copyright (C) 2018 Bloomberg LP
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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>
#        Benjamin Schubert <bschubert15@bloomberg.net>

"""
Foundation types
================

"""

from enum import Enum
import heapq


class Scope(Enum):
    """Defines the scope of dependencies to include for a given element
    when iterating over the dependency graph in APIs like
    :func:`Element.dependencies() <buildstream.element.Element.dependencies>`
    """

    ALL = 1
    """All elements which the given element depends on, following
    all elements required for building. Including the element itself.
    """

    BUILD = 2
    """All elements required for building the element, including their
    respective run dependencies. Not including the given element itself.
    """

    RUN = 3
    """All elements required for running the element. Including the element
    itself.
    """

    NONE = 4
    """Just the element itself, no dependencies.

    *Since: 1.4*
    """


class Consistency():
    """Defines the various consistency states of a :class:`.Source`.
    """

    INCONSISTENT = 0
    """Inconsistent

    Inconsistent sources have no explicit reference set. They cannot
    produce a cache key, be fetched or staged. They can only be tracked.
    """

    RESOLVED = 1
    """Resolved

    Resolved sources have a reference and can produce a cache key and
    be fetched, however they cannot be staged.
    """

    CACHED = 2
    """Cached

    Sources have a cached unstaged copy in the source directory.
    """


class CoreWarnings():
    """CoreWarnings()

    Some common warnings which are raised by core functionalities within BuildStream are found in this class.
    """

    OVERLAPS = "overlaps"
    """
    This warning will be produced when buildstream detects an overlap on an element
        which is not whitelisted. See :ref:`Overlap Whitelist <public_overlap_whitelist>`
    """

    REF_NOT_IN_TRACK = "ref-not-in-track"
    """
    This warning will be produced when a source is configured with a reference
    which is found to be invalid based on the configured track
    """

    BAD_ELEMENT_SUFFIX = "bad-element-suffix"
    """
    This warning will be produced when an element whose name does not end in .bst
    is referenced either on the command line or by another element
    """

    BAD_CHARACTERS_IN_NAME = "bad-characters-in-name"
    """
    This warning will be produces when filename for a target contains invalid
    characters in its name.
    """

    UNALIASED_URL = "unaliased-url"
    """
    A URL used for fetching a sources was specified without specifying any
    :ref:`alias <project_source_aliases>`
    """


# _KeyStrength():
#
# Strength of cache key
#
class _KeyStrength(Enum):

    # Includes strong cache keys of all build dependencies and their
    # runtime dependencies.
    STRONG = 1

    # Includes names of direct build dependencies but does not include
    # cache keys of dependencies.
    WEAK = 2


# _UniquePriorityQueue():
#
# Implements a priority queue that adds only each key once.
#
# The queue will store and priority based on a tuple (key, item).
#
class _UniquePriorityQueue:

    def __init__(self):
        self._items = set()
        self._heap = []

    # push():
    #
    # Push a new item in the queue.
    #
    # If the item is already present in the queue as identified by the key,
    # this is a noop.
    #
    # Args:
    #     key (hashable, comparable): unique key to use for checking for
    #                                 the object's existence and used for
    #                                 ordering
    #     item (any): item to push to the queue
    #
    def push(self, key, item):
        if key not in self._items:
            self._items.add(key)
            heapq.heappush(self._heap, (key, item))

    # pop():
    #
    # Pop the next item from the queue, by priority order.
    #
    # Returns:
    #     (any): the next item
    #
    # Throw:
    #     IndexError: when the list is empty
    #
    def pop(self):
        key, item = heapq.heappop(self._heap)
        self._items.remove(key)
        return item

    def __len__(self):
        return len(self._heap)
