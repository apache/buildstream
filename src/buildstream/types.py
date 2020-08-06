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

from typing import Any, Dict, List, Union

from ._types import MetaFastEnum


class FastEnum(metaclass=MetaFastEnum):
    """
    A reimplementation of a subset of the `Enum` functionality, which is far quicker than `Enum`.

    :class:`enum.Enum` attributes accesses can be really slow, and slow down the execution noticeably.
    This reimplementation doesn't suffer the same problems, but also does not reimplement everything.
    """

    name = None
    """The name of the current Enum entry, same as :func:`enum.Enum.name`
    """

    value = None
    """The value of the current Enum entry, same as :func:`enum.Enum.value`
    """

    # A dict of all values mapping to the entries in the enum
    _value_to_entry = dict()  # type: Dict[str, Any]

    @classmethod
    def values(cls):
        """Get all the possible values for the enum.

        Returns:
            list: the list of all possible values for the enum
        """
        return cls._value_to_entry.keys()

    def __new__(cls, value):
        try:
            return cls._value_to_entry[value]
        except KeyError:
            if type(value) is cls:  # pylint: disable=unidiomatic-typecheck
                return value
            raise ValueError("Unknown enum value: {}".format(value))

    def __eq__(self, other):
        if self.__class__ is not other.__class__:
            raise ValueError("Unexpected comparison between {} and {}".format(self, repr(other)))
        # Enums instances are unique, so creating an instance with the same value as another will just
        # send back the other one, hence we can use an identity comparison, which is much faster than '=='
        return self is other

    def __ne__(self, other):
        if self.__class__ is not other.__class__:
            raise ValueError("Unexpected comparison between {} and {}".format(self, repr(other)))
        return self is not other

    def __hash__(self):
        return hash(id(self))

    def __str__(self):
        return "{}.{}".format(self.__class__.__name__, self.name)

    def __reduce__(self):
        return self.__class__, (self.value,)


class Scope(FastEnum):
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
    """


class CoreWarnings:
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


# _KeyStrength():
#
# Strength of cache key
#
class _KeyStrength(FastEnum):

    # Includes strong cache keys of all build dependencies and their
    # runtime dependencies.
    STRONG = 1

    # Includes names of direct build dependencies but does not include
    # cache keys of dependencies.
    WEAK = 2


# _SchedulerErrorAction()
#
# Actions the scheduler can take on error
#
class _SchedulerErrorAction(FastEnum):

    # Continue building the rest of the tree
    CONTINUE = "continue"

    # finish ongoing work and quit
    QUIT = "quit"

    # Abort immediately
    TERMINATE = "terminate"


# _CacheBuildTrees()
#
# When to cache build trees
#
class _CacheBuildTrees(FastEnum):

    # Always store build trees
    ALWAYS = "always"

    # Store build trees when they might be useful for BuildStream
    # (eg: on error, to allow for a shell to debug that)
    AUTO = "auto"

    # Never cache build trees
    NEVER = "never"


# _PipelineSelection()
#
# Defines the kind of pipeline selection to make when the pipeline
# is provided a list of targets, for whichever purpose.
#
# These values correspond to the CLI `--deps` arguments for convenience.
#
class _PipelineSelection(FastEnum):

    # Select only the target elements in the associated targets
    NONE = "none"

    # As NONE, but redirect elements that are capable of it
    REDIRECT = "redirect"

    # Select elements which must be built for the associated targets to be built
    PLAN = "plan"

    # All dependencies of all targets, including the targets
    ALL = "all"

    # All direct build dependencies and their recursive runtime dependencies,
    # excluding the targets
    BUILD = "build"

    # All direct runtime dependencies and their recursive runtime dependencies,
    # including the targets
    RUN = "run"

    def __str__(self):
        return str(self.value)


# _ProjectInformation()
#
# A descriptive object about a project.
#
# Args:
#    project (Project): The project instance
#    provenance (ProvenanceInformation): The provenance information, if any
#    duplicates (list): List of project descriptions which declared this project as a duplicate
#    internal (list): List of project descriptions which declared this project as internal
#
class _ProjectInformation:
    def __init__(self, project, provenance, duplicates, internal):
        self.project = project
        self.provenance = provenance
        self.duplicates = duplicates
        self.internal = internal


########################################
#           Type aliases               #
########################################

# Internal reference for a given Source
SourceRef = Union[None, int, List[Any], Dict[str, Any]]
