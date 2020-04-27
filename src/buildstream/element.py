#
#  Copyright (C) 2016-2018 Codethink Limited
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

"""
Element - Base element class
============================


.. _core_element_abstract_methods:

Abstract Methods
----------------
For loading and configuration purposes, Elements must implement the
:ref:`Plugin base class abstract methods <core_plugin_abstract_methods>`.


.. _core_element_build_phase:

Build Phase
~~~~~~~~~~~
The following methods are the foundation of the element's *build
phase*, they must be implemented by all Element classes, unless
explicitly stated otherwise.

* :func:`Element.configure_sandbox() <buildstream.element.Element.configure_sandbox>`

  Configures the :class:`.Sandbox`. This is called before anything else

* :func:`Element.stage() <buildstream.element.Element.stage>`

  Stage dependencies and :class:`Sources <buildstream.source.Source>` into
  the sandbox.

* :func:`Element.prepare() <buildstream.element.Element.prepare>`

  Call preparation methods that should only be performed once in the
  lifetime of a build directory (e.g. autotools' ./configure).

  **Optional**: If left unimplemented, this step will be skipped.

* :func:`Element.assemble() <buildstream.element.Element.assemble>`

  Perform the actual assembly of the element


Miscellaneous
~~~~~~~~~~~~~
Miscellaneous abstract methods also exist:

* :func:`Element.generate_script() <buildstream.element.Element.generate_script>`

  For the purpose of ``bst source checkout --include-build-scripts``, an Element may optionally implement this.


Class Reference
---------------
"""

import os
import re
import stat
import copy
from collections import OrderedDict
import contextlib
from contextlib import contextmanager
from functools import partial
from itertools import chain
import string
from typing import cast, TYPE_CHECKING, Any, Dict, Iterator, List, Optional

from pyroaring import BitMap  # pylint: disable=no-name-in-module

from . import _yaml
from ._variables import Variables
from ._versions import BST_CORE_ARTIFACT_VERSION
from ._exceptions import BstError, LoadError, ImplError, SourceCacheError
from .exceptions import ErrorDomain, LoadErrorReason
from .utils import FileListResult, BST_ARBITRARY_TIMESTAMP
from . import utils
from . import _cachekey
from . import _site
from ._platform import Platform
from .node import Node
from .plugin import Plugin
from .sandbox import SandboxFlags, SandboxCommandError
from .sandbox._config import SandboxConfig
from .sandbox._sandboxremote import SandboxRemote
from .types import CoreWarnings, Scope, _CacheBuildTrees, _KeyStrength
from ._artifact import Artifact

from .storage.directory import Directory
from .storage._filebaseddirectory import FileBasedDirectory
from .storage._casbaseddirectory import CasBasedDirectory
from .storage.directory import VirtualDirectoryError

if TYPE_CHECKING:
    from .node import MappingNode, ScalarNode, SequenceNode
    from .types import SourceRef
    from typing import Set, Tuple

    # pylint: disable=cyclic-import
    from .sandbox import Sandbox
    from .source import Source
    from ._context import Context
    from ._loader.metaelement import MetaElement
    from ._project import Project

    # pylint: enable=cyclic-import


class ElementError(BstError):
    """This exception should be raised by :class:`.Element` implementations
    to report errors to the user.

    Args:
       message: The error message to report to the user
       detail: A possibly multiline, more detailed error message
       reason: An optional machine readable reason string, used for test cases
       collect: An optional directory containing partial install contents
       temporary: An indicator to whether the error may occur if the operation was run again.
    """

    def __init__(
        self, message: str, *, detail: str = None, reason: str = None, collect: str = None, temporary: bool = False
    ):
        super().__init__(message, detail=detail, domain=ErrorDomain.ELEMENT, reason=reason, temporary=temporary)

        self.collect = collect


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """

    # The defaults from the yaml file and project
    __defaults = None
    # A hash of Element by MetaElement
    __instantiated_elements = {}  # type: Dict[MetaElement, Element]
    # A list of (source, ref) tuples which were redundantly specified
    __redundant_source_refs = []  # type: List[Tuple[Source, SourceRef]]

    BST_ARTIFACT_VERSION = 0
    """The element plugin's artifact version

    Elements must first set this to 1 if they change their unique key
    structure in a way that would produce a different key for the
    same input, or introduce a change in the build output for the
    same unique key. Further changes of this nature require bumping the
    artifact version.
    """

    BST_STRICT_REBUILD = False
    """Whether to rebuild this element in non strict mode if
    any of the dependencies have changed.
    """

    BST_FORBID_RDEPENDS = False
    """Whether to raise exceptions if an element has runtime dependencies.
    """

    BST_FORBID_BDEPENDS = False
    """Whether to raise exceptions if an element has build dependencies.
    """

    BST_FORBID_SOURCES = False
    """Whether to raise exceptions if an element has sources.
    """

    BST_VIRTUAL_DIRECTORY = False
    """Whether to raise exceptions if an element uses Sandbox.get_directory
    instead of Sandbox.get_virtual_directory.
    """

    BST_RUN_COMMANDS = True
    """Whether the element may run commands using Sandbox.run.
    """

    BST_ELEMENT_HAS_ARTIFACT = True
    """Whether the element produces an artifact when built.
    """

    def __init__(self, context: "Context", project: "Project", meta: "MetaElement", plugin_conf: Dict[str, Any]):

        self.__cache_key_dict = None  # Dict for cache key calculation
        self.__cache_key = None  # Our cached cache key

        super().__init__(meta.name, context, project, meta.provenance, "element")

        # Ensure the project is fully loaded here rather than later on
        if not meta.is_junction:
            project.ensure_fully_loaded()

        self.project_name = self._get_project().name
        self.normal_name = _get_normal_name(self.name)
        """A normalized element name

        This is the original element without path separators or
        the extension, it's used mainly for composing log file names
        and creating directory names and such.
        """

        # Direct runtime dependency Elements
        self.__runtime_dependencies = []  # type: List[Element]
        # Direct build dependency Elements
        self.__build_dependencies = []  # type: List[Element]
        # Direct build dependency subset which require strict rebuilds
        self.__strict_dependencies = []  # type: List[Element]
        # Direct reverse build dependency Elements
        self.__reverse_build_deps = set()  # type: Set[Element]
        # Direct reverse runtime dependency Elements
        self.__reverse_runtime_deps = set()  # type: Set[Element]
        self.__build_deps_without_strict_cache_key = None  # Number of build dependencies without a strict key
        self.__runtime_deps_without_strict_cache_key = None  # Number of runtime dependencies without a strict key
        self.__build_deps_without_cache_key = None  # Number of build dependencies without a cache key
        self.__runtime_deps_without_cache_key = None  # Number of runtime dependencies without a cache key
        self.__build_deps_uncached = None  # Build dependencies which are not yet cached
        self.__runtime_deps_uncached = None  # Runtime dependencies which are not yet cached
        self.__updated_strict_cache_keys_of_rdeps = False  # Whether we've updated strict cache keys of rdeps
        self.__ready_for_runtime = False  # Whether the element and its runtime dependencies have cache keys
        self.__ready_for_runtime_and_cached = False  # Whether all runtime deps are cached, as well as the element
        self.__cached_remotely = None  # Whether the element is cached remotely
        # List of Sources
        self.__sources = []  # type: List[Source]
        self.__sources_vdir = None  # Directory with staged sources
        self.__weak_cache_key = None  # Our cached weak cache key
        self.__strict_cache_key = None  # Our cached cache key for strict builds
        self.__artifacts = context.artifactcache  # Artifact cache
        self.__sourcecache = context.sourcecache  # Source cache
        self.__is_resolved = False  # Whether the source is fully resolved or not
        self.__assemble_scheduled = False  # Element is scheduled to be assembled
        self.__assemble_done = False  # Element is assembled
        self.__pull_done = False  # Whether pull was attempted
        self.__cached_successfully = None  # If the Element is known to be successfully cached
        self.__has_all_sources_in_source_cache = None  # If the sources are known to be successfully cached
        self.__has_all_sources_cached = False  # Whether all sources have a local copy of their respective sources
        self.__splits = None  # Resolved regex objects for computing split domains
        self.__whitelist_regex = None  # Resolved regex object to check if file is allowed to overlap
        self.__tainted = None  # Whether the artifact is tainted and should not be shared
        self.__artifact_files_required = False  # Whether artifact files are required in the local cache
        self.__build_result = None  # The result of assembling this Element (success, description, detail)
        self._build_log_path = None  # The path of the build log for this Element
        # Artifact class for direct artifact composite interaction
        self.__artifact = None  # type: Optional[Artifact]
        self.__strict_artifact = None  # Artifact for strict cache key
        self.__meta_kind = meta.kind  # The kind of this source, required for unpickling

        # the index of the last source in this element that requires previous
        # sources for staging
        self.__last_source_requires_previous_ix = None

        self.__batch_prepare_assemble = False  # Whether batching across prepare()/assemble() is configured
        self.__batch_prepare_assemble_flags = 0  # Sandbox flags for batching across prepare()/assemble()
        # Collect dir for batching across prepare()/assemble()
        self.__batch_prepare_assemble_collect = None  # type: Optional[str]

        # Callbacks
        self.__can_query_cache_callback = None  # Callback to PullQueue/FetchQueue
        self.__buildable_callback = None  # Callback to BuildQueue

        self._depth = None  # Depth of Element in its current dependency graph
        self._resolved_initial_state = False  # Whether the initial state of the Element has been resolved

        # Ensure we have loaded this class's defaults
        self.__init_defaults(project, plugin_conf, meta.kind, meta.is_junction)

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(project, meta)
        variables["element-name"] = self.name
        self.__variables = Variables(variables)

        # Collect the composited environment now that we have variables
        unexpanded_env = self.__extract_environment(project, meta)
        self.__environment = self.__expand_environment(unexpanded_env)

        # Collect the environment nocache blacklist list
        nocache = self.__extract_env_nocache(project, meta)
        self.__env_nocache = nocache

        # Grab public domain data declared for this instance
        unexpanded_public = self.__extract_public(meta)
        self.__public = self.__expand_splits(unexpanded_public)
        self.__dynamic_public = None

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__config = self.__extract_config(meta)
        self._configure(self.__config)

        # Extract remote execution URL
        if meta.is_junction:
            self.__remote_execution_specs = None
        else:
            self.__remote_execution_specs = project.remote_execution_specs

        # Extract Sandbox config
        self.__sandbox_config = self.__extract_sandbox_config(context, project, meta)

    def __lt__(self, other):
        return self.name < other.name

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def configure_sandbox(self, sandbox: "Sandbox") -> None:
        """Configures the the sandbox for execution

        Args:
           sandbox: The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to configure the sandbox object
        for execution.
        """
        raise ImplError("element plugin '{kind}' does not implement configure_sandbox()".format(kind=self.get_kind()))

    def stage(self, sandbox: "Sandbox") -> None:
        """Stage inputs into the sandbox directories

        Args:
           sandbox: The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to populate the sandbox
        directory with data. This is done either by staging :class:`.Source`
        objects, by staging the artifacts of the elements this element depends
        on, or both.
        """
        raise ImplError("element plugin '{kind}' does not implement stage()".format(kind=self.get_kind()))

    def prepare(self, sandbox: "Sandbox") -> None:
        """Run one-off preparation commands.

        This is run before assemble(), but is guaranteed to run only
        the first time if we build incrementally - this makes it
        possible to run configure-like commands without causing the
        entire element to rebuild.

        Args:
           sandbox: The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        By default, this method does nothing, but may be overriden to
        allow configure-like commands.
        """

    def assemble(self, sandbox: "Sandbox") -> str:
        """Assemble the output artifact

        Args:
           sandbox: The build sandbox

        Returns:
           An absolute path within the sandbox to collect the artifact from

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to create an output
        artifact from its sources and dependencies.
        """
        raise ImplError("element plugin '{kind}' does not implement assemble()".format(kind=self.get_kind()))

    def generate_script(self) -> str:
        """Generate a build (sh) script to build this element

        Returns:
           A string containing the shell commands required to build the element

        BuildStream guarantees the following environment when the
        generated script is run:

        - All element variables have been exported.
        - The cwd is `self.get_variable('build-root')/self.normal_name`.
        - $PREFIX is set to `self.get_variable('install-root')`.
        - The directory indicated by $PREFIX is an empty directory.

        Files are expected to be installed to $PREFIX.

        If the script fails, it is expected to return with an exit
        code != 0.
        """
        raise ImplError("element plugin '{kind}' does not implement write_script()".format(kind=self.get_kind()))

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def sources(self) -> Iterator["Source"]:
        """A generator function to enumerate the element sources

        Yields:
           The sources of this element
        """
        for source in self.__sources:
            yield source

    def dependencies(self, scope: Scope, *, recurse: bool = True, visited=None) -> Iterator["Element"]:
        """dependencies(scope, *, recurse=True)

        A generator function which yields the dependencies of the given element.

        If `recurse` is specified (the default), the full dependencies will be listed
        in deterministic staging order, starting with the basemost elements in the
        given `scope`. Otherwise, if `recurse` is not specified then only the direct
        dependencies in the given `scope` will be traversed, and the element itself
        will be omitted.

        Args:
           scope: The scope to iterate in
           recurse: Whether to recurse

        Yields:
           The dependencies in `scope`, in deterministic staging order
        """
        # The format of visited is (BitMap(), BitMap()), with the first BitMap
        # containing element that have been visited for the `Scope.BUILD` case
        # and the second one relating to the `Scope.RUN` case.
        if not recurse:
            if scope in (Scope.BUILD, Scope.ALL):
                yield from self.__build_dependencies
            if scope in (Scope.RUN, Scope.ALL):
                yield from self.__runtime_dependencies
        else:

            def visit(element, scope, visited):
                if scope == Scope.ALL:
                    visited[0].add(element._unique_id)
                    visited[1].add(element._unique_id)

                    for dep in chain(element.__build_dependencies, element.__runtime_dependencies):
                        if dep._unique_id not in visited[0] and dep._unique_id not in visited[1]:
                            yield from visit(dep, Scope.ALL, visited)

                    yield element
                elif scope == Scope.BUILD:
                    visited[0].add(element._unique_id)

                    for dep in element.__build_dependencies:
                        if dep._unique_id not in visited[1]:
                            yield from visit(dep, Scope.RUN, visited)

                elif scope == Scope.RUN:
                    visited[1].add(element._unique_id)

                    for dep in element.__runtime_dependencies:
                        if dep._unique_id not in visited[1]:
                            yield from visit(dep, Scope.RUN, visited)

                    yield element
                else:
                    yield element

            if visited is None:
                # Visited is of the form (Visited for Scope.BUILD, Visited for Scope.RUN)
                visited = (BitMap(), BitMap())
            else:
                # We have already a visited set passed. we might be able to short-circuit
                if scope in (Scope.BUILD, Scope.ALL) and self._unique_id in visited[0]:
                    return
                if scope in (Scope.RUN, Scope.ALL) and self._unique_id in visited[1]:
                    return

            yield from visit(self, scope, visited)

    def search(self, scope: Scope, name: str) -> Optional["Element"]:
        """Search for a dependency by name

        Args:
           scope: The scope to search
           name: The dependency to search for

        Returns:
           The dependency element, or None if not found.
        """
        for dep in self.dependencies(scope):
            if dep.name == name:
                return dep

        return None

    def node_subst_vars(self, node: "ScalarNode") -> str:
        """Replace any variables in the string contained in the node and returns it.

        Args:
           node: A ScalarNode loaded from YAML

        Returns:
           The value with all variables replaced

        Raises:
           :class:`.LoadError`: When the node doesn't contain a string or a variable was not found.

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node', substituting any
          # variables in the returned string
          name = self.node_subst_vars(node.get_str('name'))
        """
        try:
            return self.__variables.subst(node.as_str())
        except LoadError as e:
            provenance = node.get_provenance()
            raise LoadError("{}: {}".format(provenance, e), e.reason, detail=e.detail) from e

    def node_subst_sequence_vars(self, node: "SequenceNode[ScalarNode]") -> List[str]:
        """Substitute any variables in the given sequence

        Args:
          node: A SequenceNode loaded from YAML

        Returns:
          The list with every variable replaced

        Raises:
          :class:`.LoadError`

        """
        ret = []
        for value in node:
            try:
                ret.append(self.__variables.subst(value.as_str()))
            except LoadError as e:
                provenance = value.get_provenance()
                raise LoadError("{}: {}".format(provenance, e), e.reason, detail=e.detail) from e
        return ret

    def compute_manifest(
        self, *, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None, orphans: bool = True
    ) -> str:
        """Compute and return this element's selective manifest

        The manifest consists on the list of file paths in the
        artifact. The files in the manifest are selected according to
        `include`, `exclude` and `orphans` parameters. If `include` is
        not specified then all files spoken for by any domain are
        included unless explicitly excluded with an `exclude` domain.

        Args:
           include: An optional list of domains to include files from
           exclude: An optional list of domains to exclude files from
           orphans: Whether to include files not spoken for by split domains

        Yields:
           The paths of the files in manifest
        """
        self.__assert_cached()
        return self.__compute_splits(include, exclude, orphans)

    def get_artifact_name(self, key: Optional[str] = None) -> str:
        """Compute and return this element's full artifact name

        Generate a full name for an artifact, including the project
        namespace, element name and cache key.

        This can also be used as a relative path safely, and
        will normalize parts of the element name such that only
        digits, letters and some select characters are allowed.

        Args:
           key: The element's cache key. Defaults to None

        Returns:
           The relative path for the artifact
        """
        if key is None:
            key = self._get_cache_key()

        assert key is not None

        return _compose_artifact_name(self.project_name, self.normal_name, key)

    def stage_artifact(
        self,
        sandbox: "Sandbox",
        *,
        path: str = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> FileListResult:
        """Stage this element's output artifact in the sandbox

        This will stage the files from the artifact to the sandbox at specified location.
        The files are selected for staging according to the `include`, `exclude` and `orphans`
        parameters; if `include` is not specified then all files spoken for by any domain
        are included unless explicitly excluded with an `exclude` domain.

        Args:
           sandbox: The build sandbox
           path: An optional sandbox relative path
           include: An optional list of domains to include files from
           exclude: An optional list of domains to exclude files from
           orphans: Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): If the element has not yet produced an artifact.

        Returns:
           The result describing what happened while staging

        .. note::

           Directories in `dest` are replaced with files from `src`,
           unless the existing directory in `dest` is not empty in
           which case the path will be reported in the return value.

        **Example:**

        .. code:: python

          # Stage the dependencies for a build of 'self'
          for dep in self.dependencies(Scope.BUILD):
              dep.stage_artifact(sandbox)
        """

        if not self._cached():
            detail = (
                "No artifacts have been cached yet for that element\n"
                + "Try building the element first with `bst build`\n"
            )
            raise ElementError("No artifacts to stage", detail=detail, reason="uncached-checkout-attempt")

        # Time to use the artifact, check once more that it's there
        self.__assert_cached()

        with self.timed_activity("Staging {}/{}".format(self.name, self._get_brief_display_key())):
            # Disable type checking since we can't easily tell mypy that
            # `self.__artifact` can't be None at this stage.
            files_vdir = self.__artifact.get_files()  # type: ignore

            # Hard link it into the staging area
            #
            vbasedir = sandbox.get_virtual_directory()
            vstagedir = vbasedir if path is None else vbasedir.descend(*path.lstrip(os.sep).split(os.sep), create=True)

            split_filter = self.__split_filter_func(include, exclude, orphans)

            result = vstagedir.import_files(
                files_vdir, filter_callback=split_filter, report_written=True, can_link=True
            )

            return result

    def stage_dependency_artifacts(
        self,
        sandbox: "Sandbox",
        scope: Scope,
        *,
        path: str = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> None:
        """Stage element dependencies in scope

        This is primarily a convenience wrapper around
        :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>`
        which takes care of staging all the dependencies in `scope` and issueing the
        appropriate warnings.

        Args:
           sandbox: The build sandbox
           scope: The scope to stage dependencies in
           path An optional sandbox relative path
           include: An optional list of domains to include files from
           exclude: An optional list of domains to exclude files from
           orphans: Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): If any of the dependencies in `scope` have not
                                     yet produced artifacts, or if forbidden overlaps
                                     occur.
        """
        ignored = {}
        overlaps = OrderedDict()  # type: OrderedDict[str, List[str]]
        files_written = {}  # type: Dict[str, List[str]]

        for dep in self.dependencies(scope):
            result = dep.stage_artifact(sandbox, path=path, include=include, exclude=exclude, orphans=orphans)
            if result.overwritten:
                for overwrite in result.overwritten:
                    # Completely new overwrite
                    if overwrite not in overlaps:
                        # Find the overwritten element by checking where we've
                        # written the element before
                        for elm, contents in files_written.items():
                            if overwrite in contents:
                                overlaps[overwrite] = [elm, dep.name]
                    else:
                        overlaps[overwrite].append(dep.name)
            files_written[dep.name] = result.files_written

            if result.ignored:
                ignored[dep.name] = result.ignored

        if overlaps:
            overlap_warning = False
            warning_detail = "Staged files overwrite existing files in staging area:\n"
            for f, elements in overlaps.items():
                overlap_warning_elements = []
                # The bottom item overlaps nothing
                overlapping_elements = elements[1:]
                for elm in overlapping_elements:
                    element = cast(Element, self.search(scope, elm))
                    if not element.__file_is_whitelisted(f):
                        overlap_warning_elements.append(elm)
                        overlap_warning = True

                warning_detail += _overlap_error_detail(f, overlap_warning_elements, elements)

            if overlap_warning:
                self.warn(
                    "Non-whitelisted overlaps detected", detail=warning_detail, warning_token=CoreWarnings.OVERLAPS
                )

        if ignored:
            detail = "Not staging files which would replace non-empty directories:\n"
            for key, value in ignored.items():
                detail += "\nFrom {}:\n".format(key)
                detail += "  " + "  ".join(["/" + f + "\n" for f in value])
            self.warn("Ignored files", detail=detail)

    def integrate(self, sandbox: "Sandbox") -> None:
        """Integrate currently staged filesystem against this artifact.

        Args:
           sandbox: The build sandbox

        This modifies the sysroot staged inside the sandbox so that
        the sysroot is *integrated*. Only an *integrated* sandbox
        may be trusted for running the software therein, as the integration
        commands will create and update important system cache files
        required for running the installed software (such as the ld.so.cache).
        """
        bstdata = self.get_public_data("bst")
        environment = self.get_environment()

        if bstdata is not None:
            with sandbox.batch(SandboxFlags.NONE):
                commands = bstdata.get_sequence("integration-commands", [])
                for command in commands:
                    cmd = self.node_subst_vars(command)

                    sandbox.run(["sh", "-e", "-c", cmd], 0, env=environment, cwd="/", label=cmd)

    def stage_sources(self, sandbox: "Sandbox", directory: str) -> None:
        """Stage this element's sources to a directory in the sandbox

        Args:
           sandbox: The build sandbox
           directory: An absolute path within the sandbox to stage the sources at
        """
        self._stage_sources_in_sandbox(sandbox, directory)

    def get_public_data(self, domain: str) -> "MappingNode[Any, Any]":
        """Fetch public data on this element

        Args:
           domain: A public domain name to fetch data for

        Returns:

        .. note::

           This can only be called the abstract methods which are
           called as a part of the :ref:`build phase <core_element_build_phase>`
           and never before.
        """
        if self.__dynamic_public is None:
            self.__load_public_data()

        # Disable type-checking since we can't easily tell mypy that
        # `self.__dynamic_public` can't be None here.
        data = self.__dynamic_public.get_mapping(domain, default=None)  # type: ignore
        if data is not None:
            data = data.clone()

        return data

    def set_public_data(self, domain: str, data: "MappingNode[Any, Any]") -> None:
        """Set public data on this element

        Args:
           domain: A public domain name to fetch data for
           data: The public data dictionary for the given domain

        This allows an element to dynamically mutate public data of
        elements or add new domains as the result of success completion
        of the :func:`Element.assemble() <buildstream.element.Element.assemble>`
        method.
        """
        if self.__dynamic_public is None:
            self.__load_public_data()

        if data is not None:
            data = data.clone()

        self.__dynamic_public[domain] = data  # type: ignore

    def get_environment(self) -> Dict[str, str]:
        """Fetch the environment suitable for running in the sandbox

        Returns:
           A dictionary of string key/values suitable for passing
           to :func:`Sandbox.run() <buildstream.sandbox.Sandbox.run>`
        """
        return self.__environment

    def get_variable(self, varname: str) -> Optional[str]:
        """Fetch the value of a variable resolved for this element.

        Args:
           varname: The name of the variable to fetch

        Returns:
           The resolved value for *varname*, or None if no
           variable was declared with the given name.
        """
        # Flat is not recognized correctly by Pylint as being a dictionary
        return self.__variables.flat.get(varname)  # pylint: disable=no-member

    def batch_prepare_assemble(self, flags: int, *, collect: Optional[str] = None) -> None:
        """ Configure command batching across prepare() and assemble()

        Args:
           flags: The sandbox flags for the command batch
           collect: An optional directory containing partial install contents
                    on command failure.

        This may be called in :func:`Element.configure_sandbox() <buildstream.element.Element.configure_sandbox>`
        to enable batching of all sandbox commands issued in prepare() and assemble().
        """
        if self.__batch_prepare_assemble:
            raise ElementError("{}: Command batching for prepare/assemble is already configured".format(self))

        self.__batch_prepare_assemble = True
        self.__batch_prepare_assemble_flags = flags
        self.__batch_prepare_assemble_collect = collect

    def get_logs(self) -> List[str]:
        """Obtain a list of log file paths

        Returns:
           A list of log file paths
        """
        return cast(Artifact, self.__artifact).get_logs()

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _new_from_meta():
    #
    # Recursively instantiate a new Element instance, its sources
    # and its dependencies from a meta element.
    #
    # Args:
    #    meta (MetaElement): The meta element
    #    task (Task): A task object to report progress to
    #
    # Returns:
    #    (Element): A newly created Element instance
    #
    @classmethod
    def _new_from_meta(cls, meta, task=None):

        if not meta.first_pass:
            meta.project.ensure_fully_loaded()

        if meta in cls.__instantiated_elements:
            return cls.__instantiated_elements[meta]

        element = meta.project.create_element(meta, first_pass=meta.first_pass)
        cls.__instantiated_elements[meta] = element

        # Instantiate sources and generate their keys
        for meta_source in meta.sources:
            meta_source.first_pass = meta.is_junction
            source = meta.project.create_source(meta_source, first_pass=meta.first_pass)

            redundant_ref = source._load_ref()

            element.__sources.append(source)

            # Collect redundant refs which occurred at load time
            if redundant_ref is not None:
                cls.__redundant_source_refs.append((source, redundant_ref))

        # Instantiate dependencies
        for meta_dep in meta.dependencies:
            dependency = Element._new_from_meta(meta_dep, task)
            element.__runtime_dependencies.append(dependency)
            dependency.__reverse_runtime_deps.add(element)
        no_of_runtime_deps = len(element.__runtime_dependencies)
        element.__runtime_deps_without_strict_cache_key = no_of_runtime_deps
        element.__runtime_deps_without_cache_key = no_of_runtime_deps
        element.__runtime_deps_uncached = no_of_runtime_deps

        for meta_dep in meta.build_dependencies:
            dependency = Element._new_from_meta(meta_dep, task)
            element.__build_dependencies.append(dependency)
            dependency.__reverse_build_deps.add(element)

            if meta_dep in meta.strict_dependencies:
                element.__strict_dependencies.append(dependency)

        no_of_build_deps = len(element.__build_dependencies)
        element.__build_deps_without_strict_cache_key = no_of_build_deps
        element.__build_deps_without_cache_key = no_of_build_deps
        element.__build_deps_uncached = no_of_build_deps

        element.__preflight()

        if task:
            task.add_current_progress()

        return element

    # _clear_meta_elements_cache()
    #
    # Clear the internal meta elements cache.
    #
    # When loading elements from meta, we cache already instantiated elements
    # in order to not have to load the same elements twice.
    # This clears the cache.
    #
    # It should be called whenever we are done loading all elements in order
    # to save memory.
    #
    @classmethod
    def _clear_meta_elements_cache(cls):
        cls.__instantiated_elements = {}

    # _get_redundant_source_refs()
    #
    # Fetches a list of (Source, ref) tuples of all the Sources
    # which were loaded with a ref specified in the element declaration
    # for projects which use project.refs ref-storage.
    #
    # This is used to produce a warning
    @classmethod
    def _get_redundant_source_refs(cls):
        return cls.__redundant_source_refs

    # _reset_load_state()
    #
    # This is called by Pipeline.cleanup() and is used to
    # reset the loader state between multiple sessions.
    #
    @classmethod
    def _reset_load_state(cls):
        cls.__instantiated_elements = {}
        cls.__redundant_source_refs = []

    # _cached():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache
    #
    def _cached(self):
        if not self.__artifact:
            return False

        return self.__artifact.cached()

    # _cached_remotely():
    #
    # Returns:
    #    (bool): Whether this element is present in a remote cache
    #
    def _cached_remotely(self):
        if self.__cached_remotely is None:
            self.__cached_remotely = self.__artifacts.check_remotes_for_element(self)
        return self.__cached_remotely

    # _get_build_result():
    #
    # Returns:
    #    (bool): Whether the artifact of this element present in the artifact cache is of a success
    #    (str): Short description of the result
    #    (str): Detailed description of the result
    #
    def _get_build_result(self):
        if self.__build_result is None:
            self.__load_build_result()

        return self.__build_result

    # __set_build_result():
    #
    # Sets the assembly result
    #
    # Args:
    #    success (bool): Whether the result is a success
    #    description (str): Short description of the result
    #    detail (str): Detailed description of the result
    #
    def __set_build_result(self, success, description, detail=None):
        self.__build_result = (success, description, detail)

    # _cached_success():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache and the element assembled successfully
    #
    def _cached_success(self):
        # FIXME:  _cache() and _cached_success() should be converted to
        # push based functions where we only update __cached_successfully
        # once we know this has changed. This will allow us to cheaply check
        # __cached_successfully instead of calling _cached_success()
        if self.__cached_successfully:
            return True

        if not self._cached():
            return False

        success, _, _ = self._get_build_result()
        if success:
            self.__cached_successfully = True
            return True
        else:
            return False

    # _cached_failure():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache and the element did not assemble successfully
    #
    def _cached_failure(self):
        if not self._cached():
            return False

        success, _, _ = self._get_build_result()
        return not success

    # _buildable():
    #
    # Returns:
    #    (bool): Whether this element can currently be built
    #
    def _buildable(self):
        if not (self._has_all_sources_in_source_cache() or self._has_all_sources_cached()):
            return False

        if not self.__assemble_scheduled:
            return False

        return self.__build_deps_uncached == 0

    # _get_cache_key():
    #
    # Returns the cache key
    #
    # Args:
    #    strength (_KeyStrength): Either STRONG or WEAK key strength
    #
    # Returns:
    #    (str): A hex digest cache key for this Element, or None
    #
    # None is returned if information for the cache key is missing.
    #
    def _get_cache_key(self, strength=_KeyStrength.STRONG):
        if strength == _KeyStrength.STRONG:
            return self.__cache_key
        else:
            return self.__weak_cache_key

    # _can_query_cache():
    #
    # Returns whether the cache key required for cache queries is available.
    #
    # Returns:
    #    (bool): True if cache can be queried
    #
    def _can_query_cache(self):
        # cache cannot be queried until strict cache key is available
        return self.__strict_cache_key is not None

    # _initialize_state()
    #
    # Compute up the elment's initial state. Element state contains
    # the following mutable sub-states:
    #
    # - Source state
    # - Artifact cache key
    #   - Source key
    #     - Integral component of the cache key
    #     - Computed as part of the source state
    # - Artifact state
    #   - Cache key
    #     - Must be known to compute this state
    # - Build status
    #   - Artifact state
    #     - Must be known before we can decide whether to build
    #
    # Note that sub-states are dependent on each other, and changes to
    # one state will effect changes in the next.
    #
    # Changes to these states can be caused by numerous things,
    # notably jobs executed in sub-processes. Changes are performed by
    # invocations of the following methods:
    #
    # - __update_resolved_state()
    #   - Computes the state of all sources of the element.
    # - __update_cache_keys()
    #   - Computes the strong and weak cache keys.
    # - _update_artifact_state()
    #   - Computes the state of the element's artifact using the
    #     cache key.
    # - _schedule_assembly_when_necessary()
    #   - Schedules assembly of an element, iff its current state
    #     allows/necessitates it
    # - __update_cache_key_non_strict()
    #   - Sets strict cache keys in non-strict builds
    #     - Some non-strict build actions can create artifacts
    #       compatible with strict mode (such as pulling), so
    #       this needs to be done
    #
    # When any one of these methods are called and cause a change,
    # they will invoke methods that have a potential dependency on
    # them, causing the state change to bubble through all potential
    # side effects.
    #
    # *This* method starts the process by invoking
    # `__update_resolved_state()`, which will cause all necessary state
    # changes. Other functions should use the appropriate methods and
    # only update what they expect to change - this will ensure that
    # the minimum amount of work is done.
    #
    def _initialize_state(self):
        assert not self._resolved_initial_state, "_initialize_state() should only be called once"
        self._resolved_initial_state = True

        # This will update source state, and for un-initialized
        # elements recursively initialize anything else (because it
        # will become considered outdated after source state is
        # updated).
        #
        # FIXME: Currently this method may cause recursion through
        # `self.__update_strict_cache_key_of_rdeps()`, since this may
        # invoke reverse dependencies' cache key updates
        # recursively. This is necessary when we update keys after a
        # pull/build, however should not occur during initialization
        # (since we will eventualyl visit reverse dependencies during
        # our initialization anyway).
        self.__update_resolved_state()

    # _get_display_key():
    #
    # Returns cache keys for display purposes
    #
    # Returns:
    #    (str): A full hex digest cache key for this Element
    #    (str): An abbreviated hex digest cache key for this Element
    #    (bool): True if key should be shown as dim, False otherwise
    #
    # Question marks are returned if information for the cache key is missing.
    #
    def _get_display_key(self):
        context = self._get_context()
        dim_key = True

        cache_key = self._get_cache_key()

        if not cache_key:
            cache_key = "{:?<64}".format("")
        elif cache_key == self.__strict_cache_key:
            # Strong cache key used in this session matches cache key
            # that would be used in strict build mode
            dim_key = False

        length = min(len(cache_key), context.log_key_length)
        return (cache_key, cache_key[0:length], dim_key)

    # _get_brief_display_key()
    #
    # Returns an abbreviated cache key for display purposes
    #
    # Returns:
    #    (str): An abbreviated hex digest cache key for this Element
    #
    # Question marks are returned if information for the cache key is missing.
    #
    def _get_brief_display_key(self):
        _, display_key, _ = self._get_display_key()
        return display_key

    # _tracking_done():
    #
    # This is called in the main process after the element has been tracked
    #
    def _tracking_done(self):
        # Tracking may change the sources' refs, and therefore the
        # source state. We need to update source state.
        self.__update_resolved_state()

        # Check whether sources are now cached.
        # This is done here so that we don't throw an exception trying to show the pipeline at the end
        # This has for side-effect to cache this fact too, which will change the object's state.
        # This is done here rather than later so we can validate that the sources are valid locally
        self._has_all_sources_in_source_cache()
        self._has_all_sources_cached()

    # _track():
    #
    # Calls track() on the Element sources
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    # Returns:
    #    (list): A list of Source object ids and their new references
    #
    def _track(self):
        refs = []
        for index, source in enumerate(self.__sources):
            old_ref = source.get_ref()
            new_ref = source._track(self.__sources[0:index])
            refs.append((source._unique_id, new_ref))

            # Complimentary warning that the new ref will be unused.
            if old_ref != new_ref and self._get_workspace():
                detail = (
                    "This source has an open workspace.\n"
                    + "To start using the new reference, please close the existing workspace."
                )
                source.warn("Updated reference will be ignored as source has open workspace", detail=detail)

        return refs

    # _prepare_sandbox():
    #
    # This stages things for either _shell() (below) or also
    # is used to stage things by the `bst artifact checkout` codepath
    #
    @contextmanager
    def _prepare_sandbox(self, scope, shell=False, integrate=True, usebuildtree=False):
        # bst shell and bst artifact checkout require a local sandbox.
        with self.__sandbox(None, config=self.__sandbox_config, allow_remote=False) as sandbox:
            sandbox._usebuildtree = usebuildtree

            # Configure always comes first, and we need it.
            self.__configure_sandbox(sandbox)

            # Stage what we need
            if shell and scope == Scope.BUILD:
                self.stage(sandbox)
            else:
                # Stage deps in the sandbox root
                with self.timed_activity("Staging dependencies", silent_nested=True):
                    self.stage_dependency_artifacts(sandbox, scope)

                # Run any integration commands provided by the dependencies
                # once they are all staged and ready
                if integrate:
                    with self.timed_activity("Integrating sandbox"):
                        for dep in self.dependencies(scope):
                            dep.integrate(sandbox)

            yield sandbox

    # _stage_sources_in_sandbox():
    #
    # Stage this element's sources to a directory inside sandbox
    #
    # Args:
    #     sandbox (:class:`.Sandbox`): The build sandbox
    #     directory (str): An absolute path to stage the sources at
    #
    def _stage_sources_in_sandbox(self, sandbox, directory):

        # Stage all sources that need to be copied
        sandbox_vroot = sandbox.get_virtual_directory()
        host_vdirectory = sandbox_vroot.descend(*directory.lstrip(os.sep).split(os.sep), create=True)
        self._stage_sources_at(host_vdirectory, usebuildtree=sandbox._usebuildtree)

    # _stage_sources_at():
    #
    # Stage this element's sources to a directory
    #
    # Args:
    #     vdirectory (:class:`.storage.Directory`): A virtual directory object to stage sources into.
    #     usebuildtree (bool): use a the elements build tree as its source.
    #
    def _stage_sources_at(self, vdirectory, usebuildtree=False):

        context = self._get_context()

        # It's advantageous to have this temporary directory on
        # the same file system as the rest of our cache.
        with self.timed_activity("Staging sources", silent_nested=True), utils._tempdir(
            dir=context.tmpdir, prefix="staging-temp"
        ) as temp_staging_directory:

            import_dir = temp_staging_directory

            if not isinstance(vdirectory, Directory):
                vdirectory = FileBasedDirectory(vdirectory)
            if not vdirectory.is_empty():
                raise ElementError("Staging directory '{}' is not empty".format(vdirectory))

            # Check if we have a cached buildtree to use
            if usebuildtree:
                import_dir = self.__artifact.get_buildtree()
                if import_dir.is_empty():
                    detail = "Element type either does not expect a buildtree or it was explictily cached without one."
                    self.warn("WARNING: {} Artifact contains an empty buildtree".format(self.name), detail=detail)

            # No cached buildtree, stage source from source cache
            else:

                # Assert sources are cached
                assert self._has_all_sources_in_source_cache()

                if self.__sources:

                    sourcecache = context.sourcecache
                    # find last required source
                    last_required_previous_ix = self.__last_source_requires_previous()
                    import_dir = CasBasedDirectory(context.get_cascache())

                    try:
                        for source in self.__sources[last_required_previous_ix:]:
                            source_dir = sourcecache.export(source)
                            import_dir.import_files(source_dir)

                    except SourceCacheError as e:
                        raise ElementError("Error trying to export source for {}: {}".format(self.name, e))
                    except VirtualDirectoryError as e:
                        raise ElementError(
                            "Error trying to import sources together for {}: {}".format(self.name, e),
                            reason="import-source-files-fail",
                        )

                    self.__sources_vdir = import_dir

                    # incremental builds should merge the source into the last artifact before staging
                    last_build_artifact = self.__get_last_build_artifact()
                    if last_build_artifact:
                        self.info("Incremental build")
                        last_sources = last_build_artifact.get_sources()
                        import_dir = last_build_artifact.get_buildtree()
                        import_dir._apply_changes(last_sources, self.__sources_vdir)

            # Set update_mtime to ensure deterministic mtime of sources at build time
            with utils._deterministic_umask():
                vdirectory.import_files(import_dir, update_mtime=BST_ARBITRARY_TIMESTAMP)

        # Ensure deterministic owners of sources at build time
        vdirectory.set_deterministic_user()

    # _set_artifact_files_required():
    #
    # Mark artifact files for this element and its runtime dependencies as
    # required in the local cache.
    #
    def _set_artifact_files_required(self, scope=Scope.RUN):
        if self.__artifact_files_required:
            # Already done
            return

        self.__artifact_files_required = True

        # Request artifact files of runtime dependencies
        for dep in self.dependencies(scope, recurse=False):
            dep._set_artifact_files_required(scope=scope)

    # _artifact_files_required():
    #
    # Returns whether artifact files for this element have been marked as required.
    #
    def _artifact_files_required(self):
        return self.__artifact_files_required

    # __should_schedule()
    #
    # Returns:
    #     bool - Whether the element can be scheduled for a build.
    #
    def __should_schedule(self):
        # We're processing if we're already scheduled, we've
        # finished assembling or if we're waiting to pull.
        processing = self.__assemble_scheduled or self.__assemble_done or self._pull_pending()

        # We should schedule a build when
        return (
            # We're not processing
            not processing
            and
            # We have figured out the state of our artifact
            self.__artifact
            and
            # And we're not cached yet
            not self._cached()
        )

    # _schedule_assembly_when_necessary():
    #
    # This is called in the main process before the element is assembled
    # in a subprocess.
    #
    def _schedule_assembly_when_necessary(self):
        # FIXME: We could reduce the number of function calls a bit by
        # factoring this out of this method (and checking whether we
        # should schedule at the calling end).
        #
        # This would make the code less pretty, but it's a possible
        # optimization if we get desperate enough (and we will ;)).
        if not self.__should_schedule():
            return

        self.__assemble_scheduled = True

        # Requests artifacts of build dependencies
        for dep in self.dependencies(Scope.BUILD, recurse=False):
            dep._schedule_assembly_when_necessary()

        # Once we schedule an element for assembly, we know that our
        # build dependencies have strong cache keys, so we can update
        # our own strong cache key.
        self.__update_cache_key_non_strict()

    # _assemble_done():
    #
    # This is called in the main process after the element has been assembled.
    #
    # This will result in updating the element state.
    #
    # Args:
    #     successful (bool): Whether the build was successful
    #
    def _assemble_done(self, successful):
        assert self.__assemble_scheduled

        self.__assemble_scheduled = False
        self.__assemble_done = True

        self.__strict_artifact.reset_cached()

        if successful:
            # Directly set known cached status as optimization to avoid
            # querying buildbox-casd and the filesystem.
            self.__artifact.set_cached()
            self.__cached_successfully = True
        else:
            self.__artifact.reset_cached()

        # When we're building in non-strict mode, we may have
        # assembled everything to this point without a strong cache
        # key. Once the element has been assembled, a strong cache key
        # can be set, so we do so.
        self.__update_cache_key_non_strict()
        self._update_ready_for_runtime_and_cached()

        if self._get_workspace() and self._cached():
            assert utils._is_main_process(), "Attempted to save workspace configuration from child process"
            #
            # Note that this block can only happen in the
            # main process, since `self._cached_success()` cannot
            # be true when assembly is successful in the task.
            #
            # For this reason, it is safe to update and
            # save the workspaces configuration
            #
            key = self._get_cache_key()
            workspace = self._get_workspace()
            workspace.last_build = key
            self._get_context().get_workspaces().save_config()

    # _assemble():
    #
    # Internal method for running the entire build phase.
    #
    # This will:
    #   - Prepare a sandbox for the build
    #   - Call the public abstract methods for the build phase
    #   - Cache the resulting artifact
    #
    # Returns:
    #    (int): The size of the newly cached artifact
    #
    def _assemble(self):

        # Assert call ordering
        assert not self._cached_success()

        context = self._get_context()
        with self._output_file() as output_file:

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)

            with utils._tempdir(
                prefix="{}-".format(self.normal_name), dir=context.builddir
            ) as rootdir, self.__sandbox(
                rootdir, output_file, output_file, self.__sandbox_config
            ) as sandbox:  # noqa

                # Let the sandbox know whether the buildtree will be required.
                # This allows the remote execution sandbox to skip buildtree
                # download when it's not needed.
                buildroot = self.get_variable("build-root")
                cache_buildtrees = context.cache_buildtrees
                if cache_buildtrees != _CacheBuildTrees.NEVER:
                    always_cache_buildtrees = cache_buildtrees == _CacheBuildTrees.ALWAYS
                    sandbox._set_build_directory(buildroot, always=always_cache_buildtrees)

                if not self.BST_RUN_COMMANDS:
                    # Element doesn't need to run any commands in the sandbox.
                    #
                    # Disable Sandbox.run() to allow CasBasedDirectory for all
                    # sandboxes.
                    sandbox._disable_run()

                # By default, the dynamic public data is the same as the static public data.
                # The plugin's assemble() method may modify this, though.
                self.__dynamic_public = self.__public.clone()

                # Call the abstract plugin methods

                # Step 1 - Configure
                self.__configure_sandbox(sandbox)
                # Step 2 - Stage
                self.stage(sandbox)
                try:
                    if self.__batch_prepare_assemble:
                        cm = sandbox.batch(
                            self.__batch_prepare_assemble_flags, collect=self.__batch_prepare_assemble_collect
                        )
                    else:
                        cm = contextlib.suppress()

                    with cm:
                        # Step 3 - Prepare
                        self.__prepare(sandbox)
                        # Step 4 - Assemble
                        collect = self.assemble(sandbox)  # pylint: disable=assignment-from-no-return

                    self.__set_build_result(success=True, description="succeeded")
                except (ElementError, SandboxCommandError) as e:
                    # Shelling into a sandbox is useful to debug this error
                    e.sandbox = True

                    self.__set_build_result(success=False, description=str(e), detail=e.detail)
                    self._cache_artifact(sandbox, e.collect)

                    raise
                else:
                    return self._cache_artifact(sandbox, collect)

    def _cache_artifact(self, sandbox, collect):

        context = self._get_context()
        buildresult = self.__build_result
        publicdata = self.__dynamic_public
        sandbox_vroot = sandbox.get_virtual_directory()
        collectvdir = None
        sandbox_build_dir = None
        sourcesvdir = None

        cache_buildtrees = context.cache_buildtrees
        build_success = buildresult[0]

        # cache_buildtrees defaults to 'auto', only caching buildtrees
        # when necessary, which includes failed builds.
        # If only caching failed artifact buildtrees, then query the build
        # result. Element types without a build-root dir will be cached
        # with an empty buildtreedir regardless of this configuration.

        if cache_buildtrees == _CacheBuildTrees.ALWAYS or (
            cache_buildtrees == _CacheBuildTrees.AUTO and (not build_success or self._get_workspace())
        ):
            try:
                sandbox_build_dir = sandbox_vroot.descend(
                    *self.get_variable("build-root").lstrip(os.sep).split(os.sep)
                )
                sandbox._fetch_missing_blobs(sandbox_build_dir)
            except VirtualDirectoryError:
                # Directory could not be found. Pre-virtual
                # directory behaviour was to continue silently
                # if the directory could not be found.
                pass

            sourcesvdir = self.__sources_vdir

        if collect is not None:
            try:
                collectvdir = sandbox_vroot.descend(*collect.lstrip(os.sep).split(os.sep))
                sandbox._fetch_missing_blobs(collectvdir)
            except VirtualDirectoryError:
                pass

        # ensure we have cache keys
        self.__update_cache_key_non_strict()

        with self.timed_activity("Caching artifact"):
            artifact_size = self.__artifact.cache(sandbox_build_dir, collectvdir, sourcesvdir, buildresult, publicdata)

        if collect is not None and collectvdir is None:
            raise ElementError(
                "Directory '{}' was not found inside the sandbox, "
                "unable to collect artifact contents".format(collect)
            )

        return artifact_size

    def _get_build_log(self):
        return self._build_log_path

    # _fetch_done()
    #
    # Indicates that fetching the sources for this element has been done.
    #
    # Args:
    #   fetched_original (bool): Whether the original sources had been asked (and fetched) or not
    #
    def _fetch_done(self, fetched_original):
        self.__has_all_sources_in_source_cache = True
        if fetched_original:
            self.__has_all_sources_cached = True

        for source in self.__sources:
            source._fetch_done(fetched_original)

    # _pull_pending()
    #
    # Check whether the artifact will be pulled. If the pull operation is to
    # include a specific subdir of the element artifact (from cli or user conf)
    # then the local cache is queried for the subdirs existence.
    #
    # Returns:
    #   (bool): Whether a pull operation is pending
    #
    def _pull_pending(self):
        if self._get_workspace():
            # Workspace builds are never pushed to artifact servers
            return False

        # Check whether the pull has been invoked with a specific subdir requested
        # in user context, as to complete a partial artifact
        pull_buildtrees = self._get_context().pull_buildtrees

        if self.__strict_artifact:
            if self.__strict_artifact.cached() and pull_buildtrees:
                # If we've specified a subdir, check if the subdir is cached locally
                # or if it's possible to get
                if self._cached_buildtree() or not self._buildtree_exists():
                    return False
            elif self.__strict_artifact.cached():
                return False

        # Pull is pending if artifact remote server available
        # and pull has not been attempted yet
        return self.__artifacts.has_fetch_remotes(plugin=self) and not self.__pull_done

    # _pull_done()
    #
    # Indicate that pull was attempted.
    #
    # This needs to be called in the main process after a pull
    # succeeds or fails so that we properly update the main
    # process data model
    #
    # This will result in updating the element state.
    #
    def _pull_done(self):
        self.__pull_done = True

        # Artifact may become cached after pulling, so let it query the
        # filesystem again to check
        self.__strict_artifact.reset_cached()
        self.__artifact.reset_cached()

        # We may not have actually pulled an artifact - the pull may
        # have failed. We might therefore need to schedule assembly.
        self._schedule_assembly_when_necessary()
        # If we've finished pulling, an artifact might now exist
        # locally, so we might need to update a non-strict strong
        # cache key.
        self.__update_cache_key_non_strict()
        self._update_ready_for_runtime_and_cached()

    # _pull():
    #
    # Pull artifact from remote artifact repository into local artifact cache.
    #
    # Returns: True if the artifact has been downloaded, False otherwise
    #
    def _pull(self):
        context = self._get_context()

        # Get optional specific subdir to pull and optional list to not pull
        # based off of user context
        pull_buildtrees = context.pull_buildtrees

        # Attempt to pull artifact without knowing whether it's available
        pulled = self.__pull_strong(pull_buildtrees=pull_buildtrees)

        if not pulled and not self._cached() and not context.get_strict():
            pulled = self.__pull_weak(pull_buildtrees=pull_buildtrees)

        if not pulled:
            return False

        # Notify successfull download
        return True

    def _skip_source_push(self):
        if not self.__sources or self._get_workspace():
            return True
        return not (self.__sourcecache.has_push_remotes(plugin=self) and self._has_all_sources_in_source_cache())

    def _source_push(self):
        # try and push sources if we've got them
        if self.__sourcecache.has_push_remotes(plugin=self) and self._has_all_sources_in_source_cache():
            for source in self.sources():
                if not self.__sourcecache.push(source):
                    return False

        # Notify successful upload
        return True

    # _skip_push():
    #
    # Determine whether we should create a push job for this element.
    #
    # Returns:
    #   (bool): True if this element does not need a push job to be created
    #
    def _skip_push(self):
        if not self.__artifacts.has_push_remotes(plugin=self):
            # No push remotes for this element's project
            return True

        # Do not push elements that aren't cached, or that are cached with a dangling buildtree
        # ref unless element type is expected to have an an empty buildtree directory
        if not self._cached_buildtree() and self._buildtree_exists():
            return True

        # Do not push tainted artifact
        if self.__get_tainted():
            return True

        return False

    # _push():
    #
    # Push locally cached artifact to remote artifact repository.
    #
    # Returns:
    #   (bool): True if the remote was updated, False if it already existed
    #           and no updated was required
    #
    def _push(self):
        self.__assert_cached()

        if self.__get_tainted():
            self.warn("Not pushing tainted artifact.")
            return False

        # Push all keys used for local commit via the Artifact member
        pushed = self.__artifacts.push(self, self.__artifact)
        if not pushed:
            return False

        # Notify successful upload
        return True

    # _shell():
    #
    # Connects the terminal with a shell running in a staged
    # environment
    #
    # Args:
    #    scope (Scope): Either BUILD or RUN scopes are valid, or None
    #    mounts (list): A list of (str, str) tuples, representing host/target paths to mount
    #    isolate (bool): Whether to isolate the environment like we do in builds
    #    prompt (str): A suitable prompt string for PS1
    #    command (list): An argv to launch in the sandbox
    #    usebuildtree (bool): Use the buildtree as its source
    #
    # Returns: Exit code
    def _shell(self, scope=None, *, mounts=None, isolate=False, prompt=None, command=None, usebuildtree=False):

        with self._prepare_sandbox(scope, shell=True, usebuildtree=usebuildtree) as sandbox:
            environment = self.get_environment()
            environment = copy.copy(environment)
            flags = SandboxFlags.INTERACTIVE | SandboxFlags.ROOT_READ_ONLY

            # Fetch the main toplevel project, in case this is a junctioned
            # subproject, we want to use the rules defined by the main one.
            context = self._get_context()
            project = context.get_toplevel_project()
            shell_command, shell_environment, shell_host_files = project.get_shell_config()

            if prompt is not None:
                environment["PS1"] = prompt

            # Special configurations for non-isolated sandboxes
            if not isolate:

                # Open the network, and reuse calling uid/gid
                #
                flags |= SandboxFlags.NETWORK_ENABLED | SandboxFlags.INHERIT_UID

                # Apply project defined environment vars to set for a shell
                for key, value in shell_environment.items():
                    environment[key] = value

                # Setup any requested bind mounts
                if mounts is None:
                    mounts = []

                for mount in shell_host_files + mounts:
                    if not os.path.exists(mount.host_path):
                        if not mount.optional:
                            self.warn("Not mounting non-existing host file: {}".format(mount.host_path))
                    else:
                        sandbox.mark_directory(mount.path)
                        sandbox._set_mount_source(mount.path, mount.host_path)

            if command:
                argv = command
            else:
                argv = shell_command

            self.status("Running command", detail=" ".join(argv))

            # Run shells with network enabled and readonly root.
            return sandbox.run(argv, flags, env=environment)

    # _open_workspace():
    #
    # "Open" a workspace for this element
    #
    # This requires that a workspace already be created in
    # the workspaces metadata first.
    #
    def _open_workspace(self):
        context = self._get_context()
        workspace = self._get_workspace()
        assert workspace is not None

        # First lets get a temp dir in our build directory
        # and stage there, then link the files over to the desired
        # path.
        #
        # We do this so that force opening workspaces which overwrites
        # files in the target directory actually works without any
        # additional support from Source implementations.
        #
        os.makedirs(context.builddir, exist_ok=True)
        with utils._tempdir(dir=context.builddir, prefix="workspace-{}".format(self.normal_name)) as temp:
            for source in self.sources():
                source._init_workspace(temp)

            # Now hardlink the files into the workspace target.
            utils.link_files(temp, workspace.get_absolute_path())

    # _get_workspace():
    #
    # Returns:
    #    (Workspace|None): A workspace associated with this element
    #
    def _get_workspace(self):
        workspaces = self._get_context().get_workspaces()
        return workspaces.get_workspace(self._get_full_name())

    # _write_script():
    #
    # Writes a script to the given directory.
    def _write_script(self, directory):
        with open(_site.build_module_template, "r") as f:
            script_template = f.read()

        variable_string = ""
        for var, val in self.get_environment().items():
            variable_string += "{0}={1} ".format(var, val)

        script = script_template.format(
            name=self.normal_name,
            build_root=self.get_variable("build-root"),
            install_root=self.get_variable("install-root"),
            variables=variable_string,
            commands=self.generate_script(),
        )

        os.makedirs(directory, exist_ok=True)
        script_path = os.path.join(directory, "build-" + self.normal_name)

        with self.timed_activity("Writing build script", silent_nested=True):
            with utils.save_file_atomic(script_path, "w") as script_file:
                script_file.write(script)

            os.chmod(script_path, stat.S_IEXEC | stat.S_IREAD)

    # Returns the element whose sources this element is ultimately derived from.
    #
    # This is intended for being used to redirect commands that operate on an
    # element to the element whose sources it is ultimately derived from.
    #
    # For example, element A is a build element depending on source foo,
    # element B is a filter element that depends on element A. The source
    # element of B is A, since B depends on A, and A has sources.
    #
    def _get_source_element(self):
        return self

    # _cached_buildtree()
    #
    # Check if element artifact contains expected buildtree. An
    # element's buildtree artifact will not be present if the rest
    # of the partial artifact is not cached.
    #
    # Returns:
    #     (bool): True if artifact cached with buildtree, False if
    #             element not cached or missing expected buildtree.
    #             Note this only confirms if a buildtree is present,
    #             not its contents.
    #
    def _cached_buildtree(self):
        if not self._cached():
            return False

        return self.__artifact.cached_buildtree()

    # _buildtree_exists()
    #
    # Check if artifact was created with a buildtree. This does not check
    # whether the buildtree is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildtree, False if
    #             element not cached or not created with a buildtree.
    #
    def _buildtree_exists(self):
        if not self._cached():
            return False

        return self.__artifact.buildtree_exists()

    # _cached_logs()
    #
    # Check if the artifact is cached with log files.
    #
    # Returns:
    #     (bool): True if artifact is cached with logs, False if
    #             element not cached or missing logs.
    #
    def _cached_logs(self):
        return self.__artifact.cached_logs()

    # _fetch()
    #
    # Fetch the element's sources.
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    def _fetch(self, fetch_original=False):
        previous_sources = []
        fetch_needed = False

        if self.__sources and not fetch_original:
            for source in self.__sources:
                if self.__sourcecache.contains(source):
                    continue

                # try and fetch from source cache
                if not source._is_cached() and self.__sourcecache.has_fetch_remotes():
                    if self.__sourcecache.pull(source):
                        continue

                fetch_needed = True

        # We need to fetch original sources
        if fetch_needed or fetch_original:
            for source in self.sources():
                if not source._is_cached():
                    source._fetch(previous_sources)
                previous_sources.append(source)

            self.__cache_sources()

    # _calculate_cache_key():
    #
    # Calculates the cache key
    #
    # Returns:
    #    (str): A hex digest cache key for this Element, or None
    #
    # None is returned if information for the cache key is missing.
    #
    def _calculate_cache_key(self, dependencies):
        # No cache keys for dependencies which have no cache keys
        if None in dependencies:
            return None

        # Generate dict that is used as base for all cache keys
        if self.__cache_key_dict is None:
            # Filter out nocache variables from the element's environment
            cache_env = {key: value for key, value in self.__environment.items() if key not in self.__env_nocache}

            project = self._get_project()

            self.__cache_key_dict = {
                "core-artifact-version": BST_CORE_ARTIFACT_VERSION,
                "element-plugin-key": self.get_unique_key(),
                "element-plugin-name": self.get_kind(),
                "element-plugin-version": self.BST_ARTIFACT_VERSION,
                "sandbox": self.__sandbox_config.get_unique_key(),
                "environment": cache_env,
                "public": self.__public.strip_node_info(),
            }

            self.__cache_key_dict["sources"] = []

            for source in self.__sources:
                self.__cache_key_dict["sources"].append(
                    {"key": source._get_unique_key(), "name": source._get_source_name()}
                )

            self.__cache_key_dict["fatal-warnings"] = sorted(project._fatal_warnings)

        cache_key_dict = self.__cache_key_dict.copy()
        cache_key_dict["dependencies"] = dependencies

        return _cachekey.generate_key(cache_key_dict)

    # Check if sources are cached, generating the source key if it hasn't been
    def _has_all_sources_in_source_cache(self):
        if self.__has_all_sources_in_source_cache is not None:
            return self.__has_all_sources_in_source_cache

        if self.__sources:
            sourcecache = self._get_context().sourcecache

            # Go through sources we'll cache generating keys
            for ix, source in enumerate(self.__sources):
                if not source._key:
                    if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                        source._generate_key(self.__sources[:ix])
                    else:
                        source._generate_key([])

            # Check all sources are in source cache
            for source in self.__sources:
                if not sourcecache.contains(source):
                    return False

        self.__has_all_sources_in_source_cache = True
        return True

    # _has_all_sources_resolved()
    #
    # Get whether all sources of the element are resolved
    #
    def _has_all_sources_resolved(self):
        return self.__is_resolved

    # _has_all_sources_cached()
    #
    # Get whether all the sources of the element have their own cached
    # copy of their sources.
    #
    def _has_all_sources_cached(self):
        if not self.__has_all_sources_cached:
            self.__has_all_sources_cached = all(source._is_cached() for source in self.__sources)
        return self.__has_all_sources_cached

    def _should_fetch(self, fetch_original=False):
        """ return bool of if we need to run the fetch stage for this element

        Args:
            fetch_original (bool): whether we need to original unstaged source
        """
        if fetch_original:
            return not self._has_all_sources_cached()
        return not self._has_all_sources_in_source_cache()

    # _set_can_query_cache_callback()
    #
    # Notify the pull/fetch queue that the element is potentially
    # ready to be processed.
    #
    # Set the _can_query_cache_callback - the _can_query_cache_callback is
    # invoked when an element becomes able to query the cache. That is,
    # the (non-workspaced) element's strict cache key has been calculated.
    # However, if the element is workspaced, we also invoke this callback
    # once its build has been scheduled - this ensures that the workspaced
    # element does not get blocked in the pull queue.
    #
    # Args:
    #    callback (callable) - The callback function
    #
    def _set_can_query_cache_callback(self, callback):
        self.__can_query_cache_callback = callback

    # _set_buildable_callback()
    #
    # Notifiy the build queue that the element is potentially ready
    # to be processed
    #
    # Set the _buildable_callback - the _buildable_callback is invoked when
    # an element is marked as "buildable". That is, its sources are consistent,
    # its been scheduled to be built and all of its build dependencies have
    # had their cache key's calculated and are cached.
    #
    # Args:
    #    callback (callable) - The callback function
    #
    def _set_buildable_callback(self, callback):
        self.__buildable_callback = callback

    # _set_depth()
    #
    # Set the depth of the Element.
    #
    # The depth represents the position of the Element within the current
    # session's dependency graph. A depth of zero represents the bottommost element.
    #
    def _set_depth(self, depth):
        self._depth = depth

    # _update_ready_for_runtime_and_cached()
    #
    # An Element becomes ready for runtime and cached once the following criteria
    # are met:
    #  1. The Element has a strong cache key
    #  2. The Element is cached (locally)
    #  3. The runtime dependencies of the Element are ready for runtime and cached.
    #
    # These criteria serve as potential trigger points as to when an Element may have
    # become ready for runtime and cached.
    #
    # Once an Element becomes ready for runtime and cached, we notify the reverse
    # runtime dependencies and the reverse build dependencies of the element, decrementing
    # the appropriate counters.
    #
    def _update_ready_for_runtime_and_cached(self):
        if not self.__ready_for_runtime_and_cached:
            if self.__runtime_deps_uncached == 0 and self._cached_success() and self.__cache_key:
                self.__ready_for_runtime_and_cached = True

                # Notify reverse dependencies
                for rdep in self.__reverse_runtime_deps:
                    rdep.__runtime_deps_uncached -= 1
                    assert not rdep.__runtime_deps_uncached < 0

                    # Try to notify reverse dependencies if all runtime deps are ready
                    if rdep.__runtime_deps_uncached == 0:
                        rdep._update_ready_for_runtime_and_cached()

                for rdep in self.__reverse_build_deps:
                    rdep.__build_deps_uncached -= 1
                    assert not rdep.__build_deps_uncached < 0

                    if rdep.__buildable_callback is not None and rdep._buildable():
                        rdep.__buildable_callback(rdep)
                        rdep.__buildable_callback = None

    # _get_args_for_child_job_pickling(self)
    #
    # Return data necessary to reconstruct this object in a child job process.
    #
    # Returns:
    #    (str, dict): A tuple of (meta_kind, state), where a factory can use
    #    `meta_kind` to create an instance of the same type as `self`. `state`
    #    is what we want `self.__dict__` to be restored to after instantiation
    #    in the child process.
    #
    def _get_args_for_child_job_pickling(self):
        state = self.__dict__.copy()

        # These are called in the main process to notify the scheduler about
        # certain things. They carry a reference to the scheduler, which we
        # don't want in the child process, so clear them.
        #
        # Note that this method of referring to members is error-prone in that
        # a later 'search and replace' renaming might miss these. Guard against
        # this by making sure we are not creating new members, only clearing
        # existing ones.
        #
        assert "_Element__can_query_cache_callback" in state
        state["_Element__can_query_cache_callback"] = None
        assert "_Element__buildable_callback" in state
        state["_Element__buildable_callback"] = None

        return self.__meta_kind, state

    def _walk_artifact_files(self):
        yield from self.__artifact.get_files().walk()

    # _get_artifact()
    #
    # Return the Element's Artifact object
    #
    # Returns:
    #    (Artifact): The Artifact object of the Element
    #
    def _get_artifact(self):
        assert self.__artifact, "{}: has no Artifact object".format(self.name)
        return self.__artifact

    # _add_build_dependency()
    #
    # Add a build dependency to the Element
    #
    # Args:
    #    (Element): The Element to add as a build dependency
    #
    def _add_build_dependency(self, dependency):
        self.__build_dependencies.append(dependency)

    #############################################################
    #                   Private Local Methods                   #
    #############################################################

    # __update_resolved_state()
    #
    # Updates source's resolved state
    #
    # An element's source state must be resolved before it may compute
    # cache keys, because the source's ref, whether defined in yaml or
    # from the workspace, is a component of the element's cache keys.
    #
    def __update_resolved_state(self):
        for source in self.__sources:
            if not source.is_resolved():
                break
        else:
            self.__is_resolved = True
            self.__update_cache_keys()

    # __get_dependency_refs()
    #
    # Retrieve the artifact refs of the element's dependencies
    #
    # Args:
    #    scope (Scope): The scope of dependencies
    #
    # Returns:
    #    (list [str]): A list of refs of all dependencies in staging order.
    #
    def __get_dependency_refs(self, scope):
        return [
            os.path.join(dep.project_name, _get_normal_name(dep.name), dep._get_cache_key())
            for dep in self.dependencies(scope)
        ]

    # __get_last_build_artifact()
    #
    # Return the Artifact of the previous build of this element,
    # if incremental build is available.
    #
    # Returns:
    #    (Artifact): The Artifact of the previous build or None
    #
    def __get_last_build_artifact(self):
        workspace = self._get_workspace()
        if not workspace:
            # Currently incremental builds are only supported for workspaces
            return None

        if not workspace.last_build:
            return None

        artifact = Artifact(self, self._get_context(), strong_key=workspace.last_build)

        if not artifact.cached():
            return None

        if not artifact.cached_buildtree():
            return None

        if not artifact.cached_sources():
            return None

        # Don't perform an incremental build if there has been a change in
        # build dependencies.
        old_dep_refs = artifact.get_dependency_refs(Scope.BUILD)
        new_dep_refs = self.__get_dependency_refs(Scope.BUILD)
        if old_dep_refs != new_dep_refs:
            return None

        return artifact

    # __configure_sandbox():
    #
    # Internal method for calling public abstract configure_sandbox() method.
    #
    def __configure_sandbox(self, sandbox):
        self.__batch_prepare_assemble = False

        self.configure_sandbox(sandbox)

    # __prepare():
    #
    # Internal method for calling public abstract prepare() method.
    #
    def __prepare(self, sandbox):
        self.prepare(sandbox)

    # __preflight():
    #
    # A internal wrapper for calling the abstract preflight() method on
    # the element and its sources.
    #
    def __preflight(self):

        if self.BST_FORBID_RDEPENDS and self.BST_FORBID_BDEPENDS:
            if any(self.dependencies(Scope.RUN, recurse=False)) or any(self.dependencies(Scope.BUILD, recurse=False)):
                raise ElementError(
                    "{}: Dependencies are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-depends",
                )

        if self.BST_FORBID_RDEPENDS:
            if any(self.dependencies(Scope.RUN, recurse=False)):
                raise ElementError(
                    "{}: Runtime dependencies are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-rdepends",
                )

        if self.BST_FORBID_BDEPENDS:
            if any(self.dependencies(Scope.BUILD, recurse=False)):
                raise ElementError(
                    "{}: Build dependencies are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-bdepends",
                )

        if self.BST_FORBID_SOURCES:
            if any(self.sources()):
                raise ElementError(
                    "{}: Sources are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-sources",
                )

        try:
            self.preflight()
        except BstError as e:
            # Prepend provenance to the error
            raise ElementError("{}: {}".format(self, e), reason=e.reason, detail=e.detail) from e

        # Ensure that the first source does not need access to previous soruces
        if self.__sources and self.__sources[0]._requires_previous_sources():
            raise ElementError(
                "{}: {} cannot be the first source of an element "
                "as it requires access to previous sources".format(self, self.__sources[0])
            )

        # Preflight the sources
        for source in self.sources():
            source._preflight()

    # __assert_cached()
    #
    # Raises an error if the artifact is not cached.
    #
    def __assert_cached(self):
        assert self._cached(), "{}: Missing artifact {}".format(self, self._get_brief_display_key())

    # __get_tainted():
    #
    # Checkes whether this artifact should be pushed to an artifact cache.
    #
    # Args:
    #    recalculate (bool) - Whether to force recalculation
    #
    # Returns:
    #    (bool) False if this artifact should be excluded from pushing.
    #
    # Note:
    #    This method should only be called after the element's
    #    artifact is present in the local artifact cache.
    #
    def __get_tainted(self, recalculate=False):
        if recalculate or self.__tainted is None:

            # Whether this artifact has a workspace
            workspaced = self.__artifact.get_metadata_workspaced()

            # Whether this artifact's dependencies have workspaces
            workspaced_dependencies = self.__artifact.get_metadata_workspaced_dependencies()

            # Other conditions should be or-ed
            self.__tainted = workspaced or workspaced_dependencies

        return self.__tainted

    # __use_remote_execution():
    #
    # Returns True if remote execution is configured and the element plugin
    # supports it.
    #
    def __use_remote_execution(self):
        return bool(self.__remote_execution_specs)

    # __sandbox():
    #
    # A context manager to prepare a Sandbox object at the specified directory,
    # if the directory is None, then a directory will be chosen automatically
    # in the configured build directory.
    #
    # Args:
    #    directory (str): The local directory where the sandbox will live, or None
    #    stdout (fileobject): The stream for stdout for the sandbox
    #    stderr (fileobject): The stream for stderr for the sandbox
    #    config (SandboxConfig): The SandboxConfig object
    #    allow_remote (bool): Whether the sandbox is allowed to be remote
    #
    # Yields:
    #    (Sandbox): A usable sandbox
    #
    @contextmanager
    def __sandbox(self, directory, stdout=None, stderr=None, config=None, allow_remote=True):
        context = self._get_context()
        project = self._get_project()
        platform = context.platform

        if self._get_workspace():
            output_node_properties = ["MTime"]
        else:
            output_node_properties = None

        if directory is not None and allow_remote and self.__use_remote_execution():

            if not self.BST_VIRTUAL_DIRECTORY:
                raise ElementError(
                    "Element {} is configured to use remote execution but plugin does not support it.".format(
                        self.name
                    ),
                    detail="Plugin '{kind}' does not support virtual directories.".format(kind=self.get_kind()),
                )

            self.info("Using a remote sandbox for artifact {} with directory '{}'".format(self.name, directory))

            output_files_required = context.require_artifact_files or self._artifact_files_required()

            sandbox = SandboxRemote(
                context,
                project,
                directory,
                plugin=self,
                stdout=stdout,
                stderr=stderr,
                config=config,
                specs=self.__remote_execution_specs,
                allow_real_directory=False,
                output_files_required=output_files_required,
                output_node_properties=output_node_properties,
            )
            yield sandbox

        elif directory is not None and os.path.exists(directory):
            platform = context.platform
            platform.check_sandbox_config(config)

            sandbox = platform.create_sandbox(
                context,
                project,
                directory,
                plugin=self,
                stdout=stdout,
                stderr=stderr,
                config=config,
                allow_real_directory=not self.BST_VIRTUAL_DIRECTORY,
                output_node_properties=output_node_properties,
            )
            yield sandbox

        else:
            os.makedirs(context.builddir, exist_ok=True)

            # Recursive contextmanager...
            with utils._tempdir(
                prefix="{}-".format(self.normal_name), dir=context.builddir
            ) as rootdir, self.__sandbox(
                rootdir, stdout=stdout, stderr=stderr, config=config, allow_remote=allow_remote
            ) as sandbox:
                yield sandbox

    @classmethod
    def __compose_default_splits(cls, project, defaults, is_junction):

        element_public = defaults.get_mapping("public", default={})
        element_bst = element_public.get_mapping("bst", default={})
        element_splits = element_bst.get_mapping("split-rules", default={})

        if is_junction:
            splits = element_splits.clone()
        else:
            assert project._splits is not None

            splits = project._splits.clone()
            # Extend project wide split rules with any split rules defined by the element
            element_splits._composite(splits)

        element_bst["split-rules"] = splits
        element_public["bst"] = element_bst
        defaults["public"] = element_public

    @classmethod
    def __init_defaults(cls, project, plugin_conf, kind, is_junction):
        # Defaults are loaded once per class and then reused
        #
        if cls.__defaults is None:
            defaults = Node.from_dict({})

            if plugin_conf is not None:
                # Load the plugin's accompanying .yaml file if one was provided
                try:
                    defaults = _yaml.load(plugin_conf, os.path.basename(plugin_conf))
                except LoadError as e:
                    if e.reason != LoadErrorReason.MISSING_FILE:
                        raise e

            # Special case; compose any element-wide split-rules declarations
            cls.__compose_default_splits(project, defaults, is_junction)

            # Override the element's defaults with element specific
            # overrides from the project.conf
            if is_junction:
                elements = project.first_pass_config.element_overrides
            else:
                elements = project.element_overrides

            overrides = elements.get_mapping(kind, default=None)
            if overrides:
                overrides._composite(defaults)

            # Set the data class wide
            cls.__defaults = defaults

    # This will acquire the environment to be used when
    # creating sandboxes for this element
    #
    @classmethod
    def __extract_environment(cls, project, meta):
        default_env = cls.__defaults.get_mapping("environment", default={})

        if meta.is_junction:
            environment = Node.from_dict({})
        else:
            environment = project.base_environment.clone()

        default_env._composite(environment)
        meta.environment._composite(environment)
        environment._assert_fully_composited()

        return environment

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __expand_environment(self, environment):
        # Resolve variables in environment value strings
        final_env = {}
        for key, value in environment.items():
            final_env[key] = self.node_subst_vars(value)

        return final_env

    @classmethod
    def __extract_env_nocache(cls, project, meta):
        if meta.is_junction:
            project_nocache = []
        else:
            project_nocache = project.base_env_nocache

        default_nocache = cls.__defaults.get_str_list("environment-nocache", default=[])
        element_nocache = meta.env_nocache

        # Accumulate values from the element default, the project and the element
        # itself to form a complete list of nocache env vars.
        env_nocache = set(project_nocache + default_nocache + element_nocache)

        # Convert back to list now we know they're unique
        return list(env_nocache)

    # This will resolve the final variables to be used when
    # substituting command strings to be run in the sandbox
    #
    @classmethod
    def __extract_variables(cls, project, meta):
        default_vars = cls.__defaults.get_mapping("variables", default={})

        if meta.is_junction:
            variables = project.first_pass_config.base_variables.clone()
        else:
            variables = project.base_variables.clone()

        default_vars._composite(variables)
        meta.variables._composite(variables)
        variables._assert_fully_composited()

        for var in ("project-name", "element-name", "max-jobs"):
            node = variables.get_node(var, allow_none=True)

            if node is None:
                continue

            provenance = node.get_provenance()
            if not provenance._is_synthetic:
                raise LoadError(
                    "{}: invalid redefinition of protected variable '{}'".format(provenance, var),
                    LoadErrorReason.PROTECTED_VARIABLE_REDEFINED,
                )

        return variables

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    @classmethod
    def __extract_config(cls, meta):

        # The default config is already composited with the project overrides
        config = cls.__defaults.get_mapping("config", default={})
        config = config.clone()

        meta.config._composite(config)
        config._assert_fully_composited()

        return config

    # Sandbox-specific configuration data, to be passed to the sandbox's constructor.
    #
    @classmethod
    def __extract_sandbox_config(cls, context, project, meta):
        if meta.is_junction:
            sandbox_config = Node.from_dict({})
        else:
            sandbox_config = project._sandbox.clone()

        # Get the platform to ask for host architecture
        platform = context.platform
        host_arch = platform.get_host_arch()
        host_os = platform.get_host_os()

        # The default config is already composited with the project overrides
        sandbox_defaults = cls.__defaults.get_mapping("sandbox", default={})
        sandbox_defaults = sandbox_defaults.clone()

        sandbox_defaults._composite(sandbox_config)
        meta.sandbox._composite(sandbox_config)
        sandbox_config._assert_fully_composited()

        # Sandbox config, unlike others, has fixed members so we should validate them
        sandbox_config.validate_keys(["build-uid", "build-gid", "build-os", "build-arch"])

        build_os = sandbox_config.get_str("build-os", default=None)
        if build_os:
            build_os = build_os.lower()
        else:
            build_os = host_os

        build_arch = sandbox_config.get_str("build-arch", default=None)
        if build_arch:
            build_arch = Platform.canonicalize_arch(build_arch)
        else:
            build_arch = host_arch

        return SandboxConfig(
            sandbox_config.get_int("build-uid", None), sandbox_config.get_int("build-gid", None), build_os, build_arch,
        )

    # This makes a special exception for the split rules, which
    # elements may extend but whos defaults are defined in the project.
    #
    @classmethod
    def __extract_public(cls, meta):
        base_public = cls.__defaults.get_mapping("public", default={})
        base_public = base_public.clone()

        base_bst = base_public.get_mapping("bst", default={})
        base_splits = base_bst.get_mapping("split-rules", default={})

        element_public = meta.public.clone()
        element_bst = element_public.get_mapping("bst", default={})
        element_splits = element_bst.get_mapping("split-rules", default={})

        # Allow elements to extend the default splits defined in their project or
        # element specific defaults
        element_splits._composite(base_splits)

        element_bst["split-rules"] = base_splits
        element_public["bst"] = element_bst

        element_public._assert_fully_composited()

        return element_public

    # Expand the splits in the public data using the Variables in the element
    def __expand_splits(self, element_public):
        element_bst = element_public.get_mapping("bst", default={})
        element_splits = element_bst.get_mapping("split-rules", default={})

        # Resolve any variables in the public split rules directly
        for domain, splits in element_splits.items():
            splits = [self.__variables.subst(split.strip()) for split in splits.as_str_list()]
            element_splits[domain] = splits

        return element_public

    def __init_splits(self):
        bstdata = self.get_public_data("bst")
        splits = bstdata.get_mapping("split-rules")
        self.__splits = {
            domain: re.compile("^(?:" + "|".join([utils._glob2re(r) for r in rules.as_str_list()]) + ")$")
            for domain, rules in splits.items()
        }

    # __split_filter():
    #
    # Returns True if the file with the specified `path` is included in the
    # specified split domains. This is used by `__split_filter_func()` to create
    # a filter callback.
    #
    # Args:
    #    element_domains (list): All domains for this element
    #    include (list): A list of domains to include files from
    #    exclude (list): A list of domains to exclude files from
    #    orphans (bool): Whether to include files not spoken for by split domains
    #    path (str): The relative path of the file
    #
    # Returns:
    #    (bool): Whether to include the specified file
    #
    def __split_filter(self, element_domains, include, exclude, orphans, path):
        # Absolute path is required for matching
        filename = os.path.join(os.sep, path)

        include_file = False
        exclude_file = False
        claimed_file = False

        for domain in element_domains:
            if self.__splits[domain].match(filename):
                claimed_file = True
                if domain in include:
                    include_file = True
                if domain in exclude:
                    exclude_file = True

        if orphans and not claimed_file:
            include_file = True

        return include_file and not exclude_file

    # __split_filter_func():
    #
    # Returns callable split filter function for use with `copy_files()`,
    # `link_files()` or `Directory.import_files()`.
    #
    # Args:
    #    include (list): An optional list of domains to include files from
    #    exclude (list): An optional list of domains to exclude files from
    #    orphans (bool): Whether to include files not spoken for by split domains
    #
    # Returns:
    #    (callable): Filter callback that returns True if the file is included
    #                in the specified split domains.
    #
    def __split_filter_func(self, include=None, exclude=None, orphans=True):
        # No splitting requested, no filter needed
        if orphans and not (include or exclude):
            return None

        if not self.__splits:
            self.__init_splits()

        element_domains = list(self.__splits.keys())
        if not include:
            include = element_domains
        if not exclude:
            exclude = []

        # Ignore domains that dont apply to this element
        #
        include = [domain for domain in include if domain in element_domains]
        exclude = [domain for domain in exclude if domain in element_domains]

        # The arguments element_domains, include, exclude, and orphans are
        # the same for all files. Use `partial` to create a function with
        # the required callback signature: a single `path` parameter.
        return partial(self.__split_filter, element_domains, include, exclude, orphans)

    def __compute_splits(self, include=None, exclude=None, orphans=True):
        filter_func = self.__split_filter_func(include=include, exclude=exclude, orphans=orphans)

        files_vdir = self.__artifact.get_files()

        element_files = files_vdir.list_relative_paths()

        if not filter_func:
            # No splitting requested, just report complete artifact
            yield from element_files
        else:
            for filename in element_files:
                if filter_func(filename):
                    yield filename

    def __file_is_whitelisted(self, path):
        # Considered storing the whitelist regex for re-use, but public data
        # can be altered mid-build.
        # Public data is not guaranteed to stay the same for the duration of
        # the build, but I can think of no reason to change it mid-build.
        # If this ever changes, things will go wrong unexpectedly.
        if not self.__whitelist_regex:
            bstdata = self.get_public_data("bst")
            whitelist = bstdata.get_str_list("overlap-whitelist", default=[])
            whitelist_expressions = [utils._glob2re(self.__variables.subst(exp.strip())) for exp in whitelist]
            expression = "^(?:" + "|".join(whitelist_expressions) + ")$"
            self.__whitelist_regex = re.compile(expression)
        return self.__whitelist_regex.match(os.path.join(os.sep, path))

    # __load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    def __load_public_data(self):
        self.__assert_cached()
        assert self.__dynamic_public is None

        self.__dynamic_public = self.__artifact.load_public_data()

    def __load_build_result(self):
        self.__assert_cached()
        assert self.__build_result is None

        self.__build_result = self.__artifact.load_build_result()

    # __pull_strong():
    #
    # Attempt pulling given element from configured artifact caches with
    # the strict cache key
    #
    # Args:
    #     progress (callable): The progress callback, if any
    #     subdir (str): The optional specific subdir to pull
    #     excluded_subdirs (list): The optional list of subdirs to not pull
    #
    # Returns:
    #     (bool): Whether or not the pull was successful
    #
    def __pull_strong(self, *, pull_buildtrees):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)
        key = self.__strict_cache_key
        if not self.__artifacts.pull(self, key, pull_buildtrees=pull_buildtrees):
            return False

        # update weak ref by pointing it to this newly fetched artifact
        self.__artifacts.link_key(self, key, weak_key)

        return True

    # __pull_weak():
    #
    # Attempt pulling given element from configured artifact caches with
    # the weak cache key
    #
    # Args:
    #     subdir (str): The optional specific subdir to pull
    #     excluded_subdirs (list): The optional list of subdirs to not pull
    #
    # Returns:
    #     (bool): Whether or not the pull was successful
    #
    def __pull_weak(self, *, pull_buildtrees):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)
        if not self.__artifacts.pull(self, weak_key, pull_buildtrees=pull_buildtrees):
            return False

        # extract strong cache key from this newly fetched artifact
        self._pull_done()

        # create tag for strong cache key
        key = self._get_cache_key(strength=_KeyStrength.STRONG)
        self.__artifacts.link_key(self, weak_key, key)

        return True

    # __cache_sources():
    #
    # Caches the sources into the local CAS
    #
    def __cache_sources(self):
        if self.__sources and not self._has_all_sources_in_source_cache():
            last_requires_previous = 0
            # commit all other sources by themselves
            for ix, source in enumerate(self.__sources):
                if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                    self.__sourcecache.commit(source, self.__sources[last_requires_previous:ix])
                    last_requires_previous = ix
                else:
                    self.__sourcecache.commit(source, [])

    # __last_source_requires_previous
    #
    # This is the last source that requires previous sources to be cached.
    # Sources listed after this will be cached separately.
    #
    # Returns:
    #    (int): index of last source that requires previous sources
    #
    def __last_source_requires_previous(self):
        if self.__last_source_requires_previous_ix is None:
            last_requires_previous = 0
            for ix, source in enumerate(self.__sources):
                if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                    last_requires_previous = ix
            self.__last_source_requires_previous_ix = last_requires_previous
        return self.__last_source_requires_previous_ix

    # __update_cache_keys()
    #
    # Updates weak and strict cache keys
    #
    # Note that it does not update *all* cache keys - In non-strict mode, the
    # strong cache key is updated in __update_cache_key_non_strict()
    #
    # If the element's is not resolved, this is
    # a no-op (since inconsistent elements cannot have cache keys).
    #
    # The weak and strict cache keys will be calculated if not already
    # set.
    #
    # The weak cache key is a cache key that doesn't change when its
    # runtime dependencies change, useful for avoiding full rebuilds
    # when one's dependencies guarantee stability across
    # versions. Changes in build dependencies still force a rebuild,
    # since those will change the built artifact directly.
    #
    # The strict cache key is a cache key that changes if any
    # dependency has changed.
    #
    def __update_cache_keys(self):
        if not self._has_all_sources_resolved():
            # Tracking may still be pending
            return

        context = self._get_context()

        if self.__weak_cache_key is None:
            # Calculate weak cache key
            #
            # Weak cache key includes names of direct build dependencies
            # so as to only trigger rebuilds when the shape of the
            # dependencies change.
            #
            # Some conditions cause dependencies to be strict, such
            # that this element will be rebuilt anyway if the dependency
            # changes even in non strict mode, for these cases we just
            # encode the dependency's weak cache key instead of it's name.
            #
            dependencies = [
                [e.project_name, e.name, e._get_cache_key(strength=_KeyStrength.WEAK)]
                if self.BST_STRICT_REBUILD or e in self.__strict_dependencies
                else [e.project_name, e.name]
                for e in self.dependencies(Scope.BUILD)
            ]

            self.__weak_cache_key = self._calculate_cache_key(dependencies)

            if self.__weak_cache_key is None:
                # Weak cache key could not be calculated yet, therefore
                # the Strict cache key also can't be calculated yet.
                return

        if self.__strict_cache_key is None:
            dependencies = [
                [e.project_name, e.name, e.__strict_cache_key] if e.__strict_cache_key is not None else None
                for e in self.dependencies(Scope.BUILD)
            ]
            self.__strict_cache_key = self._calculate_cache_key(dependencies)

            if self.__strict_cache_key is not None:
                # In strict mode, the strong cache key always matches the strict cache key
                if context.get_strict():
                    self.__cache_key = self.__strict_cache_key

                    # The Element may have just become ready for runtime now that the
                    # strong cache key has just been set
                    self.__update_ready_for_runtime()
                else:
                    self.__update_strict_cache_key_of_rdeps()

        if self.__strict_cache_key is not None and self.__can_query_cache_callback is not None:
            self.__can_query_cache_callback(self)
            self.__can_query_cache_callback = None

        # If we've newly calculated a cache key, our artifact's
        # current state will also change - after all, we can now find
        # a potential existing artifact.
        if self.__weak_cache_key is not None or self.__strict_cache_key is not None:
            self.__update_artifact_state()

    # __update_artifact_state()
    #
    # Updates the data involved in knowing about the artifact corresponding
    # to this element.
    #
    # If the state changes, this will subsequently call
    # `self._schedule_assembly_when_necessary()` to schedule assembly if it becomes
    # possible.
    #
    # Element.__update_cache_keys() must be called before this to have
    # meaningful results, because the element must know its cache key before
    # it can check whether an artifact exists for that cache key.
    #
    def __update_artifact_state(self):
        context = self._get_context()

        if not self.__weak_cache_key:
            return

        if not context.get_strict() and not self.__artifact:
            # We've calculated the weak_key, so instantiate artifact instance member
            self.__artifact = Artifact(self, context, weak_key=self.__weak_cache_key)
            self._schedule_assembly_when_necessary()

        if not self.__strict_cache_key:
            return

        if not self.__strict_artifact:
            self.__strict_artifact = Artifact(
                self, context, strong_key=self.__strict_cache_key, weak_key=self.__weak_cache_key
            )

            if context.get_strict():
                self.__artifact = self.__strict_artifact
                self._schedule_assembly_when_necessary()
            else:
                self.__update_cache_key_non_strict()

    # __update_cache_key_non_strict()
    #
    # Calculates the strong cache key if it hasn't already been set.
    #
    # When buildstream runs in strict mode, this is identical to the
    # strict cache key, so no work needs to be done.
    #
    # When buildstream is not run in strict mode, this requires the artifact
    # state (as set in Element.__update_artifact_state()) to be set accordingly,
    # as the cache key can be loaded from the cache (possibly pulling from
    # a remote cache).
    #
    def __update_cache_key_non_strict(self):
        if not self.__strict_artifact:
            return

        # The final cache key can be None here only in non-strict mode
        if self.__cache_key is None:
            if self._pull_pending():
                # Effective strong cache key is unknown until after the pull
                pass
            elif self._cached():
                # Load the strong cache key from the artifact
                strong_key, _ = self.__artifact.get_metadata_keys()
                self.__cache_key = strong_key
            elif self.__assemble_scheduled or self.__assemble_done:
                # Artifact will or has been built, not downloaded
                dependencies = [[e.project_name, e.name, e._get_cache_key()] for e in self.dependencies(Scope.BUILD)]
                self.__cache_key = self._calculate_cache_key(dependencies)

            if self.__cache_key is None:
                # Strong cache key could not be calculated yet
                return

            # The Element may have just become ready for runtime now that the
            # strong cache key has just been set
            self.__update_ready_for_runtime()

            # Now we have the strong cache key, update the Artifact
            self.__artifact._cache_key = self.__cache_key

    # __update_strict_cache_key_of_rdeps()
    #
    # Once an Element is given its strict cache key, immediately inform
    # its reverse dependencies and see if their strict cache key can be
    # obtained
    #
    def __update_strict_cache_key_of_rdeps(self):
        if any(
            (
                # If we've previously updated these we don't need to do so
                # again.
                self.__updated_strict_cache_keys_of_rdeps,
                # We can't do this until none of *our* rdeps are lacking a
                # strict cache key.
                not self.__runtime_deps_without_strict_cache_key == 0,
                # If we don't have a strict cache key we can't do this either.
                self.__strict_cache_key is None,
            )
        ):
            return

        self.__updated_strict_cache_keys_of_rdeps = True

        # Notify reverse dependencies
        for rdep in self.__reverse_runtime_deps:
            rdep.__runtime_deps_without_strict_cache_key -= 1
            assert not rdep.__runtime_deps_without_strict_cache_key < 0

            if rdep.__runtime_deps_without_strict_cache_key == 0:
                rdep.__update_strict_cache_key_of_rdeps()

        for rdep in self.__reverse_build_deps:
            rdep.__build_deps_without_strict_cache_key -= 1
            assert not rdep.__build_deps_without_strict_cache_key < 0

            if rdep.__build_deps_without_strict_cache_key == 0:
                rdep.__update_cache_keys()

    # __update_ready_for_runtime()
    #
    # An Element becomes ready for runtime when:
    #
    #  1. The Element has a strong cache key
    #  2. The runtime dependencies of the Element are ready for runtime
    #
    # These criteria serve as potential trigger points as to when an Element may have
    # become ready for runtime.
    #
    # Once an Element becomes ready for runtime, we notify the reverse
    # runtime dependencies and the reverse build dependencies of the Element,
    # decrementing the appropriate counters.
    #
    def __update_ready_for_runtime(self):
        if any(
            (
                # We're already ready for runtime; no update required
                self.__ready_for_runtime,
                # If not all our dependencies are ready yet, we can't be ready
                # either.
                not self.__runtime_deps_without_cache_key == 0,
                # If our cache state has not been resolved, we can't be ready.
                self.__cache_key is None,
            )
        ):
            return

        self.__ready_for_runtime = True

        # Notify reverse dependencies
        for rdep in self.__reverse_runtime_deps:
            rdep.__runtime_deps_without_cache_key -= 1
            assert not rdep.__runtime_deps_without_cache_key < 0

            # If all of our runtimes have cache keys, we can calculate ours
            if rdep.__runtime_deps_without_cache_key == 0:
                rdep.__update_ready_for_runtime()

        for rdep in self.__reverse_build_deps:
            rdep.__build_deps_without_cache_key -= 1
            assert not rdep.__build_deps_without_cache_key < 0

            if rdep.__build_deps_without_cache_key == 0:
                rdep.__update_cache_keys()

        # If the element is cached, and has all of its runtime dependencies cached,
        # now that we have the cache key, we are able to notify reverse dependencies
        # that the element it ready. This is a likely trigger for workspaced elements.
        self._update_ready_for_runtime_and_cached()


def _overlap_error_detail(f, forbidden_overlap_elements, elements):
    if forbidden_overlap_elements:
        return "/{}: {} {} not permitted to overlap other elements, order {} \n".format(
            f,
            " and ".join(forbidden_overlap_elements),
            "is" if len(forbidden_overlap_elements) == 1 else "are",
            " above ".join(reversed(elements)),
        )
    else:
        return ""


# _get_normal_name():
#
# Get the element name without path separators or
# the extension.
#
# Args:
#     element_name (str): The element's name
#
# Returns:
#     (str): The normalised element name
#
def _get_normal_name(element_name):
    return os.path.splitext(element_name.replace(os.sep, "-"))[0]


# _compose_artifact_name():
#
# Compose the completely resolved 'artifact_name' as a filepath
#
# Args:
#     project_name (str): The project's name
#     normal_name (str): The element's normalised name
#     cache_key (str): The relevant cache key
#
# Returns:
#     (str): The constructed artifact name path
#
def _compose_artifact_name(project_name, normal_name, cache_key):
    valid_chars = string.digits + string.ascii_letters + "-._"
    normal_name = "".join([x if x in valid_chars else "_" for x in normal_name])

    # Note that project names are not allowed to contain slashes. Element names containing
    # a '/' will have this replaced with a '-' upon Element object instantiation.
    return "{0}/{1}/{2}".format(project_name, normal_name, cache_key)
