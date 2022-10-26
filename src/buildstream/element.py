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
import warnings
from contextlib import contextmanager, suppress
from functools import partial
from itertools import chain
import string
from typing import cast, TYPE_CHECKING, Any, Dict, Iterator, Iterable, List, Optional, Set, Sequence

from pyroaring import BitMap  # pylint: disable=no-name-in-module

from . import _yaml
from ._variables import Variables
from ._versions import BST_CORE_ARTIFACT_VERSION
from ._exceptions import BstError, LoadError, ImplError, SourceCacheError, CachedFailure
from .exceptions import ErrorDomain, LoadErrorReason
from .utils import FileListResult, BST_ARBITRARY_TIMESTAMP
from . import utils
from . import _cachekey
from . import _site
from .node import Node
from .plugin import Plugin
from .sandbox import _SandboxFlags, SandboxCommandError
from .sandbox._config import SandboxConfig
from .sandbox._sandboxremote import SandboxRemote
from .types import _Scope, _CacheBuildTrees, _KeyStrength, OverlapAction, _DisplayKey
from ._artifact import Artifact
from ._elementproxy import ElementProxy
from ._elementsources import ElementSources
from ._loader import Symbol, DependencyType, MetaSource
from ._overlapcollector import OverlapCollector

from .storage import Directory, DirectoryError
from .storage._filebaseddirectory import FileBasedDirectory

if TYPE_CHECKING:
    from typing import Tuple
    from .node import MappingNode, ScalarNode, SequenceNode
    from .types import SourceRef

    # pylint: disable=cyclic-import
    from .sandbox import Sandbox
    from .source import Source
    from ._context import Context
    from ._loader import LoadElement
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


class DependencyConfiguration:
    """An object representing the configuration of a dependency

    This is used to provide dependency configurations for elements which implement
    :func:`Element.configure_dependencies() <buildstream.element.Element.configure_dependencies>`
    """

    def __init__(self, element: "Element", path: str, config: Optional["MappingNode"]):

        self.element = element  # type: Element
        """The dependency Element"""

        self.path = path  # type: str
        """The path used to refer to this dependency"""

        self.config = config  # type: Optional[MappingNode]
        """The custom :term:`dependency configuration <Dependency configuration>`, or ``None``
        if no custom configuration was provided"""


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """

    # The defaults from the yaml file and project
    __defaults = None
    # A hash of Element by LoadElement
    __instantiated_elements = {}  # type: Dict[LoadElement, Element]
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

    BST_RUN_COMMANDS = True
    """Whether the element may run commands using Sandbox.run.
    """

    BST_ELEMENT_HAS_ARTIFACT = True
    """Whether the element produces an artifact when built.
    """

    def __init__(
        self,
        context: "Context",
        project: "Project",
        load_element: "LoadElement",
        plugin_conf: Dict[str, Any],
        *,
        artifact_key: str = None,
    ):

        self.__cache_key_dict = None  # Dict for cache key calculation
        self.__cache_key: Optional[str] = None  # Our cached cache key

        super().__init__(load_element.name, context, project, load_element.node, "element")

        # Ensure the project is fully loaded here rather than later on
        if not load_element.first_pass:
            project.ensure_fully_loaded()

        self.project_name = self._get_project().name
        """The :ref:`name <project_format_name>` of the owning project

        .. attention::

           Combining this attribute with :attr:`Plugin.name <buildstream.plugin.Plugin.name>`
           does not provide a unique identifier for an element within a project, this is because
           multiple :mod:`junction <elements.junction>` elements can be used specify the same
           project as a subproject.
        """

        self.normal_name = _get_normal_name(self.name)
        """A normalized element name

        This is the original element without path separators or
        the extension, it's used mainly for composing log file names
        and creating directory names and such.
        """

        #
        # Internal instance properties
        #
        self._depth = None  # Depth of Element in its current dependency graph
        self._overlap_collector = None  # type: Optional[OverlapCollector]

        #
        # Private instance properties
        #

        # Cache of proxies instantiated, indexed by the proxy owner
        self.__proxies = {}  # type: Dict[Element, ElementProxy]
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
        self.__build_deps_uncached = None  # Build dependencies which are not yet cached
        self.__runtime_deps_uncached = None  # Runtime dependencies which are not yet cached
        self.__ready_for_runtime_and_cached = False  # Whether all runtime deps are cached, as well as the element
        self.__cached_remotely = None  # Whether the element is cached remotely
        self.__sources = ElementSources(context, project, self)  # The element sources
        self.__weak_cache_key: Optional[str] = None  # Our cached weak cache key
        self.__strict_cache_key: Optional[str] = None  # Our cached cache key for strict builds
        self.__artifacts = context.artifactcache  # Artifact cache
        self.__sourcecache = context.sourcecache  # Source cache
        self.__assemble_scheduled = False  # Element is scheduled to be assembled
        self.__assemble_done = False  # Element is assembled
        self.__pull_pending = False  # Whether pull is pending
        self.__cached_successfully = None  # If the Element is known to be successfully cached
        self.__splits = None  # Resolved regex objects for computing split domains
        self.__whitelist_regex = None  # Resolved regex object to check if file is allowed to overlap
        self.__tainted = None  # Whether the artifact is tainted and should not be shared
        self.__required = False  # Whether the artifact is required in the current session
        self.__build_result = None  # The result of assembling this Element (success, description, detail)
        # Artifact class for direct artifact composite interaction
        self.__artifact = None  # type: Optional[Artifact]
        self.__dynamic_public = None
        self.__sandbox_config = None  # type: Optional[SandboxConfig]

        # Callbacks
        self.__required_callback = None  # Callback to Queues
        self.__can_query_cache_callback = None  # Callback to PullQueue/FetchQueue
        self.__buildable_callback = None  # Callback to BuildQueue

        self.__resolved_initial_state = False  # Whether the initial state of the Element has been resolved

        self.__environment: Dict[str, str] = {}
        self.__variables: Optional[Variables] = None

        if artifact_key:
            self.__initialize_from_artifact_key(artifact_key)
        else:
            self.__initialize_from_yaml(load_element, plugin_conf)

    def __lt__(self, other):
        return self.name < other.name

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def configure_dependencies(self, dependencies: Iterable[DependencyConfiguration]) -> None:
        """Configure the Element with regards to it's build dependencies

        Elements can use this method to parse custom configuration which define their
        relationship to their build dependencies.

        If this method is implemented, then it will be called with all direct build dependencies
        specified in their :ref:`element declaration <format_dependencies>` in a list.

        If the dependency was declared with custom configuration, it will be provided along
        with the dependency element, otherwise `None` will be passed with dependencies which
        do not have any additional configuration.

        If the user has specified the same build dependency multiple times with differing
        configurations, then those build dependencies will be provided multiple times
        in the ``dependencies`` list.

        Args:
           dependencies (list): A list of :class:`DependencyConfiguration <buildstream.element.DependencyConfiguration>`
                                objects

        Raises:
           :class:`.ElementError`: When the element raises an error

        The format of the :class:`MappingNode <buildstream.node.MappingNode>` provided as
        :attr:`DependencyConfiguration.config <buildstream.element.DependencyConfiguration.config>
        belongs to the implementing element, and as such the format should be documented by the plugin,
        and the :func:`MappingNode.validate_keys() <buildstream.node.MappingNode.validate_keys>`
        method should be called by the implementing plugin in order to validate it.

        .. note::

           It is unnecessary to implement this method if the plugin does not support
           any custom :term:`dependency configuration <Dependency configuration>`.
        """
        # This method is not called on plugins which do not implement it, so it would
        # be a bug if this accidentally gets called.
        #
        assert False, "Code should not be reached"

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
        return self.__sources.sources()

    def dependencies(self, selection: Sequence["Element"] = None, *, recurse: bool = True) -> Iterator["Element"]:
        """A generator function which yields the build dependencies of the given element.

        This generator gives the Element access to all of the dependencies which it is has
        access to at build time. As explained in :ref:`the dependency type documentation <format_dependencies_types>`,
        this includes the direct build dependencies of the element being built, along with any
        transient runtime dependencies of those build dependencies.

        Subsets of the dependency graph can be selected using the `selection` argument,, which
        must consist of dependencies of this element. If the `selection` argument is specified as
        `None`, then the `self` element on which this is called is used as the `selection`.

        If `recurse` is specified (the default), the full dependencies will be listed
        in deterministic staging order, starting with the basemost elements. Otherwise,
        if `recurse` is not specified then only the direct dependencies will be traversed.

        Args:
           selection (Sequence[Element]): A list of dependencies to select, or None
           recurse (bool): Whether to recurse

        Yields:
           The dependencies of the selection, in deterministic staging order
        """
        #
        # In this public API, we ensure the invariant that an element can only
        # ever see elements in it's own _Scope.BUILD scope.
        #
        #  - Yield ElementProxy objects for every element except for the self element
        #  - When a selection is provided, ensure that we call the real _dependencies()
        #    method using _Scope.RUNTIME
        #  - When iterating over the self element, use _Scope.BUILD
        #
        visited = (BitMap(), BitMap())
        if selection is None:
            selection = [self]

        for element in selection:
            if element is self:
                scope = _Scope.BUILD
            else:
                scope = _Scope.RUN

            # Elements in the `selection` will actually be `ElementProxy` objects, but
            # those calls will be forwarded to their actual internal `_dependencies()`
            # methods.
            #
            for dep in element._dependencies(scope, recurse=recurse, visited=visited):
                yield cast("Element", dep.__get_proxy(self))

    def search(self, name: str) -> Optional["Element"]:
        """Search for a dependency by name

        Args:
           name: The dependency to search for

        Returns:
           The dependency element, or None if not found.
        """
        search = self._search(_Scope.BUILD, name)
        if search is self:
            return self
        elif search:
            return cast("Element", search.__get_proxy(self))

        return None

    def node_subst_vars(self, node: "ScalarNode") -> str:
        """Replace any variables in the string contained in the node and returns it.

        **Warning**: The method is deprecated and will get removed in the next version

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
          name = self.node_subst_vars(node.get_scalar('name'))
        """
        # FIXME: remove this
        warnings.warn(
            "configuration is now automatically expanded, this is a no-op and will be removed.", DeprecationWarning
        )
        return node.as_str()

    def node_subst_sequence_vars(self, node: "SequenceNode[ScalarNode]") -> List[str]:
        """Substitute any variables in the given sequence

        **Warning**: The method is deprecated and will get removed in the next version

        Args:
          node: A SequenceNode loaded from YAML

        Returns:
          The list with every variable replaced

        Raises:
          :class:`.LoadError`

        """
        # FIXME: remove this
        warnings.warn(
            "configuration is now automatically expanded, this is a no-op and will be removed.", DeprecationWarning
        )
        return node.as_str_list()

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
        namespace, element name and :ref:`cache key <cachekeys>`.

        This can also be used as a relative path safely, and
        will normalize parts of the element name such that only
        digits, letters and some select characters are allowed.

        Args:
           key: The element's :ref:`cache key <cachekeys>`. Defaults to None

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
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True,
    ) -> FileListResult:
        """Stage this element's output artifact in the sandbox

        This will stage the files from the artifact to the sandbox at specified location.
        The files are selected for staging according to the `include`, `exclude` and `orphans`
        parameters; if `include` is not specified then all files spoken for by any domain
        are included unless explicitly excluded with an `exclude` domain.

        Args:
           sandbox: The build sandbox
           path: An optional sandbox relative path
           action (OverlapAction): The action to take when overlapping with previous invocations
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

        .. attention::

           When staging artifacts with their dependencies, use
           :func:`Element.stage_dependency_artifacts() <buildstream.element.Element.stage_dependency_artifacts>`
           instead.
        """
        assert self._overlap_collector is not None, "Attempted to stage artifacts outside of Element.stage()"

        #
        # The public API can only be called on the implementing plugin itself.
        #
        # ElementProxy calls to stage_artifact() are routed directly to _stage_artifact(),
        # and the ElementProxy takes care of starting and ending the OverlapCollector session.
        #
        with self._overlap_collector.session(action, path):
            result = self._stage_artifact(
                sandbox, path=path, action=action, include=include, exclude=exclude, orphans=orphans
            )

        return result

    def stage_dependency_artifacts(
        self,
        sandbox: "Sandbox",
        selection: Sequence["Element"] = None,
        *,
        path: str = None,
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True,
    ) -> None:
        """Stage element dependencies in scope

        This is primarily a convenience wrapper around
        :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>`
        which takes care of staging all the dependencies in staging order and issueing the
        appropriate warnings.

        The `selection` argument will behave in the same was as specified by
        :func:`Element.dependencies() <buildstream.element.Element.dependencies>`,
        If the `selection` argument is specified as `None`, then the `self` element on which this
        is called is used as the `selection`.

        Args:
           sandbox (Sandbox): The build sandbox
           selection (Sequence[Element]): A list of dependencies to select, or None
           path (str): An optional sandbox relative path
           action (OverlapAction): The action to take when overlapping with previous invocations
           include (List[str]): An optional list of domains to include files from
           exclude (List[str]): An optional list of domains to exclude files from
           orphans (bool): Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): if forbidden overlaps occur.
        """
        assert self._overlap_collector is not None, "Attempted to stage artifacts outside of Element.stage()"

        with self._overlap_collector.session(action, path):
            for dep in self.dependencies(selection):
                dep._stage_artifact(sandbox, path=path, include=include, exclude=exclude, orphans=orphans, owner=self)

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
            with sandbox.batch():
                for command in bstdata.get_str_list("integration-commands", []):
                    sandbox.run(["sh", "-e", "-c", command], env=environment, cwd="/", label=command)

    def stage_sources(self, sandbox: "Sandbox", directory: str) -> None:
        """Stage this element's sources to a directory in the sandbox

        Args:
           sandbox: The build sandbox
           directory: An absolute path within the sandbox to stage the sources at
        """
        self._stage_sources_in_sandbox(sandbox, directory)

    def get_public_data(self, domain: str) -> "MappingNode[Node]":
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

    def set_public_data(self, domain: str, data: "MappingNode[Node]") -> None:
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
        assert self.__variables
        return self.__variables.get(varname)

    def run_cleanup_commands(self, sandbox: "Sandbox") -> None:
        """Run commands to cleanup the build directory.

        Args:
           sandbox: The build sandbox

        This may be called at the end of a command batch in
        :func:`Element.assemble() <buildstream.element.Element.assemble>`
        to avoid the costs of capturing the build directory after a successful
        build.

        This will have no effect if the build tree is required after the build.
        """
        context = self._get_context()

        if self._get_workspace() or context.cache_buildtrees == _CacheBuildTrees.ALWAYS:
            # Buildtree must be preserved even after a success build if this is a
            # workspace build or the user has configured to always cache buildtrees.
            return

        build_root = self.get_variable("build-root")
        install_root = self.get_variable("install-root")

        assert build_root
        if install_root and (build_root.startswith(install_root) or install_root.startswith(build_root)):
            # Preserve the build directory if cleaning would affect the install directory
            return

        sandbox._clean_directory(build_root)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _dependencies()
    #
    # A generator function which yields the dependencies of the given element.
    #
    # If `recurse` is specified (the default), the full dependencies will be listed
    # in deterministic staging order, starting with the basemost elements in the
    # given `scope`. Otherwise, if `recurse` is not specified then only the direct
    # dependencies in the given `scope` will be traversed, and the element itself
    # will be omitted.
    #
    # Args:
    #    scope (_Scope): The scope to iterate in
    #    recurse (bool): Whether to recurse
    #
    # Yields:
    #    (Element): The dependencies in `scope`, in deterministic staging order
    #
    def _dependencies(self, scope, *, recurse=True, visited=None):

        # The format of visited is (BitMap(), BitMap()), with the first BitMap
        # containing element that have been visited for the `_Scope.BUILD` case
        # and the second one relating to the `_Scope.RUN` case.
        if not recurse:
            result: Set["Element"] = set()
            if scope in (_Scope.BUILD, _Scope.ALL):
                for dep in self.__build_dependencies:
                    if dep not in result:
                        result.add(dep)
                        yield dep
            if scope in (_Scope.RUN, _Scope.ALL):
                for dep in self.__runtime_dependencies:
                    if dep not in result:
                        result.add(dep)
                        yield dep
        else:

            def visit(element, scope, visited):
                if scope == _Scope.ALL:
                    visited[0].add(element._unique_id)
                    visited[1].add(element._unique_id)

                    for dep in chain(element.__build_dependencies, element.__runtime_dependencies):
                        if dep._unique_id not in visited[0] and dep._unique_id not in visited[1]:
                            yield from visit(dep, _Scope.ALL, visited)

                    yield element
                elif scope == _Scope.BUILD:
                    visited[0].add(element._unique_id)

                    for dep in element.__build_dependencies:
                        if dep._unique_id not in visited[1]:
                            yield from visit(dep, _Scope.RUN, visited)

                elif scope == _Scope.RUN:
                    visited[1].add(element._unique_id)

                    for dep in element.__runtime_dependencies:
                        if dep._unique_id not in visited[1]:
                            yield from visit(dep, _Scope.RUN, visited)

                    yield element
                else:
                    yield element

            if visited is None:
                # Visited is of the form (Visited for _Scope.BUILD, Visited for _Scope.RUN)
                visited = (BitMap(), BitMap())
            else:
                # We have already a visited set passed. we might be able to short-circuit
                if scope in (_Scope.BUILD, _Scope.ALL) and self._unique_id in visited[0]:
                    return
                if scope in (_Scope.RUN, _Scope.ALL) and self._unique_id in visited[1]:
                    return

            yield from visit(self, scope, visited)

    # _search()
    #
    # Search for a dependency by name
    #
    # Args:
    #    scope (_Scope): The scope to search
    #    name (str): The dependency to search for
    #
    # Returns:
    #    (Element): The dependency element, or None if not found.
    #
    def _search(self, scope, name):

        for dep in self._dependencies(scope):
            if dep.name == name:
                return dep

        return None

    # _stage_artifact()
    #
    # Stage this element's output artifact in the sandbox
    #
    # This will stage the files from the artifact to the sandbox at specified location.
    # The files are selected for staging according to the `include`, `exclude` and `orphans`
    # parameters; if `include` is not specified then all files spoken for by any domain
    # are included unless explicitly excluded with an `exclude` domain.
    #
    # Args:
    #    sandbox: The build sandbox
    #    path: An optional sandbox relative path
    #    action (OverlapAction): The action to take when overlapping with previous invocations
    #    include: An optional list of domains to include files from
    #    exclude: An optional list of domains to exclude files from
    #    orphans: Whether to include files not spoken for by split domains
    #    owner: The session element currently running Element.stage()
    #
    # Raises:
    #    (:class:`.ElementError`): If the element has not yet produced an artifact.
    #
    # Returns:
    #    The result describing what happened while staging
    #
    def _stage_artifact(
        self,
        sandbox: "Sandbox",
        *,
        path: str = None,
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True,
        owner: Optional["Element"] = None,
    ) -> FileListResult:

        owner = owner or self
        assert owner._overlap_collector is not None, "Attempted to stage artifacts outside of Element.stage()"

        if not self._cached():
            detail = (
                "No artifacts have been cached yet for that element\n"
                + "Try building the element first with `bst build`\n"
            )
            raise ElementError("No artifacts to stage", detail=detail, reason="uncached-checkout-attempt")

        # Time to use the artifact, check once more that it's there
        self.__assert_cached()

        self.status("Staging {}/{}".format(self.name, self._get_display_key().brief))
        # Disable type checking since we can't easily tell mypy that
        # `self.__artifact` can't be None at this stage.
        files_vdir = self.__artifact.get_files()  # type: ignore

        # Import files into the staging area
        #
        vbasedir = sandbox.get_virtual_directory()
        vstagedir = vbasedir if path is None else vbasedir.open_directory(path.lstrip(os.sep), create=True)

        split_filter = self.__split_filter_func(include, exclude, orphans)

        result = vstagedir._import_files_internal(files_vdir, filter_callback=split_filter)
        assert result is not None

        owner._overlap_collector.collect_stage_result(self, result)

        return result

    # _stage_dependency_artifacts()
    #
    # Stage element dependencies in scope, this is used for core
    # functionality especially in the CLI which wants to stage specifically
    # build or runtime dependencies.
    #
    # Args:
    #    sandbox: The build sandbox
    #    scope (_Scope): The scope of artifacts to stage
    #    path An optional sandbox relative path
    #    include: An optional list of domains to include files from
    #    exclude: An optional list of domains to exclude files from
    #    orphans: Whether to include files not spoken for by split domains
    #
    # Raises:
    #    (:class:`.ElementError`): If any of the dependencies in `scope` have not
    #                              yet produced artifacts, or if forbidden overlaps
    #                              occur.
    #
    def _stage_dependency_artifacts(self, sandbox, scope, *, path=None, include=None, exclude=None, orphans=True):
        with self._overlap_collector.session(OverlapAction.WARNING, path):
            for dep in self._dependencies(scope):
                dep._stage_artifact(sandbox, path=path, include=include, exclude=exclude, orphans=orphans, owner=self)

    # _new_from_load_element():
    #
    # Recursively instantiate a new Element instance, its sources
    # and its dependencies from a LoadElement.
    #
    # FIXME: Need to use an iterative algorithm here since recursion
    #        will limit project dependency depth.
    #
    # Args:
    #    load_element (LoadElement): The LoadElement
    #    task (Task): A task object to report progress to
    #
    # Returns:
    #    (Element): A newly created Element instance
    #
    @classmethod
    def _new_from_load_element(cls, load_element, task=None):

        if not load_element.first_pass:
            load_element.project.ensure_fully_loaded()

        with suppress(KeyError):
            return cls.__instantiated_elements[load_element]

        element = load_element.project.create_element(load_element)
        cls.__instantiated_elements[load_element] = element

        # If the element implements configure_dependencies(), we will collect
        # the dependency configurations for it, otherwise we will consider
        # it an error to specify `config` on dependencies.
        #
        if element.configure_dependencies.__func__ is not Element.configure_dependencies:
            custom_configurations = []
        else:
            custom_configurations = None

        # Load the sources from the LoadElement
        element.__load_sources(load_element)

        # Instantiate dependencies
        for dep in load_element.dependencies:
            dependency = Element._new_from_load_element(dep.element, task)

            if dep.dep_type & DependencyType.BUILD:
                element.__build_dependencies.append(dependency)
                dependency.__reverse_build_deps.add(element)

                # Configuration data is only collected for build dependencies,
                # if configuration data is specified on a runtime dependency
                # then the assertion will be raised by the LoadElement.
                #
                if custom_configurations is not None:

                    # Create a proxy for the dependency
                    dep_proxy = cast("Element", ElementProxy(element, dependency))

                    # Class supports dependency configuration
                    if dep.config_nodes:

                        # Ensure variables are substituted first
                        #
                        for config in dep.config_nodes:
                            element.__variables.expand(config)

                        custom_configurations.extend(
                            [DependencyConfiguration(dep_proxy, dep.path, config) for config in dep.config_nodes]
                        )
                    else:
                        custom_configurations.append(DependencyConfiguration(dep_proxy, dep.path, None))

                elif dep.config_nodes:
                    # Class does not support dependency configuration
                    provenance = dep.config_nodes[0].get_provenance()
                    raise LoadError(
                        "{}: Custom dependency configuration is not supported by element plugin '{}'".format(
                            provenance, element.get_kind()
                        ),
                        LoadErrorReason.INVALID_DEPENDENCY_CONFIG,
                    )

            if dep.dep_type & DependencyType.RUNTIME:
                element.__runtime_dependencies.append(dependency)
                dependency.__reverse_runtime_deps.add(element)

            if dep.strict:
                element.__strict_dependencies.append(dependency)

        no_of_runtime_deps = len(element.__runtime_dependencies)
        element.__runtime_deps_uncached = no_of_runtime_deps

        no_of_build_deps = len(element.__build_dependencies)
        element.__build_deps_uncached = no_of_build_deps

        if custom_configurations is not None:
            element.configure_dependencies(custom_configurations)

        element.__preflight()

        element._initialize_state()

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
    # This is used to reset the loader state across multiple load sessions.
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
        # This check must be before `_fetch_needed()` as source cache status
        # is not always available for non-build pipelines.
        if not self.__assemble_scheduled:
            return False

        if self._fetch_needed():
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
        return self.__artifact is not None

    # _can_query_source_cache():
    #
    # Returns whether the source cache status is available.
    #
    # Returns:
    #    (bool): True if source cache can be queried
    #
    def _can_query_source_cache(self):
        return self.__sources.can_query_cache()

    # _initialize_state()
    #
    # Compute up the elment's initial state. Element state contains
    # the following mutable sub-states:
    #
    # - Source state in `ElementSources`
    # - Artifact cache key
    #   - Source key in `ElementSources`
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
    # - __update_cache_keys()
    #   - Computes the strong and weak cache keys.
    # - __schedule_assembly_when_necessary()
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
    # After initializing the source state via `ElementSources`,
    # *this* method starts the process by invoking
    # `__update_cache_keys()`, which will cause all necessary state
    # changes. Other functions should use the appropriate methods and
    # only update what they expect to change - this will ensure that
    # the minimum amount of work is done.
    #
    def _initialize_state(self):
        if self.__resolved_initial_state:
            return
        self.__resolved_initial_state = True

        # This will initialize source state.
        self.__sources.update_resolved_state()

        # This will calculate the cache keys, and for un-initialized
        # elements recursively initialize anything else (because it
        # will become considered outdated after cache keys are
        # updated).
        self.__update_cache_keys()

    # _get_display_key():
    #
    # Returns cache keys for display purposes
    #
    # Returns:
    #    (_DisplayKey): The display key
    #
    # Question marks are returned if information for the cache key is missing.
    #
    def _get_display_key(self):
        context = self._get_context()
        strict = False

        cache_key = self._get_cache_key()

        if not cache_key:
            cache_key = "{:?<64}".format("")
        elif cache_key == self.__strict_cache_key:
            # Strong cache key used in this session matches cache key
            # that would be used in strict build mode
            strict = True

        length = min(len(cache_key), context.log_key_length)
        return _DisplayKey(cache_key, cache_key[0:length], strict)

    # _tracking_done():
    #
    # This is called in the main process after the element has been tracked
    #
    def _tracking_done(self):
        # Tracking may change the sources' refs, and therefore the
        # source state. We need to update source state.
        self.__sources.update_resolved_state()
        self.__update_cache_keys()

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
        return self.__sources.track(self._get_workspace())

    # _prepare_sandbox():
    #
    # This stages things for either _shell() (below) or also
    # is used to stage things by the `bst artifact checkout` codepath
    #
    @contextmanager
    def _prepare_sandbox(self, scope, shell=False, integrate=True, usebuildtree=False):

        # Assert first that we have a sandbox configuration
        if not self.__sandbox_config:
            raise ElementError(
                "Error preparing sandbox for element: {}".format(self.name),
                detail="This is most likely an artifact that is not yet cached, try building or pulling the artifact first",
                reason="missing-sandbox-config",
            )

        # bst shell and bst artifact checkout require a local sandbox.
        with self.__sandbox(None, config=self.__sandbox_config, allow_remote=False) as sandbox:

            # Configure always comes first, and we need it.
            self.__configure_sandbox(sandbox)

            if usebuildtree:
                # Use the cached buildroot directly
                buildrootvdir = self.__artifact.get_buildroot()
                sandbox_vroot = sandbox.get_virtual_directory()
                sandbox_vroot._import_files_internal(buildrootvdir, collect_result=False)
            elif shell and scope == _Scope.BUILD:
                # Stage what we need
                self.__stage(sandbox)
            else:
                # Stage deps in the sandbox root
                with self.timed_activity("Staging dependencies", silent_nested=True), self.__collect_overlaps():
                    self._stage_dependency_artifacts(sandbox, scope)

                # Run any integration commands provided by the dependencies
                # once they are all staged and ready
                if integrate:
                    with self.timed_activity("Integrating sandbox"), sandbox.batch():
                        for dep in self._dependencies(scope):
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
        host_vdirectory = sandbox_vroot.open_directory(directory.lstrip(os.sep), create=True)
        self._stage_sources_at(host_vdirectory)

    # _stage_sources_at():
    #
    # Stage this element's sources to a directory
    #
    # Args:
    #     vdirectory (Union[str, Directory]): A virtual directory object or local path to stage sources to.
    #
    def _stage_sources_at(self, vdirectory):

        # It's advantageous to have this temporary directory on
        # the same file system as the rest of our cache.
        with self.timed_activity("Staging sources", silent_nested=True):

            if not isinstance(vdirectory, Directory):
                vdirectory = FileBasedDirectory(vdirectory)
            if vdirectory:
                raise ElementError("Staging directory '{}' is not empty".format(vdirectory))

            # stage sources from source cache
            staged_sources = self.__sources.get_files()

            # incremental builds should merge the source into the last artifact before staging
            last_build_artifact = self.__get_last_build_artifact()
            if last_build_artifact:
                self.info("Incremental build")
                last_sources = last_build_artifact.get_sources()
                import_dir = last_build_artifact.get_buildtree()
                import_dir._apply_changes(last_sources, staged_sources)
            else:
                import_dir = staged_sources

            # Set update_mtime to ensure deterministic mtime of sources at build time
            vdirectory._import_files_internal(import_dir, update_mtime=BST_ARBITRARY_TIMESTAMP, collect_result=False)

        # Ensure deterministic owners of sources at build time
        vdirectory._set_deterministic_user()

    # _set_required():
    #
    # Mark this element and its dependencies as required.
    # This unblocks pull/fetch/build.
    #
    # Args:
    #    scope (_Scope): The scope of dependencies to mark as required
    #
    def _set_required(self, scope=_Scope.RUN):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        if self.__required:
            # Already done
            return

        self.__required = True

        # Request artifacts of dependencies
        for dep in self._dependencies(scope, recurse=False):
            dep._set_required(scope=_Scope.RUN)

        # When an element becomes required, it must be assembled for
        # the current pipeline. `__schedule_assembly_when_necessary()`
        # will abort if some other state prevents it from being built,
        # and changes to such states will cause re-scheduling, so this
        # is safe.
        self.__schedule_assembly_when_necessary()

        # Callback to the Queue
        if self.__required_callback is not None:
            self.__required_callback(self)
            self.__required_callback = None

    # _is_required():
    #
    # Returns whether this element has been marked as required.
    #
    def _is_required(self):
        return self.__required

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
            # We're required for the current build
            self._is_required()
            and
            # We have figured out the state of our artifact
            self.__artifact
            and
            # And we're not cached yet
            not self._cached_success()
        )

    # __schedule_assembly_when_necessary():
    #
    # This is called in the main process before the element is assembled
    # in a subprocess.
    #
    def __schedule_assembly_when_necessary(self):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

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
        for dep in self._dependencies(_Scope.BUILD, recurse=False):
            dep._set_required()

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
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        self.__assemble_done = True

        if successful:
            # Directly set known cached status as optimization to avoid
            # querying buildbox-casd and the filesystem.
            self.__artifact.set_cached()
            self.__cached_successfully = True
        else:
            self.__artifact.query_cache()

        # When we're building in non-strict mode, we may have
        # assembled everything to this point without a strong cache
        # key. Once the element has been assembled, a strong cache key
        # can be set, so we do so.
        self.__update_cache_key_non_strict()
        self._update_ready_for_runtime_and_cached()

        if self._get_workspace() and self._cached():
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
    def _assemble(self):

        # Only do this the first time around (i.e. __assemble_done is False)
        # to allow for retrying the job
        if self._cached_failure() and not self.__assemble_done:
            with self._output_file() as output_file:
                for log_path in self.__artifact.get_logs():
                    with open(log_path, encoding="utf-8") as log_file:
                        output_file.write(log_file.read())

            _, description, detail = self._get_build_result()
            e = CachedFailure(description, detail=detail)
            # Shelling into a sandbox is useful to debug this error
            e.sandbox = True
            raise e

        # Assert call ordering
        assert not self._cached_success()

        # Print the environment at the beginning of the log file.
        env_dump = _yaml.roundtrip_dump_string(self.get_environment())

        self.log("Build environment for element {}".format(self.name), detail=env_dump)

        context = self._get_context()
        with self._output_file() as output_file:

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)

            with utils._tempdir(
                prefix="{}-".format(self.normal_name), dir=context.builddir
            ) as rootdir, self.__sandbox(
                rootdir, output_file, output_file, self.__sandbox_config
            ) as sandbox:  # noqa

                # Ensure that the plugin does not run commands if it said that it wouldn't
                #
                # We only disable commands here in _assemble() instead of __sandbox() because
                # the user might still run a shell on an element which itself does not run commands.
                #
                if not self.BST_RUN_COMMANDS:
                    sandbox._disable_run()

                # By default, the dynamic public data is the same as the static public data.
                # The plugin's assemble() method may modify this, though.
                self.__dynamic_public = self.__public.clone()

                # Call the abstract plugin methods

                # Step 1 - Configure
                self.__configure_sandbox(sandbox)
                # Step 2 - Stage
                self.__stage(sandbox)
                try:
                    # Step 3 - Assemble
                    collect = self.assemble(sandbox)  # pylint: disable=assignment-from-no-return

                    self.__set_build_result(success=True, description="succeeded")
                except (ElementError, SandboxCommandError) as e:
                    # Shelling into a sandbox is useful to debug this error
                    e.sandbox = True

                    self.__set_build_result(success=False, description=str(e), detail=e.detail)
                    self._cache_artifact(sandbox, e.collect)

                    raise
                else:
                    self._cache_artifact(sandbox, collect)

    def _cache_artifact(self, sandbox, collect):

        context = self._get_context()
        buildresult = self.__build_result
        publicdata = self.__dynamic_public
        sandbox_vroot = sandbox.get_virtual_directory()
        collectvdir = None
        sandbox_build_dir = None
        sourcesvdir = None
        buildrootvdir = None

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
                sandbox_build_dir = sandbox_vroot.open_directory(self.get_variable("build-root").lstrip(os.sep))
                sandbox._fetch_missing_blobs(sandbox_build_dir)
            except DirectoryError:
                # Directory could not be found. Pre-virtual
                # directory behaviour was to continue silently
                # if the directory could not be found.
                pass

            buildrootvdir = sandbox_vroot
            sourcesvdir = self.__sources.get_files()

        if collect is not None:
            try:
                collectvdir = sandbox_vroot.open_directory(collect.lstrip(os.sep))
                sandbox._fetch_missing_blobs(collectvdir)
            except DirectoryError:
                pass

        # We should always have cache keys already set when caching an artifact
        assert self.__cache_key is not None
        assert self.__artifact._cache_key is not None

        with self.timed_activity("Caching artifact"):
            self.__artifact.cache(
                buildrootvdir=buildrootvdir,
                sandbox_build_dir=sandbox_build_dir,
                collectvdir=collectvdir,
                sourcesvdir=sourcesvdir,
                buildresult=buildresult,
                publicdata=publicdata,
                variables=self.__variables,
                environment=self.__environment,
                sandboxconfig=self.__sandbox_config,
            )

        if collect is not None and collectvdir is None:
            raise ElementError(
                "Directory '{}' was not found inside the sandbox, "
                "unable to collect artifact contents".format(collect)
            )

    # _fetch_done()
    #
    # Indicates that fetching the sources for this element has been done.
    #
    # Args:
    #   fetched_original (bool): Whether the original sources had been asked (and fetched) or not
    #
    def _fetch_done(self, fetched_original):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        self.__sources.fetch_done(fetched_original)

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
        return self.__pull_pending

    # _load_artifact_done()
    #
    # Indicate that `_load_artifact()` has completed.
    #
    # This needs to be called in the main process after `_load_artifact()`
    # succeeds or fails so that we properly update the main
    # process data model
    #
    # This will result in updating the element state.
    #
    def _load_artifact_done(self):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        assert self.__artifact

        context = self._get_context()

        if not context.get_strict() and self.__artifact.cached():
            # In non-strict mode, strong cache key becomes available when
            # the artifact is cached
            self.__update_cache_key_non_strict()

        self._update_ready_for_runtime_and_cached()

        self.__schedule_assembly_when_necessary()

        if self.__can_query_cache_callback is not None:
            self.__can_query_cache_callback(self)
            self.__can_query_cache_callback = None

    # _load_artifact():
    #
    # Load artifact from cache or pull it from remote artifact repository.
    #
    # Args:
    #    pull (bool): Whether to attempt to pull the artifact
    #    strict (bool|None): Force strict/non-strict operation
    #
    # Returns: True if the artifact has been downloaded, False otherwise
    #
    def _load_artifact(self, *, pull, strict=None):
        context = self._get_context()

        if strict is None:
            strict = context.get_strict()

        pull_buildtrees = context.pull_buildtrees and not self._get_workspace()

        # First check whether we already have the strict artifact in the local cache
        artifact = Artifact(
            self,
            context,
            strict_key=self.__strict_cache_key,
            strong_key=self.__strict_cache_key,
            weak_key=self.__weak_cache_key,
        )
        artifact.query_cache()

        self.__pull_pending = False
        if not pull and not artifact.cached(buildtree=pull_buildtrees):
            if self.__artifacts.has_fetch_remotes(plugin=self) and not self._get_workspace():
                # Artifact is not completely available in cache and artifact remote server is available.
                # Stop artifact loading here as pull is required to proceed.
                self.__pull_pending = True

        # Attempt to pull artifact with the strict cache key
        pulled = pull and artifact.pull(pull_buildtrees=pull_buildtrees)

        if artifact.cached() or strict:
            self.__artifact = artifact
            return pulled
        elif self.__pull_pending:
            return False

        # In non-strict mode retry with weak cache key
        artifact = Artifact(self, context, strict_key=self.__strict_cache_key, weak_key=self.__weak_cache_key)
        artifact.query_cache()

        # Attempt to pull artifact with the weak cache key
        pulled = pull and artifact.pull(pull_buildtrees=pull_buildtrees)

        # Automatically retry building failed builds in non-strict mode, because
        # dependencies may have changed since the last build which might cause this
        # failed build to succeed.
        #
        # When not building (e.g. `bst show`, `bst artifact push` etc), we do not drop
        # the failed artifact, the retry only occurs at build time.
        #
        if context.build and artifact.cached():
            success, _, _ = artifact.load_build_result()
            if not success:
                #
                # If we could resolve the stong cache key for this element at this time,
                # we could compare the artifact key against the resolved strong key.
                #
                # If we could assert that artifact state is never consulted in advance
                # of resolving the strong key, then we could discard the loaded artifact
                # at that time instead.
                #
                # Since neither of these are true, we settle for always retrying a failed
                # build in non-strict mode unless the failed artifact's strong key is
                # equal to the resolved strict key.
                #
                if artifact.strong_key != self.__strict_cache_key:
                    artifact = Artifact(
                        self,
                        context,
                        strict_key=self.__strict_cache_key,
                        weak_key=self.__weak_cache_key,
                    )
                    artifact._cached = False
                    pulled = False

        self.__artifact = artifact
        return pulled

    def _query_source_cache(self):
        self.__sources.query_cache()

    def _skip_source_push(self):
        if not self.sources() or self._get_workspace():
            return True
        return not (self.__sourcecache.has_push_remotes(plugin=self) and self._cached_sources())

    def _source_push(self):
        return self.__sources.push()

    # _skip_push():
    #
    # Determine whether we should create a push job for this element.
    #
    # Args:
    #    skip_uncached (bool): Whether to skip elements that aren't cached
    #
    # Returns:
    #   (bool): True if this element does not need a push job to be created
    #
    def _skip_push(self, *, skip_uncached):
        if not self.__artifacts.has_push_remotes(plugin=self):
            # No push remotes for this element's project
            return True

        # Do not push elements that aren't cached, or that are cached with a dangling buildtree
        # ref unless element type is expected to have an an empty buildtree directory
        if skip_uncached:
            if not self._cached():
                return True
            if not self._cached_buildtree() and self._buildtree_exists():
                return True
            if not self._cached_buildroot() and self._buildroot_exists():
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
        if not self._cached():
            raise ElementError("Push failed: {} is not cached".format(self.name))

        # Do not push elements that are cached with a dangling buildtree ref
        # unless element type is expected to have an an empty buildtree directory
        if not self._cached_buildtree() and self._buildtree_exists():
            raise ElementError("Push failed: buildtree of {} is not cached".format(self.name))

        if not self._cached_buildroot() and self._buildroot_exists():
            raise ElementError("Push failed: buildroot of {} is not cached".format(self.name))

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
    #    scope (_Scope): Either BUILD or RUN scopes are valid, or None
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
            flags = _SandboxFlags.INTERACTIVE | _SandboxFlags.ROOT_READ_ONLY

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
                flags |= _SandboxFlags.NETWORK_ENABLED | _SandboxFlags.INHERIT_UID

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
            return sandbox._run_with_flags(argv, flags=flags, env=environment)

    # _open_workspace():
    #
    # "Open" a workspace for this element
    #
    # This requires that a workspace already be created in
    # the workspaces metadata first.
    #
    def _open_workspace(self):
        assert utils._is_in_main_thread(), "This writes to a global file and therefore must be run in the main thread"

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
            self.__sources.init_workspace(temp)

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
        with open(_site.build_module_template, "r", encoding="utf-8") as f:
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

    # _cached_buildroot()
    #
    # Check if element artifact contains expected buildroot. An
    # element's buildroot artifact will not be present if the rest
    # of the partial artifact is not cached.
    #
    # Returns:
    #     (bool): True if artifact cached with buildroot, False if
    #             element not cached or missing expected buildroot.
    #             Note this only confirms if a buildroot is present,
    #             not its contents.
    #
    def _cached_buildroot(self):
        if not self._cached():
            return False

        return self.__artifact.cached_buildroot()

    # _buildroot_exists()
    #
    # Check if artifact was created with a buildroot. This does not check
    # whether the buildroot is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildroot, False if
    #             element not cached or not created with a buildroot.
    #
    def _buildroot_exists(self):
        if not self._cached():
            return False

        return self.__artifact.buildroot_exists()

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
        if fetch_original:
            self.__sources.fetch_sources(fetch_original=True)

        self.__sources.fetch()

        if not self.__sources.cached():
            try:
                # Stage all element sources into CAS
                self.__sources.stage_and_cache()
            except (SourceCacheError, DirectoryError) as e:
                raise ElementError(
                    "Error trying to stage sources for {}: {}".format(self.name, e), reason="stage-sources-fail"
                )

    # _calculate_cache_key():
    #
    # Calculates the cache key
    #
    # Args:
    #    dependencies (List[List[str]]): list of dependencies with project name,
    #                                    element name and optional cache key
    #    weak_cache_key (Optional[str]): the weak cache key, required for calculating the
    #                                    strict and strong cache keys
    #
    # Returns:
    #    (str): A hex digest cache key for this Element, or None
    #
    # None is returned if information for the cache key is missing.
    #
    def _calculate_cache_key(self, dependencies, weak_cache_key=None):
        # No cache keys for dependencies which have no cache keys
        if any(not all(dep) for dep in dependencies):
            return None

        # Generate dict that is used as base for all cache keys
        if self.__cache_key_dict is None:
            project = self._get_project()

            self.__cache_key_dict = {
                "core-artifact-version": BST_CORE_ARTIFACT_VERSION,
                "element-base-key": self.__get_base_key(),
                "element-plugin-key": self.get_unique_key(),
                "element-plugin-name": self.get_kind(),
                "element-plugin-version": self.BST_ARTIFACT_VERSION,
                "public": self.__public.strip_node_info(),
            }

            self.__cache_key_dict["sources"] = self.__sources.get_unique_key()
            self.__cache_key_dict["fatal-warnings"] = sorted(project._fatal_warnings)

            # Calculate sandbox related factors if this element runs the sandbox at assemble time.
            if self.BST_RUN_COMMANDS:
                # Filter out nocache variables from the element's environment
                cache_env = {key: value for key, value in self.__environment.items() if key not in self.__env_nocache}
                self.__cache_key_dict["sandbox"] = self.__sandbox_config.to_dict()
                self.__cache_key_dict["environment"] = cache_env

        cache_key_dict = self.__cache_key_dict.copy()
        cache_key_dict["dependencies"] = dependencies
        if weak_cache_key is not None:
            cache_key_dict["weak-cache-key"] = weak_cache_key

        return _cachekey.generate_key(cache_key_dict)

    # _cached_sources()
    #
    # Get whether the staged element sources are cached in CAS
    #
    # Returns:
    #    (bool): True if the element sources are in CAS
    #
    def _cached_sources(self):
        return self.__sources.cached()

    # _has_all_sources_resolved()
    #
    # Get whether all sources of the element are resolved
    #
    # Returns:
    #    (bool): True if all element sources are resolved
    #
    def _has_all_sources_resolved(self):
        return self.__sources.is_resolved()

    # _fetch_needed():
    #
    # Return whether sources need to be fetched from a remote
    #
    # Returns:
    #    (bool): True if one or more element sources need to be fetched
    #
    def _fetch_needed(self):
        return not self.__sources.cached() and not self.__sources.cached_original()

    # _should_fetch():
    #
    # Return whether we need to run the fetch stage for this element
    #
    # Args:
    #    fetch_original (bool): whether we need the original unstaged source
    #
    # Returns:
    #    (bool): True if a fetch job is required
    #
    def _should_fetch(self, fetch_original=False):
        if fetch_original:
            return not self.__sources.cached_original()
        return not self.__sources.cached()

    # _set_required_callback()
    #
    #
    # Notify the pull/fetch/build queue that the element is potentially
    # ready to be processed.
    #
    # _Set the _required_callback - the _required_callback is invoked when an
    # element is marked as required. This informs us that the element needs to
    # either be pulled or fetched + built.
    #
    # Args:
    #    callback (callable) - The callback function
    #
    def _set_required_callback(self, callback):
        self.__required_callback = callback

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
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        if not self.__ready_for_runtime_and_cached:
            if self.__runtime_deps_uncached == 0 and self.__artifact and self.__cache_key and self._cached_success():
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

                    if rdep._buildable():
                        rdep.__update_cache_key_non_strict()

                        if rdep.__buildable_callback is not None:
                            rdep.__buildable_callback(rdep)
                            rdep.__buildable_callback = None

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

    # _mimic_artifact()
    #
    # Assume the state dictated by the currently set artifact.
    #
    # This is used both when initializing an Element's state
    # from a loaded artifact, or after pulling the artifact from
    # a remote.
    #
    def _mimic_artifact(self):
        artifact = self._get_artifact()

        # Load bits which have been stored on the artifact
        #
        if artifact.cached():
            self.__environment = artifact.load_environment()
            self.__sandbox_config = artifact.load_sandbox_config()
            self.__variables = artifact.load_variables()

        self.__cache_key = artifact.strong_key
        self.__strict_cache_key = artifact.strict_key
        self.__weak_cache_key = artifact.weak_key

    # _add_build_dependency()
    #
    # Add a build dependency to the Element
    #
    # Args:
    #    (Element): The Element to add as a build dependency
    #
    def _add_build_dependency(self, dependency):
        self.__build_dependencies.append(dependency)

    # _file_is_whitelisted()
    #
    # Checks if a file is whitelisted in the overlap whitelist
    #
    # This is only internal (one underscore) and not locally private
    # because it needs to be proxied through ElementProxy.
    #
    # Args:
    #    path (str): The path to check
    #
    # Returns:
    #    (bool): True of the specified `path` is whitelisted
    #
    def _file_is_whitelisted(self, path):
        # Considered storing the whitelist regex for re-use, but public data
        # can be altered mid-build.
        # Public data is not guaranteed to stay the same for the duration of
        # the build, but I can think of no reason to change it mid-build.
        # If this ever changes, things will go wrong unexpectedly.
        if not self.__whitelist_regex:
            bstdata = self.get_public_data("bst")
            whitelist = bstdata.get_sequence("overlap-whitelist", default=[])
            whitelist_expressions = [utils._glob2re(self.__variables.subst(node)) for node in whitelist]
            expression = "^(?:" + "|".join(whitelist_expressions) + ")$"
            self.__whitelist_regex = re.compile(expression, re.MULTILINE | re.DOTALL)
        return self.__whitelist_regex.match(os.path.join(os.sep, path))

    # _get_logs()
    #
    # Obtain a list of log file paths
    #
    # Returns:
    #    A list of log file paths
    #
    def _get_logs(self) -> List[str]:
        return cast(Artifact, self.__artifact).get_logs()

    #############################################################
    #                   Private Local Methods                   #
    #############################################################

    # __get_proxy()
    #
    # Obtain a proxy for this element for the specified `owner`.
    #
    # We cache the proxies for plugin convenience, this allows plugins
    # compare proxies to other proxies returned to them, so they
    # can run valid statements such as `proxy_a is `proxy_b` or
    # `proxy_a in list_of_proxies`.
    #
    # Args:
    #    owner (Element): The owning element
    #
    # Returns:
    #    (ElementProxy): An ElementProxy to self, for owner.
    #
    def __get_proxy(self, owner: "Element") -> ElementProxy:
        with suppress(KeyError):
            return self.__proxies[owner]

        proxy = ElementProxy(owner, self)
        self.__proxies[owner] = proxy
        return proxy

    # __load_sources()
    #
    # Load the Source objects from the LoadElement
    #
    def __load_sources(self, load_element):
        project = self._get_project()
        workspace = self._get_workspace()
        meta_sources = []

        # If there's a workspace for this element then we just load a workspace
        # source plugin instead of the real plugins
        if workspace:
            workspace_node = {"kind": "workspace"}
            workspace_node["path"] = workspace.get_absolute_path()
            workspace_node["last_build"] = str(workspace.to_dict().get("last_build", ""))
            meta = MetaSource(
                self.name,
                0,
                self.get_kind(),
                "workspace",
                Node.from_dict(workspace_node),
                None,
                load_element.first_pass,
            )
            meta_sources.append(meta)
        else:
            sources = load_element.node.get_sequence(Symbol.SOURCES, default=[])
            for index, source in enumerate(sources):
                kind = source.get_scalar(Symbol.KIND)

                # The workspace source plugin is only valid for internal use
                if kind.as_str() == "workspace":
                    raise LoadError(
                        "{}: Invalid usage of workspace source kind".format(kind.get_provenance()),
                        LoadErrorReason.INVALID_DATA,
                    )
                del source[Symbol.KIND]

                # Directory is optional
                directory = source.get_str(Symbol.DIRECTORY, default=None)
                if directory:
                    del source[Symbol.DIRECTORY]
                meta_source = MetaSource(
                    self.name, index, self.get_kind(), kind.as_str(), source, directory, load_element.first_pass
                )
                meta_sources.append(meta_source)

        for meta_source in meta_sources:
            source = project.create_source(meta_source, variables=self.__variables)
            redundant_ref = source._load_ref()

            self.__sources.add_source(source)

            # Collect redundant refs which occurred at load time
            if redundant_ref is not None:
                self.__redundant_source_refs.append((source, redundant_ref))

    # __get_dependency_artifact_names()
    #
    # Retrieve the artifact names of all of the dependencies in _Scope.BUILD
    #
    # Returns:
    #    (list [str]): A list of refs of all dependencies in staging order.
    #
    def __get_dependency_artifact_names(self):
        return [
            os.path.join(dep.project_name, _get_normal_name(dep.name), dep._get_cache_key())
            for dep in self._dependencies(_Scope.BUILD)
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
        artifact.query_cache()

        if not artifact.cached():
            return None

        if not artifact.cached_buildtree():
            return None

        if not artifact.cached_sources():
            return None

        # Don't perform an incremental build if there has been a change in
        # build dependencies.
        old_dep_refs = artifact.get_dependency_artifact_names()
        new_dep_refs = self.__get_dependency_artifact_names()
        if old_dep_refs != new_dep_refs:
            return None

        return artifact

    # __configure_sandbox():
    #
    # Internal method for calling public abstract configure_sandbox() method.
    #
    def __configure_sandbox(self, sandbox):

        self.configure_sandbox(sandbox)

    # __stage():
    #
    # Internal method for calling public abstract stage() method.
    #
    def __stage(self, sandbox):

        # Enable the overlap collector during the staging process
        with self.__collect_overlaps():
            self.stage(sandbox)

    # __preflight():
    #
    # A internal wrapper for calling the abstract preflight() method on
    # the element and its sources.
    #
    def __preflight(self):

        if self.BST_FORBID_RDEPENDS and self.BST_FORBID_BDEPENDS:
            if any(self._dependencies(_Scope.RUN, recurse=False)) or any(
                self._dependencies(_Scope.BUILD, recurse=False)
            ):
                raise ElementError(
                    "{}: Dependencies are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-depends",
                )

        if self.BST_FORBID_RDEPENDS:
            if any(self._dependencies(_Scope.RUN, recurse=False)):
                raise ElementError(
                    "{}: Runtime dependencies are forbidden for '{}' elements".format(self, self.get_kind()),
                    reason="element-forbidden-rdepends",
                )

        if self.BST_FORBID_BDEPENDS:
            if any(self._dependencies(_Scope.BUILD, recurse=False)):
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

        self.__sources.preflight()

    # __get_base_key()
    #
    # Gets the base key for this element, the base key
    # is the part of the cache key which is element instance
    # specific and automatically generated by BuildStream core.
    #
    def __get_base_key(self):
        return {
            "build-root": self.get_variable("build-root"),
        }

    # __assert_cached()
    #
    # Raises an error if the artifact is not cached.
    #
    def __assert_cached(self):
        assert self._cached(), "{}: Missing artifact {}".format(self, self._get_display_key().brief)

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

    # __collect_overlaps():
    #
    # A context manager for collecting overlap warnings and errors.
    #
    # Any places where code might call Element.stage_artifact()
    # or Element.stage_dependency_artifacts() should be run in
    # this context manager.
    #
    @contextmanager
    def __collect_overlaps(self):
        self._overlap_collector = OverlapCollector(self)
        yield
        self._overlap_collector = None

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
            output_node_properties = ["mtime"]
        else:
            output_node_properties = None

        if directory is not None and allow_remote and context.remote_execution_specs:

            self.info("Using a remote sandbox for artifact {} with directory '{}'".format(self.name, directory))

            with SandboxRemote(
                context,
                project,
                directory,
                plugin=self,
                stdout=stdout,
                stderr=stderr,
                config=config,
                output_node_properties=output_node_properties,
            ) as sandbox:
                yield sandbox

        elif directory is not None and os.path.exists(directory):
            platform = context.platform

            sandbox = platform.create_sandbox(
                context,
                project,
                directory,
                plugin=self,
                stdout=stdout,
                stderr=stderr,
                config=config,
                output_node_properties=output_node_properties,
            )
            with sandbox:
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

    # __initialize_from_yaml()
    #
    # Normal element initialization procedure.
    #
    def __initialize_from_yaml(self, load_element: "LoadElement", plugin_conf: Dict[str, Any]):

        context = self._get_context()
        project = self._get_project()

        # Ensure we have loaded this class's defaults
        self.__init_defaults(project, plugin_conf, load_element.kind, load_element.first_pass)

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(project, load_element)
        variables["element-name"] = self.name
        self.__variables = Variables(variables)
        if not load_element.first_pass:
            self.__variables.check()

        # Collect the composited environment now that we have variables
        unexpanded_env = self.__extract_environment(project, load_element)
        self.__variables.expand(unexpanded_env)
        self.__environment = unexpanded_env.strip_node_info()

        # Collect the environment nocache blacklist list
        nocache = self.__extract_env_nocache(project, load_element)
        self.__env_nocache = nocache

        # Grab public domain data declared for this instance
        self.__public = self.__extract_public(load_element)
        self.__variables.expand(self.__public)

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__config = self.__extract_config(load_element)
        self.__variables.expand(self.__config)

        self._configure(self.__config)

        # Extract Sandbox config
        sandbox_config = self.__extract_sandbox_config(project, load_element)
        self.__variables.expand(sandbox_config)
        self.__sandbox_config = SandboxConfig.new_from_node(sandbox_config, platform=context.platform)

    # __initialize_from_artifact_key()
    #
    # Initialize the element state from an artifact key
    #
    def __initialize_from_artifact_key(self, key: str):
        # At this point we only know the key which was specified on the command line,
        # so we will pretend all keys are equal.
        #
        # If the artifact is cached, then the real keys will be loaded from the
        # artifact in `_load_artifact()` and `_load_artifact_done()`.
        #
        self.__cache_key = key
        self.__strict_cache_key = key
        self.__weak_cache_key = key

        self._initialize_state()

        # ArtifactElement requires access to the artifact early on to walk
        # dependencies.
        self._load_artifact(pull=False)

        if not self._cached():
            # Remotes are not initialized when artifact elements are loaded.
            # Always consider pull pending if the artifact is not cached.
            self.__pull_pending = True
        else:
            self._load_artifact_done()

    @classmethod
    def __compose_default_splits(cls, project, defaults, first_pass):

        element_public = defaults.get_mapping(Symbol.PUBLIC, default={})
        element_bst = element_public.get_mapping("bst", default={})
        element_splits = element_bst.get_mapping("split-rules", default={})

        if first_pass:
            splits = element_splits.clone()
        else:
            assert project.splits is not None

            splits = project.splits.clone()
            # Extend project wide split rules with any split rules defined by the element
            element_splits._composite(splits)

        element_bst["split-rules"] = splits
        element_public["bst"] = element_bst
        defaults[Symbol.PUBLIC] = element_public

    @classmethod
    def __init_defaults(cls, project, plugin_conf, kind, first_pass):
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
            cls.__compose_default_splits(project, defaults, first_pass)

            # Override the element's defaults with element specific
            # overrides from the project.conf
            if first_pass:
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
    def __extract_environment(cls, project, load_element):
        default_env = cls.__defaults.get_mapping(Symbol.ENVIRONMENT, default={})
        element_env = load_element.node.get_mapping(Symbol.ENVIRONMENT, default={}) or Node.from_dict({})

        if load_element.first_pass:
            environment = Node.from_dict({})
        else:
            environment = project.base_environment.clone()

        default_env._composite(environment)
        element_env._composite(environment)
        environment._assert_fully_composited()

        return environment

    @classmethod
    def __extract_env_nocache(cls, project, load_element):
        if load_element.first_pass:
            project_nocache = []
        else:
            project_nocache = project.base_env_nocache

        default_nocache = cls.__defaults.get_str_list(Symbol.ENV_NOCACHE, default=[])
        element_nocache = load_element.node.get_str_list(Symbol.ENV_NOCACHE, default=[])

        # Accumulate values from the element default, the project and the element
        # itself to form a complete list of nocache env vars.
        env_nocache = set(project_nocache + default_nocache + element_nocache)

        # Convert back to list now we know they're unique
        return list(env_nocache)

    # This will resolve the final variables to be used when
    # substituting command strings to be run in the sandbox
    #
    @classmethod
    def __extract_variables(cls, project, load_element):
        default_vars = cls.__defaults.get_mapping(Symbol.VARIABLES, default={})
        element_vars = load_element.node.get_mapping(Symbol.VARIABLES, default={}) or Node.from_dict({})

        if load_element.first_pass:
            variables = project.first_pass_config.base_variables.clone()
        else:
            variables = project.base_variables.clone()

        default_vars._composite(variables)
        element_vars._composite(variables)
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
    def __extract_config(cls, load_element):
        element_config = load_element.node.get_mapping(Symbol.CONFIG, default={}) or Node.from_dict({})

        # The default config is already composited with the project overrides
        config = cls.__defaults.get_mapping(Symbol.CONFIG, default={})
        config = config.clone()

        element_config._composite(config)
        config._assert_fully_composited()

        return config

    # Sandbox-specific configuration data, to be passed to the sandbox's constructor.
    #
    @classmethod
    def __extract_sandbox_config(cls, project, load_element):
        element_sandbox = load_element.node.get_mapping(Symbol.SANDBOX, default={}) or Node.from_dict({})

        if load_element.first_pass:
            sandbox_config = Node.from_dict({})
        else:
            sandbox_config = project.sandbox.clone()

        # The default config is already composited with the project overrides
        sandbox_defaults = cls.__defaults.get_mapping(Symbol.SANDBOX, default={})
        sandbox_defaults = sandbox_defaults.clone()

        sandbox_defaults._composite(sandbox_config)
        element_sandbox._composite(sandbox_config)
        sandbox_config._assert_fully_composited()

        return sandbox_config

    # This makes a special exception for the split rules, which
    # elements may extend but whos defaults are defined in the project.
    #
    @classmethod
    def __extract_public(cls, load_element):
        element_public = load_element.node.get_mapping(Symbol.PUBLIC, default={}) or Node.from_dict({})

        base_public = cls.__defaults.get_mapping(Symbol.PUBLIC, default={})
        base_public = base_public.clone()

        base_bst = base_public.get_mapping("bst", default={})
        base_splits = base_bst.get_mapping("split-rules", default={})

        element_public = element_public.clone()
        element_bst = element_public.get_mapping("bst", default={})
        element_splits = element_bst.get_mapping("split-rules", default={})

        # Allow elements to extend the default splits defined in their project or
        # element specific defaults
        element_splits._composite(base_splits)

        element_bst["split-rules"] = base_splits
        element_public["bst"] = element_bst

        element_public._assert_fully_composited()

        return element_public

    def __init_splits(self):
        bstdata = self.get_public_data("bst")
        splits = bstdata.get_mapping("split-rules")
        self.__splits = {
            domain: re.compile(
                "^(?:" + "|".join([utils._glob2re(r) for r in rules.as_str_list()]) + ")$", re.MULTILINE | re.DOTALL
            )
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

    # __update_cache_keys()
    #
    # Updates weak and strict cache keys
    #
    # Note that it does not update *all* cache keys - In non-strict mode, the
    # strong cache key is updated in __update_cache_key_non_strict()
    #
    # If the element is not resolved, this is a no-op (since inconsistent
    # elements cannot have cache keys).
    #
    # The weak and strict cache keys will be calculated if not already
    # set.
    #
    # The weak cache key is a cache key that doesn't change when the
    # content of the build dependency graph changes (e.g., the configurations
    # or source versions of each dependency in Scope.BUILD), but does
    # take the shape of the build dependency graph into account, such
    # that adding or removing a dependency will still cause a rebuild to
    # occur (except for the strict dependency and BST_STRICT_REBUILD element
    # cases which are treated specially below).
    #
    # The strict cache key is a cache key that changes if any dependencies
    # in Scope.BUILD has changed in any way.
    #
    def __update_cache_keys(self):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        if self.__strict_cache_key is not None:
            # Cache keys already calculated
            assert self.__weak_cache_key is not None
            return

        if not self._has_all_sources_resolved():
            # Tracking may still be pending
            return

        # Calculate weak cache key first, as it is required for generating the other keys.
        #
        # This code can be run multiple times until the strict key can be calculated,
        # so let's ensure we only ever calculate the weak key once, even though we need
        # to resolve it before we can resolve the strict key.
        if self.__weak_cache_key is None:
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
                for e in self._dependencies(_Scope.BUILD)
            ]
            self.__weak_cache_key = self._calculate_cache_key(dependencies)

        context = self._get_context()

        # Calculate the strict cache key
        dependencies = [[e.project_name, e.name, e.__strict_cache_key] for e in self._dependencies(_Scope.BUILD)]
        self.__strict_cache_key = self._calculate_cache_key(dependencies, self.__weak_cache_key)

        if self.__strict_cache_key is None:
            # Cache keys cannot be calculated yet as a build dependency doesn't
            # have a cache key yet.
            return

        # As the strict cache key has already been calculated, it should always
        # be possible to calculate the weak cache key as well.
        assert self.__weak_cache_key is not None

        if context.get_strict():
            # In strict mode, the strong cache key always matches the strict cache key
            self.__cache_key = self.__strict_cache_key

        # Update the message kwargs in use for this plugin to dispatch messages with
        #
        self._message_kwargs["element_key"] = self._get_display_key()

    # __update_cache_key_non_strict()
    #
    # Calculates the strong cache key if it hasn't already been set.
    #
    # When buildstream runs in strict mode, this is identical to the
    # strict cache key, so no work needs to be done.
    #
    # When buildstream is not run in strict mode, this requires the artifact
    # state (as set in Element._load_artifact()) to be set accordingly,
    # as the cache key can be loaded from the cache (possibly pulling from
    # a remote cache).
    #
    def __update_cache_key_non_strict(self):
        assert utils._is_in_main_thread(), "This has an impact on all elements and must be run in the main thread"

        # The final cache key can be None here only in non-strict mode
        if self.__cache_key is None:
            if self._pull_pending():
                # Effective strong cache key is unknown until after the pull
                pass
            elif self._cached():
                # Load the strong cache key from the artifact
                strong_key, _, _ = self.__artifact.get_metadata_keys()
                self.__cache_key = strong_key
            elif self.__assemble_scheduled or self.__assemble_done:
                # Artifact will or has been built, not downloaded
                assert self.__weak_cache_key is not None

                dependencies = [[e.project_name, e.name, e._get_cache_key()] for e in self._dependencies(_Scope.BUILD)]
                self.__cache_key = self._calculate_cache_key(dependencies, self.__weak_cache_key)

            if self.__cache_key is None:
                # Strong cache key could not be calculated yet
                return

            # The Element may have just become ready for runtime now that the
            # strong cache key has just been set
            self._update_ready_for_runtime_and_cached()

            # Now we have the strong cache key, update the Artifact
            self.__artifact._cache_key = self.__cache_key

            # Update the message kwargs in use for this plugin to dispatch messages with
            self._message_kwargs["element_key"] = self._get_display_key()


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
