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
#        Jim MacArthur <jim.macarthur@codethink.co.uk>
#        Benjamin Schubert <bschubert15@bloomberg.net>

"""
Foundation types
================

"""

from typing import Any, Dict, List, Union, Optional
import os

from .node import MappingNode, SequenceNode
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
    _value_to_entry = {}  # type: Dict[str, Any]

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


class CoreWarnings:
    """CoreWarnings()

    Some common warnings which are raised by core functionalities within BuildStream are found in this class.
    """

    OVERLAPS = "overlaps"
    """
    This warning will be produced when buildstream detects an overlap on an element
        which is not whitelisted. See :ref:`Overlap Whitelist <public_overlap_whitelist>`
    """

    UNSTAGED_FILES = "unstaged-files"
    """
    This warning will be produced when a file cannot be staged. This can happen when
    a file overlaps with a directory in the sandbox that is not empty.
    """

    REF_NOT_IN_TRACK = "ref-not-in-track"
    """
    This warning will be produced when a source is configured with a reference
    which is found to be invalid based on the configured track
    """

    UNALIASED_URL = "unaliased-url"
    """
    A URL used for fetching a sources was specified without specifying any
    :ref:`alias <project_source_aliases>`
    """


class OverlapAction(FastEnum):
    """OverlapAction()

    Defines what action to take when files staged into the sandbox overlap.

    .. note::

       This only dictates what happens when functions such as
       :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>` and
       :func:`Element.stage_dependency_artifacts() <buildstream.element.Element.stage_dependency_artifacts>`
       are called multiple times in an Element's :func:`Element.stage() <buildstream.element.Element.stage>`
       implementation, and the files staged from one function call result in overlapping files staged
       from previous invocations.

       If multiple staged elements overlap eachother within a single call to
       :func:`Element.stage_dependency_artifacts() <buildstream.element.Element.stage_dependency_artifacts>`,
       then the :ref:`overlap whitelist <public_overlap_whitelist>` will be ovserved, and warnings will
       be issued for overlapping files, which will be fatal warnings if
       :attr:`CoreWarnings.OVERLAPS <buildstream.types.CoreWarnings.OVERLAPS>` is specified
       as a :ref:`fatal warning <configurable_warnings>`.
    """

    ERROR = "error"
    """
    It is an error to overlap previously staged files
    """

    WARNING = "warning"
    """
    A warning will be issued for previously staged files, which will fatal if
    :attr:`CoreWarnings.OVERLAPS <buildstream.types.CoreWarnings.OVERLAPS>` is specified
    as a :ref:`fatal warning <configurable_warnings>` in the project.
    """

    IGNORE = "ignore"
    """
    Overlapping files are acceptable, and do not cause any warning or error.
    """


# _Scope():
#
# Defines the scope of dependencies to include for a given element
# when iterating over the dependency graph in APIs like
# Element._dependencies().
#
class _Scope(FastEnum):

    # All elements which the given element depends on, following
    # all elements required for building. Including the element itself.
    #
    ALL = 1

    # All elements required for building the element, including their
    # respective run dependencies. Not including the given element itself.
    #
    BUILD = 2

    # All elements required for running the element. Including the element
    # itself.
    #
    RUN = 3

    # Just the element itself, no dependencies.
    #
    NONE = 4


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


# _DisplayKey():
#
# The components of a cache key which need to be displayed
#
# This is a part of Message() so it needs to be a simple serializable object.
#
# Args:
#    full: A full hex digest cache key for an Element
#    brief: An abbreviated hex digest cache key for an Element
#    strict: Whether the key matches the key which would be used in strict mode
#
class _DisplayKey:
    def __init__(self, full: str, brief: str, strict: bool):
        self.full = full  # type: str
        self.brief = brief  # type: str
        self.strict = strict  # type: bool


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


# _SourceUriPolicy()
#
# A policy for which URIs to access when fetching and tracking
#
class _SourceUriPolicy(FastEnum):

    # Use all URIs from default aliases and mirrors
    ALL = "all"

    # Use only the base source aliases defined in project configuration
    #
    ALIASES = "aliases"

    # Use only URIs from source mirrors (whether they are found
    # in project configuration or user configuration)
    MIRRORS = "mirrors"

    # Use only URIs from user configuration, intentionally causing
    # a failure if we try to access a source for which the user
    # configuration has not provided a mirror
    USER = "user"


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
#    provenance_node (Node): The provenance information, if any
#    duplicates (list): List of project descriptions which declared this project as a duplicate
#    internal (list): List of project descriptions which declared this project as internal
#
class _ProjectInformation:
    def __init__(self, project, provenance_node, duplicates, internal):
        self.project = project
        self.provenance = provenance_node.get_provenance() if provenance_node else None
        self.duplicates = duplicates
        self.internal = internal


# _HostMount()
#
# A simple object describing the behavior of a host mount.
#
class _HostMount:
    def __init__(self, path: str, host_path: Optional[str] = None, optional: bool = False) -> None:

        # Support environment variable expansion in host mounts
        path = os.path.expandvars(path)
        if host_path is None:
            host_path = path
        else:
            host_path = os.path.expandvars(host_path)

        self.path: str = path  # Path inside the sandbox
        self.host_path: str = host_path  # Path on the host
        self.optional: bool = optional  # Optional mounts do not incur warnings or errors


# _SourceMirror()
#
# A simple object describing a source mirror
#
# Args:
#    name: The mirror name
#    aliases: A dictionary of URI lists, keyed by alias names
#
class _SourceMirror:
    def __init__(self, name: str, aliases: Dict[str, List[str]]):
        self.name: str = name
        self.aliases: Dict[str, List[str]] = aliases

    # new_from_node():
    #
    # Creates a _SourceMirror() from a YAML loaded node.
    #
    # Args:
    #    node: The configuration node describing the spec.
    #
    # Returns:
    #    The described _SourceMirror instance.
    #
    # Raises:
    #    LoadError: If the node is malformed.
    #
    @classmethod
    def new_from_node(cls, node: MappingNode) -> "_SourceMirror":
        node.validate_keys(["name", "aliases"])

        name: str = node.get_str("name")
        aliases: Dict[str, List[str]] = {}

        alias_node: MappingNode = node.get_mapping("aliases")

        for alias, uris in alias_node.items():
            assert type(uris) is SequenceNode  # pylint: disable=unidiomatic-typecheck
            aliases[alias] = uris.as_str_list()

        return cls(name, aliases)


########################################
#           Type aliases               #
########################################

# Internal reference for a given Source
SourceRef = Union[None, int, str, List[Any], Dict[str, Any]]
"""
A simple python object used to describe and exact set of sources

This can be ``None`` in order to represent an absense of a source reference,
otherwise it can be ``int``, ``str``, or a complex ``list`` or ``dict`` consisting
of ``int``, ``str``, ``list`` and ``dict`` types.

The order of elements in ``list`` objects is meaningful and should be produced
deterministically by :class:`.Source` implementations, as this order will effect
:ref:`cache keys <cachekeys>`.

See the :ref:`source documentation <core_source_ref>` for more detils on how
:class:`.Source` implementations are expected to handle the source ref.
"""
