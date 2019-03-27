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
from collections.abc import Mapping
import contextlib
from contextlib import contextmanager
from functools import partial
from itertools import chain
import tempfile
import string

from pyroaring import BitMap  # pylint: disable=no-name-in-module

from . import _yaml
from ._variables import Variables
from ._versions import BST_CORE_ARTIFACT_VERSION
from ._exceptions import BstError, LoadError, LoadErrorReason, ImplError, \
    ErrorDomain, SourceCacheError
from .utils import UtilError
from . import Plugin, Consistency, Scope
from . import SandboxFlags, SandboxCommandError
from . import utils
from . import _cachekey
from . import _signals
from . import _site
from ._platform import Platform
from .sandbox._config import SandboxConfig
from .sandbox._sandboxremote import SandboxRemote
from .types import _KeyStrength, CoreWarnings, _UniquePriorityQueue
from ._artifact import Artifact

from .storage.directory import Directory
from .storage._filebaseddirectory import FileBasedDirectory
from .storage.directory import VirtualDirectoryError


class ElementError(BstError):
    """This exception should be raised by :class:`.Element` implementations
    to report errors to the user.

    Args:
       message (str): The error message to report to the user
       detail (str): A possibly multiline, more detailed error message
       reason (str): An optional machine readable reason string, used for test cases
       collect (str): An optional directory containing partial install contents
       temporary (bool): An indicator to whether the error may occur if the operation was run again. (*Since: 1.2*)
    """
    def __init__(self, message, *, detail=None, reason=None, collect=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.ELEMENT, reason=reason, temporary=temporary)

        self.collect = collect


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = None             # The defaults from the yaml file and project
    __instantiated_elements = {}  # A hash of Element by MetaElement
    __redundant_source_refs = []  # A list of (source, ref) tuples which were redundantly specified

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

    *Since: 1.2*
    """

    BST_FORBID_BDEPENDS = False
    """Whether to raise exceptions if an element has build dependencies.

    *Since: 1.2*
    """

    BST_FORBID_SOURCES = False
    """Whether to raise exceptions if an element has sources.

    *Since: 1.2*
    """

    BST_VIRTUAL_DIRECTORY = False
    """Whether to raise exceptions if an element uses Sandbox.get_directory
    instead of Sandbox.get_virtual_directory.

    *Since: 1.4*
    """

    BST_RUN_COMMANDS = True
    """Whether the element may run commands using Sandbox.run.

    *Since: 1.4*
    """

    def __init__(self, context, project, meta, plugin_conf):

        self.__cache_key_dict = None            # Dict for cache key calculation
        self.__cache_key = None                 # Our cached cache key

        super().__init__(meta.name, context, project, meta.provenance, "element")

        self.__is_junction = meta.kind == "junction"

        if not self.__is_junction:
            project.ensure_fully_loaded()

        self.normal_name = os.path.splitext(self.name.replace(os.sep, '-'))[0]
        """A normalized element name

        This is the original element without path separators or
        the extension, it's used mainly for composing log file names
        and creating directory names and such.
        """

        self.__runtime_dependencies = []        # Direct runtime dependency Elements
        self.__build_dependencies = []          # Direct build dependency Elements
        self.__reverse_dependencies = set()     # Direct reverse dependency Elements
        self.__ready_for_runtime = False        # Wether the element has all its dependencies ready and has a cache key
        self.__sources = []                     # List of Sources
        self.__weak_cache_key = None            # Our cached weak cache key
        self.__strict_cache_key = None          # Our cached cache key for strict builds
        self.__artifacts = context.artifactcache  # Artifact cache
        self.__sourcecache = context.sourcecache  # Source cache
        self.__consistency = Consistency.INCONSISTENT  # Cached overall consistency state
        self.__strong_cached = None             # Whether we have a cached artifact
        self.__weak_cached = None               # Whether we have a cached artifact
        self.__assemble_scheduled = False       # Element is scheduled to be assembled
        self.__assemble_done = False            # Element is assembled
        self.__tracking_scheduled = False       # Sources are scheduled to be tracked
        self.__tracking_done = False            # Sources have been tracked
        self.__pull_done = False                # Whether pull was attempted
        self.__splits = None                    # Resolved regex objects for computing split domains
        self.__whitelist_regex = None           # Resolved regex object to check if file is allowed to overlap
        self.__staged_sources_directory = None  # Location where Element.stage_sources() was called
        self.__tainted = None                   # Whether the artifact is tainted and should not be shared
        self.__required = False                 # Whether the artifact is required in the current session
        self.__build_result = None              # The result of assembling this Element (success, description, detail)
        self._build_log_path = None            # The path of the build log for this Element
        self.__artifact = Artifact(self, context)  # Artifact class for direct artifact composite interaction

        self.__batch_prepare_assemble = False         # Whether batching across prepare()/assemble() is configured
        self.__batch_prepare_assemble_flags = 0       # Sandbox flags for batching across prepare()/assemble()
        self.__batch_prepare_assemble_collect = None  # Collect dir for batching across prepare()/assemble()

        # hash tables of loaded artifact metadata, hashed by key
        self.__metadata_keys = {}                     # Strong and weak keys for this key
        self.__metadata_dependencies = {}             # Dictionary of dependency strong keys
        self.__metadata_workspaced = {}               # Boolean of whether it's workspaced
        self.__metadata_workspaced_dependencies = {}  # List of which dependencies are workspaced

        # Ensure we have loaded this class's defaults
        self.__init_defaults(plugin_conf)

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(meta)
        _yaml.node_set(variables, 'element-name', self.name)
        self.__variables = Variables(variables)

        # Collect the composited environment now that we have variables
        self.__environment = self.__extract_environment(meta)

        # Collect the environment nocache blacklist list
        nocache = self.__extract_env_nocache(meta)
        self.__env_nocache = nocache

        # Grab public domain data declared for this instance
        self.__public = self.__extract_public(meta)
        self.__dynamic_public = None

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__config = self.__extract_config(meta)
        self._configure(self.__config)

        # Extract remote execution URL
        if not self.__is_junction:
            self.__remote_execution_specs = project.remote_execution_specs
        else:
            self.__remote_execution_specs = None

        # Extract Sandbox config
        self.__sandbox_config = self.__extract_sandbox_config(meta)

        self.__sandbox_config_supported = True
        if not self.__use_remote_execution():
            platform = Platform.get_platform()
            if not platform.check_sandbox_config(self.__sandbox_config):
                # Local sandbox does not fully support specified sandbox config.
                # This will taint the artifact, disable pushing.
                self.__sandbox_config_supported = False

    def __lt__(self, other):
        return self.name < other.name

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def configure_sandbox(self, sandbox):
        """Configures the the sandbox for execution

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to configure the sandbox object
        for execution.
        """
        raise ImplError("element plugin '{kind}' does not implement configure_sandbox()".format(
            kind=self.get_kind()))

    def stage(self, sandbox):
        """Stage inputs into the sandbox directories

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to populate the sandbox
        directory with data. This is done either by staging :class:`.Source`
        objects, by staging the artifacts of the elements this element depends
        on, or both.
        """
        raise ImplError("element plugin '{kind}' does not implement stage()".format(
            kind=self.get_kind()))

    def prepare(self, sandbox):
        """Run one-off preparation commands.

        This is run before assemble(), but is guaranteed to run only
        the first time if we build incrementally - this makes it
        possible to run configure-like commands without causing the
        entire element to rebuild.

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        Raises:
           (:class:`.ElementError`): When the element raises an error

        By default, this method does nothing, but may be overriden to
        allow configure-like commands.

        *Since: 1.2*
        """

    def assemble(self, sandbox):
        """Assemble the output artifact

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        Returns:
           (str): An absolute path within the sandbox to collect the artifact from

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to create an output
        artifact from its sources and dependencies.
        """
        raise ImplError("element plugin '{kind}' does not implement assemble()".format(
            kind=self.get_kind()))

    def generate_script(self):
        """Generate a build (sh) script to build this element

        Returns:
           (str): A string containing the shell commands required to build the element

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
        raise ImplError("element plugin '{kind}' does not implement write_script()".format(
            kind=self.get_kind()))

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def sources(self):
        """A generator function to enumerate the element sources

        Yields:
           (:class:`.Source`): The sources of this element
        """
        for source in self.__sources:
            yield source

    def dependencies(self, scope, *, recurse=True, visited=None):
        """dependencies(scope, *, recurse=True)

        A generator function which yields the dependencies of the given element.

        If `recurse` is specified (the default), the full dependencies will be listed
        in deterministic staging order, starting with the basemost elements in the
        given `scope`. Otherwise, if `recurse` is not specified then only the direct
        dependencies in the given `scope` will be traversed, and the element itself
        will be omitted.

        Args:
           scope (:class:`.Scope`): The scope to iterate in
           recurse (bool): Whether to recurse

        Yields:
           (:class:`.Element`): The dependencies in `scope`, in deterministic staging order
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

    def search(self, scope, name):
        """Search for a dependency by name

        Args:
           scope (:class:`.Scope`): The scope to search
           name (str): The dependency to search for

        Returns:
           (:class:`.Element`): The dependency element, or None if not found.
        """
        for dep in self.dependencies(scope):
            if dep.name == name:
                return dep

        return None

    def node_subst_member(self, node, member_name, default=_yaml._sentinel):
        """Fetch the value of a string node member, substituting any variables
        in the loaded value with the element contextual variables.

        Args:
           node (dict): A dictionary loaded from YAML
           member_name (str): The name of the member to fetch
           default (str): A value to return when *member_name* is not specified in *node*

        Returns:
           The value of *member_name* in *node*, otherwise *default*

        Raises:
           :class:`.LoadError`: When *member_name* is not found and no *default* was provided

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_member`
        except that it assumes the expected type is a string and will also perform variable
        substitutions.

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node', substituting any
          # variables in the returned string
          name = self.node_subst_member(node, 'name')
        """
        value = self.node_get_member(node, str, member_name, default)
        try:
            return self.__variables.subst(value)
        except LoadError as e:
            provenance = _yaml.node_get_provenance(node, key=member_name)
            raise LoadError(e.reason, '{}: {}'.format(provenance, e), detail=e.detail) from e

    def node_subst_list(self, node, member_name):
        """Fetch a list from a node member, substituting any variables in the list

        Args:
          node (dict): A dictionary loaded from YAML
          member_name (str): The name of the member to fetch (a list)

        Returns:
          The list in *member_name*

        Raises:
          :class:`.LoadError`

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_member`
        except that it assumes the expected type is a list of strings and will also
        perform variable substitutions.
        """
        value = self.node_get_member(node, list, member_name)
        ret = []
        for index, x in enumerate(value):
            try:
                ret.append(self.__variables.subst(x))
            except LoadError as e:
                provenance = _yaml.node_get_provenance(node, key=member_name, indices=[index])
                raise LoadError(e.reason, '{}: {}'.format(provenance, e), detail=e.detail) from e
        return ret

    def node_subst_list_element(self, node, member_name, indices):
        """Fetch the value of a list element from a node member, substituting any variables
        in the loaded value with the element contextual variables.

        Args:
           node (dict): A dictionary loaded from YAML
           member_name (str): The name of the member to fetch
           indices (list of int): List of indices to search, in case of nested lists

        Returns:
           The value of the list element in *member_name* at the specified *indices*

        Raises:
           :class:`.LoadError`

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_list_element`
        except that it assumes the expected type is a string and will also perform variable
        substitutions.

        **Example:**

        .. code:: python

          # Fetch the list itself
          strings = self.node_get_member(node, list, 'strings')

          # Iterate over the list indices
          for i in range(len(strings)):

              # Fetch the strings in this list, substituting content
              # with our element's variables if needed
              string = self.node_subst_list_element(
                  node, 'strings', [ i ])
        """
        value = self.node_get_list_element(node, str, member_name, indices)
        try:
            return self.__variables.subst(value)
        except LoadError as e:
            provenance = _yaml.node_get_provenance(node, key=member_name, indices=indices)
            raise LoadError(e.reason, '{}: {}'.format(provenance, e), detail=e.detail) from e

    def compute_manifest(self, *, include=None, exclude=None, orphans=True):
        """Compute and return this element's selective manifest

        The manifest consists on the list of file paths in the
        artifact. The files in the manifest are selected according to
        `include`, `exclude` and `orphans` parameters. If `include` is
        not specified then all files spoken for by any domain are
        included unless explicitly excluded with an `exclude` domain.

        Args:
           include (list): An optional list of domains to include files from
           exclude (list): An optional list of domains to exclude files from
           orphans (bool): Whether to include files not spoken for by split domains

        Yields:
           (str): The paths of the files in manifest
        """
        self.__assert_cached()
        return self.__compute_splits(include, exclude, orphans)

    def get_artifact_name(self, key=None):
        """Compute and return this element's full artifact name

        Generate a full name for an artifact, including the project
        namespace, element name and cache key.

        This can also be used as a relative path safely, and
        will normalize parts of the element name such that only
        digits, letters and some select characters are allowed.

        Args:
           key (str): The element's cache key. Defaults to None

        Returns:
           (str): The relative path for the artifact
        """
        project = self._get_project()
        if key is None:
            key = self._get_cache_key()

        assert key is not None

        valid_chars = string.digits + string.ascii_letters + '-._'
        element_name = ''.join([
            x if x in valid_chars else '_'
            for x in self.normal_name
        ])

        # Note that project names are not allowed to contain slashes. Element names containing
        # a '/' will have this replaced with a '-' upon Element object instantiation.
        return '{0}/{1}/{2}'.format(project.name, element_name, key)

    def stage_artifact(self, sandbox, *, path=None, include=None, exclude=None, orphans=True, update_mtimes=None):
        """Stage this element's output artifact in the sandbox

        This will stage the files from the artifact to the sandbox at specified location.
        The files are selected for staging according to the `include`, `exclude` and `orphans`
        parameters; if `include` is not specified then all files spoken for by any domain
        are included unless explicitly excluded with an `exclude` domain.

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           path (str): An optional sandbox relative path
           include (list): An optional list of domains to include files from
           exclude (list): An optional list of domains to exclude files from
           orphans (bool): Whether to include files not spoken for by split domains
           update_mtimes (list): An optional list of files whose mtimes to set to the current time.

        Raises:
           (:class:`.ElementError`): If the element has not yet produced an artifact.

        Returns:
           (:class:`~.utils.FileListResult`): The result describing what happened while staging

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
            detail = "No artifacts have been cached yet for that element\n" + \
                     "Try building the element first with `bst build`\n"
            raise ElementError("No artifacts to stage",
                               detail=detail, reason="uncached-checkout-attempt")

        if update_mtimes is None:
            update_mtimes = []

        # Time to use the artifact, check once more that it's there
        self.__assert_cached()

        with self.timed_activity("Staging {}/{}".format(self.name, self._get_brief_display_key())):
            files_vdir, _ = self.__artifact.get_files()

            # Hard link it into the staging area
            #
            vbasedir = sandbox.get_virtual_directory()
            vstagedir = vbasedir \
                if path is None \
                else vbasedir.descend(*path.lstrip(os.sep).split(os.sep))

            split_filter = self.__split_filter_func(include, exclude, orphans)

            # We must not hardlink files whose mtimes we want to update
            if update_mtimes:
                def link_filter(path):
                    return ((split_filter is None or split_filter(path)) and
                            path not in update_mtimes)

                def copy_filter(path):
                    return ((split_filter is None or split_filter(path)) and
                            path in update_mtimes)
            else:
                link_filter = split_filter

            result = vstagedir.import_files(files_vdir, filter_callback=link_filter,
                                            report_written=True, can_link=True)

            if update_mtimes:
                copy_result = vstagedir.import_files(files_vdir, filter_callback=copy_filter,
                                                     report_written=True, update_mtime=True)
                result = result.combine(copy_result)

            return result

    def stage_dependency_artifacts(self, sandbox, scope, *, path=None,
                                   include=None, exclude=None, orphans=True):
        """Stage element dependencies in scope

        This is primarily a convenience wrapper around
        :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>`
        which takes care of staging all the dependencies in `scope` and issueing the
        appropriate warnings.

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           scope (:class:`.Scope`): The scope to stage dependencies in
           path (str): An optional sandbox relative path
           include (list): An optional list of domains to include files from
           exclude (list): An optional list of domains to exclude files from
           orphans (bool): Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): If any of the dependencies in `scope` have not
                                     yet produced artifacts, or if forbidden overlaps
                                     occur.
        """
        ignored = {}
        overlaps = OrderedDict()
        files_written = {}
        old_dep_keys = None
        workspace = self._get_workspace()

        if self.__can_build_incrementally() and workspace.last_successful:
            # Workspaces do not need to work with the special node types
            old_dep_keys = self.__get_artifact_metadata_dependencies(workspace.last_successful)

        for dep in self.dependencies(scope):
            # If we are workspaced, and we therefore perform an
            # incremental build, we must ensure that we update the mtimes
            # of any files created by our dependencies since the last
            # successful build.
            to_update = None
            if workspace and old_dep_keys:
                dep.__assert_cached()

                if _yaml.node_contains(old_dep_keys, dep.name):
                    key_new = dep._get_cache_key()
                    key_old = _yaml.node_get(old_dep_keys, str, dep.name)

                    # We only need to worry about modified and added
                    # files, since removed files will be picked up by
                    # build systems anyway.
                    to_update, _, added = self.__artifacts.diff(dep, key_old, key_new, subdir='files')
                    workspace.add_running_files(dep.name, to_update + added)
                    to_update.extend(workspace.running_files[dep.name])

                    # In case we are running `bst shell`, this happens in the
                    # main process and we need to update the workspace config
                    if utils._is_main_process():
                        self._get_context().get_workspaces().save_config()

            result = dep.stage_artifact(sandbox,
                                        path=path,
                                        include=include,
                                        exclude=exclude,
                                        orphans=orphans,
                                        update_mtimes=to_update)
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
                    element = self.search(scope, elm)
                    if not element.__file_is_whitelisted(f):
                        overlap_warning_elements.append(elm)
                        overlap_warning = True

                warning_detail += _overlap_error_detail(f, overlap_warning_elements, elements)

            if overlap_warning:
                self.warn("Non-whitelisted overlaps detected", detail=warning_detail,
                          warning_token=CoreWarnings.OVERLAPS)

        if ignored:
            detail = "Not staging files which would replace non-empty directories:\n"
            for key, value in ignored.items():
                detail += "\nFrom {}:\n".format(key)
                detail += "  " + "  ".join(["/" + f + "\n" for f in value])
            self.warn("Ignored files", detail=detail)

    def integrate(self, sandbox):
        """Integrate currently staged filesystem against this artifact.

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        This modifies the sysroot staged inside the sandbox so that
        the sysroot is *integrated*. Only an *integrated* sandbox
        may be trusted for running the software therein, as the integration
        commands will create and update important system cache files
        required for running the installed software (such as the ld.so.cache).
        """
        bstdata = self.get_public_data('bst')
        environment = self.get_environment()

        if bstdata is not None:
            with sandbox.batch(SandboxFlags.NONE):
                commands = self.node_get_member(bstdata, list, 'integration-commands', [])
                for i in range(len(commands)):
                    cmd = self.node_subst_list_element(bstdata, 'integration-commands', [i])

                    sandbox.run(['sh', '-e', '-c', cmd], 0, env=environment, cwd='/',
                                label=cmd)

    def stage_sources(self, sandbox, directory):
        """Stage this element's sources to a directory in the sandbox

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           directory (str): An absolute path within the sandbox to stage the sources at
        """

        # Hold on to the location where a plugin decided to stage sources,
        # this will be used to reconstruct the failed sysroot properly
        # after a failed build.
        #
        assert self.__staged_sources_directory is None
        self.__staged_sources_directory = directory

        self._stage_sources_in_sandbox(sandbox, directory)

    def get_public_data(self, domain):
        """Fetch public data on this element

        Args:
           domain (str): A public domain name to fetch data for

        Returns:
           (dict): The public data dictionary for the given domain

        .. note::

           This can only be called the abstract methods which are
           called as a part of the :ref:`build phase <core_element_build_phase>`
           and never before.
        """
        if self.__dynamic_public is None:
            self.__load_public_data()

        data = _yaml.node_get(self.__dynamic_public, Mapping, domain, default_value=None)
        if data is not None:
            data = _yaml.node_copy(data)

        return data

    def set_public_data(self, domain, data):
        """Set public data on this element

        Args:
           domain (str): A public domain name to fetch data for
           data (dict): The public data dictionary for the given domain

        This allows an element to dynamically mutate public data of
        elements or add new domains as the result of success completion
        of the :func:`Element.assemble() <buildstream.element.Element.assemble>`
        method.
        """
        if self.__dynamic_public is None:
            self.__load_public_data()

        if data is not None:
            data = _yaml.node_copy(data)

        _yaml.node_set(self.__dynamic_public, domain, data)

    def get_environment(self):
        """Fetch the environment suitable for running in the sandbox

        Returns:
           (dict): A dictionary of string key/values suitable for passing
           to :func:`Sandbox.run() <buildstream.sandbox.Sandbox.run>`
        """
        return _yaml.node_sanitize(self.__environment)

    def get_variable(self, varname):
        """Fetch the value of a variable resolved for this element.

        Args:
           varname (str): The name of the variable to fetch

        Returns:
           (str): The resolved value for *varname*, or None if no
           variable was declared with the given name.
        """
        return self.__variables.flat.get(varname)

    def batch_prepare_assemble(self, flags, *, collect=None):
        """ Configure command batching across prepare() and assemble()

        Args:
           flags (:class:`.SandboxFlags`): The sandbox flags for the command batch
           collect (str): An optional directory containing partial install contents
                          on command failure.

        This may be called in :func:`Element.configure_sandbox() <buildstream.element.Element.configure_sandbox>`
        to enable batching of all sandbox commands issued in prepare() and assemble().
        """
        if self.__batch_prepare_assemble:
            raise ElementError("{}: Command batching for prepare/assemble is already configured".format(self))

        self.__batch_prepare_assemble = True
        self.__batch_prepare_assemble_flags = flags
        self.__batch_prepare_assemble_collect = collect

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
    #
    # Returns:
    #    (Element): A newly created Element instance
    #
    @classmethod
    def _new_from_meta(cls, meta):

        if not meta.first_pass:
            meta.project.ensure_fully_loaded()

        if meta in cls.__instantiated_elements:
            return cls.__instantiated_elements[meta]

        element = meta.project.create_element(meta, first_pass=meta.first_pass)
        cls.__instantiated_elements[meta] = element

        # Instantiate sources and generate their keys
        for meta_source in meta.sources:
            meta_source.first_pass = meta.kind == "junction"
            source = meta.project.create_source(meta_source,
                                                first_pass=meta.first_pass)

            redundant_ref = source._load_ref()
            element.__sources.append(source)

            # Collect redundant refs which occurred at load time
            if redundant_ref is not None:
                cls.__redundant_source_refs.append((source, redundant_ref))

        # Instantiate dependencies
        for meta_dep in meta.dependencies:
            dependency = Element._new_from_meta(meta_dep)
            element.__runtime_dependencies.append(dependency)
            dependency.__reverse_dependencies.add(element)

        for meta_dep in meta.build_dependencies:
            dependency = Element._new_from_meta(meta_dep)
            element.__build_dependencies.append(dependency)
            dependency.__reverse_dependencies.add(element)

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

    # _get_consistency()
    #
    # Returns cached consistency state
    #
    def _get_consistency(self):
        return self.__consistency

    # _cached():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache
    #
    def _cached(self):
        return self.__is_cached(keystrength=None)

    # _get_build_result():
    #
    # Returns:
    #    (bool): Whether the artifact of this element present in the artifact cache is of a success
    #    (str): Short description of the result
    #    (str): Detailed description of the result
    #
    def _get_build_result(self):
        return self.__get_build_result(keystrength=None)

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
        return self.__cached_success(keystrength=None)

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
        if self._get_consistency() < Consistency.CACHED and \
                not self._source_cached():
            return False

        for dependency in self.dependencies(Scope.BUILD):
            # In non-strict mode an element's strong cache key may not be available yet
            # even though an artifact is available in the local cache. This can happen
            # if the pull job is still pending as the remote cache may have an artifact
            # that matches the strict cache key, which is preferred over a locally
            # cached artifact with a weak cache key match.
            if not dependency._cached_success() or not dependency._get_cache_key(strength=_KeyStrength.STRONG):
                return False

        if not self.__assemble_scheduled:
            return False

        return True

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
        # If build has already been scheduled, we know that the element is
        # not cached and thus can allow cache query even if the strict cache key
        # is not available yet.
        # This special case is required for workspaced elements to prevent
        # them from getting blocked in the pull queue.
        if self.__assemble_scheduled:
            return True

        # cache cannot be queried until strict cache key is available
        return self.__strict_cache_key is not None

    # _calculate_weak_cache_key():
    #
    # Calculates and sets the weak cache key of this element.
    #
    # Note that this bypasses any checks that the element is in a suitable
    # state for calculating the weak cache key (e.g. that it has a ref).
    #
    # Returns:
    #    (str): A hex digest for this element's weak cache key, or None.
    #
    def _calculate_weak_cache_key(self):
        # Weak cache key includes names of direct build dependencies
        # but does not include keys of dependencies.
        if self.BST_STRICT_REBUILD:
            dependencies = [
                e._get_cache_key(strength=_KeyStrength.WEAK)
                for e in self.dependencies(Scope.BUILD)
            ]
        else:
            dependencies = [
                e.name for e in self.dependencies(Scope.BUILD, recurse=False)
            ]

        self.__weak_cache_key = self._calculate_cache_key(dependencies)
        return self.__weak_cache_key

    # _update_state()
    #
    # Keep track of element state. Calculate cache keys if possible and
    # check whether artifacts are cached.
    #
    # This must be called whenever the state of an element may have changed.
    #
    def _update_state(self):
        context = self._get_context()

        # Compute and determine consistency of sources
        self.__update_source_state()

        if self._get_consistency() == Consistency.INCONSISTENT:
            # Tracking may still be pending
            return

        if self._get_workspace() and self.__assemble_scheduled:
            # If we have an active workspace and are going to build, then
            # discard current cache key values as their correct values can only
            # be calculated once the build is complete
            self.__cache_key_dict = None
            self.__cache_key = None
            self.__weak_cache_key = None
            self.__strict_cache_key = None
            self.__strong_cached = None
            self.__weak_cached = None
            self.__build_result = None
            return

        if self.__weak_cache_key is None:
            if self._calculate_weak_cache_key() is None:
                # Weak cache key could not be calculated yet
                return

            if not context.get_strict():
                self.__weak_cached = self.__artifact.cached(self.__weak_cache_key)

        if not context.get_strict():
            # Full cache query in non-strict mode requires both the weak and
            # strict cache keys. However, we need to determine as early as
            # possible whether a build is pending to discard unstable cache keys
            # for workspaced elements. For this cache check the weak cache keys
            # are sufficient. However, don't update the `cached` attributes
            # until the full cache query below.
            if (not self.__assemble_scheduled and not self.__assemble_done and
                    not self.__cached_success(keystrength=_KeyStrength.WEAK) and
                    not self._pull_pending()):
                # For uncached workspaced elements, assemble is required
                # even if we only need the cache key
                if self._is_required() or self._get_workspace():
                    self._schedule_assemble()
                    return

        if self.__strict_cache_key is None:
            dependencies = [
                e.__strict_cache_key for e in self.dependencies(Scope.BUILD)
            ]
            self.__strict_cache_key = self._calculate_cache_key(dependencies)
            if self.__strict_cache_key is None:
                # Strict cache key could not be calculated yet
                return

        # Query caches now that the weak and strict cache keys are available
        key_for_cache_lookup = self.__strict_cache_key if context.get_strict() else self.__weak_cache_key
        if not self.__strong_cached:
            self.__strong_cached = self.__artifact.cached(self.__strict_cache_key)
        if key_for_cache_lookup == self.__weak_cache_key:
            if not self.__weak_cached:
                self.__weak_cached = self.__artifact.cached(self.__weak_cache_key)

        if (not self.__assemble_scheduled and not self.__assemble_done and
                not self._cached_success() and not self._pull_pending()):
            # Workspaced sources are considered unstable if a build is pending
            # as the build will modify the contents of the workspace.
            # Determine as early as possible if a build is pending to discard
            # unstable cache keys.

            # For uncached workspaced elements, assemble is required
            # even if we only need the cache key
            if self._is_required() or self._get_workspace():
                self._schedule_assemble()
                return

        if self.__cache_key is None:
            # Calculate strong cache key
            if context.get_strict():
                self.__cache_key = self.__strict_cache_key
            elif self._pull_pending():
                # Effective strong cache key is unknown until after the pull
                pass
            elif self._cached():
                # Load the strong cache key from the artifact
                strong_key, _ = self.__get_artifact_metadata_keys()
                self.__cache_key = strong_key
            elif self.__assemble_scheduled or self.__assemble_done:
                # Artifact will or has been built, not downloaded
                dependencies = [
                    e._get_cache_key() for e in self.dependencies(Scope.BUILD)
                ]
                self.__cache_key = self._calculate_cache_key(dependencies)

            if self.__cache_key is None:
                # Strong cache key could not be calculated yet
                return

        if not self.__ready_for_runtime and self.__cache_key is not None:
            self.__ready_for_runtime = all(
                dep.__ready_for_runtime for dep in self.__runtime_dependencies)

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
            cache_key = "{:?<64}".format('')
        elif self._get_cache_key() == self.__strict_cache_key:
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

    # _preflight():
    #
    # A wrapper for calling the abstract preflight() method on
    # the element and its sources.
    #
    def _preflight(self):

        if self.BST_FORBID_RDEPENDS and self.BST_FORBID_BDEPENDS:
            if any(self.dependencies(Scope.RUN, recurse=False)) or any(self.dependencies(Scope.BUILD, recurse=False)):
                raise ElementError("{}: Dependencies are forbidden for '{}' elements"
                                   .format(self, self.get_kind()), reason="element-forbidden-depends")

        if self.BST_FORBID_RDEPENDS:
            if any(self.dependencies(Scope.RUN, recurse=False)):
                raise ElementError("{}: Runtime dependencies are forbidden for '{}' elements"
                                   .format(self, self.get_kind()), reason="element-forbidden-rdepends")

        if self.BST_FORBID_BDEPENDS:
            if any(self.dependencies(Scope.BUILD, recurse=False)):
                raise ElementError("{}: Build dependencies are forbidden for '{}' elements"
                                   .format(self, self.get_kind()), reason="element-forbidden-bdepends")

        if self.BST_FORBID_SOURCES:
            if any(self.sources()):
                raise ElementError("{}: Sources are forbidden for '{}' elements"
                                   .format(self, self.get_kind()), reason="element-forbidden-sources")

        try:
            self.preflight()
        except BstError as e:
            # Prepend provenance to the error
            raise ElementError("{}: {}".format(self, e), reason=e.reason, detail=e.detail) from e

        # Ensure that the first source does not need access to previous soruces
        if self.__sources and self.__sources[0]._requires_previous_sources():
            raise ElementError("{}: {} cannot be the first source of an element "
                               "as it requires access to previous sources"
                               .format(self, self.__sources[0]))

        # Preflight the sources
        for source in self.sources():
            source._preflight()

    # _schedule_tracking():
    #
    # Force an element state to be inconsistent. Any sources appear to be
    # inconsistent.
    #
    # This is used across the pipeline in sessions where the
    # elements in question are going to be tracked, causing the
    # pipeline to rebuild safely by ensuring cache key recalculation
    # and reinterrogation of element state after tracking of elements
    # succeeds.
    #
    def _schedule_tracking(self):
        self.__tracking_scheduled = True
        self._update_state()

    # _tracking_done():
    #
    # This is called in the main process after the element has been tracked
    #
    def _tracking_done(self):
        assert self.__tracking_scheduled

        self.__tracking_scheduled = False
        self.__tracking_done = True

        self.__update_state_recursively()

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
                detail = "This source has an open workspace.\n" \
                    + "To start using the new reference, please close the existing workspace."
                source.warn("Updated reference will be ignored as source has open workspace", detail=detail)

        return refs

    # _prepare_sandbox():
    #
    # This stages things for either _shell() (below) or also
    # is used to stage things by the `bst artifact checkout` codepath
    #
    @contextmanager
    def _prepare_sandbox(self, scope, directory, shell=False, integrate=True, usebuildtree=False):
        # bst shell and bst artifact checkout require a local sandbox.
        bare_directory = bool(directory)
        with self.__sandbox(directory, config=self.__sandbox_config, allow_remote=False,
                            bare_directory=bare_directory) as sandbox:
            sandbox._usebuildtree = usebuildtree

            # Configure always comes first, and we need it.
            self.__configure_sandbox(sandbox)

            # Stage something if we need it
            if not directory:
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
    #     mount_workspaces (bool): mount workspaces if True, copy otherwise
    #
    def _stage_sources_in_sandbox(self, sandbox, directory, mount_workspaces=True):

        # Only artifact caches that implement diff() are allowed to
        # perform incremental builds.
        if mount_workspaces and self.__can_build_incrementally():
            workspace = self._get_workspace()
            sandbox.mark_directory(directory)
            sandbox._set_mount_source(directory, workspace.get_absolute_path())

        # Stage all sources that need to be copied
        sandbox_vroot = sandbox.get_virtual_directory()
        host_vdirectory = sandbox_vroot.descend(*directory.lstrip(os.sep).split(os.sep), create=True)
        self._stage_sources_at(host_vdirectory, mount_workspaces=mount_workspaces, usebuildtree=sandbox._usebuildtree)

    # _stage_sources_at():
    #
    # Stage this element's sources to a directory
    #
    # Args:
    #     vdirectory (:class:`.storage.Directory`): A virtual directory object to stage sources into.
    #     mount_workspaces (bool): mount workspaces if True, copy otherwise
    #     usebuildtree (bool): use a the elements build tree as its source.
    #
    def _stage_sources_at(self, vdirectory, mount_workspaces=True, usebuildtree=False):

        context = self._get_context()

        # It's advantageous to have this temporary directory on
        # the same file system as the rest of our cache.
        with self.timed_activity("Staging sources", silent_nested=True), \
            utils._tempdir(dir=context.tmpdir, prefix='staging-temp') as temp_staging_directory:

            import_dir = temp_staging_directory

            if not isinstance(vdirectory, Directory):
                vdirectory = FileBasedDirectory(vdirectory)
            if not vdirectory.is_empty():
                raise ElementError("Staging directory '{}' is not empty".format(vdirectory))

            workspace = self._get_workspace()
            if workspace:
                # If mount_workspaces is set and we're doing incremental builds,
                # the workspace is already mounted into the sandbox.
                if not (mount_workspaces and self.__can_build_incrementally()):
                    with self.timed_activity("Staging local files at {}"
                                             .format(workspace.get_absolute_path())):
                        workspace.stage(import_dir)

            # Check if we have a cached buildtree to use
            elif usebuildtree:
                import_dir, _ = self.__artifact.get_buildtree()
                if import_dir.is_empty():
                    detail = "Element type either does not expect a buildtree or it was explictily cached without one."
                    self.warn("WARNING: {} Artifact contains an empty buildtree".format(self.name), detail=detail)

            # No workspace or cached buildtree, stage source from source cache
            else:
                # Ensure sources are cached
                self.__cache_sources()

                if self.__sources:

                    sourcecache = self._get_context().sourcecache
                    try:
                        import_dir = sourcecache.export(self.__sources[-1])
                    except SourceCacheError as e:
                        raise ElementError("Error trying to export source for {}: {}"
                                           .format(self.name, e))

            with utils._deterministic_umask():
                vdirectory.import_files(import_dir)

        # Ensure deterministic mtime of sources at build time
        vdirectory.set_deterministic_mtime()
        # Ensure deterministic owners of sources at build time
        vdirectory.set_deterministic_user()

    # _set_required():
    #
    # Mark this element and its runtime dependencies as required.
    # This unblocks pull/fetch/build.
    #
    def _set_required(self):
        if self.__required:
            # Already done
            return

        self.__required = True

        # Request artifacts of runtime dependencies
        for dep in self.dependencies(Scope.RUN, recurse=False):
            dep._set_required()

        self._update_state()

    # _is_required():
    #
    # Returns whether this element has been marked as required.
    #
    def _is_required(self):
        return self.__required

    # _schedule_assemble():
    #
    # This is called in the main process before the element is assembled
    # in a subprocess.
    #
    def _schedule_assemble(self):
        assert not self.__assemble_scheduled
        self.__assemble_scheduled = True

        # Requests artifacts of build dependencies
        for dep in self.dependencies(Scope.BUILD, recurse=False):
            dep._set_required()

        self._set_required()

        # Invalidate workspace key as the build modifies the workspace directory
        workspace = self._get_workspace()
        if workspace:
            workspace.invalidate_key()

        self._update_state()

    # _assemble_done():
    #
    # This is called in the main process after the element has been assembled
    # and in the a subprocess after assembly completes.
    #
    # This will result in updating the element state.
    #
    def _assemble_done(self):
        assert self.__assemble_scheduled

        self.__assemble_scheduled = False
        self.__assemble_done = True

        self.__update_state_recursively()

        if self._get_workspace() and self._cached_success():
            assert utils._is_main_process(), \
                "Attempted to save workspace configuration from child process"
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
            workspace.last_successful = key
            workspace.clear_running_files()
            self._get_context().get_workspaces().save_config()

            # This element will have already been marked as
            # required, but we bump the atime again, in case
            # we did not know the cache key until now.
            #
            # FIXME: This is not exactly correct, we should be
            #        doing this at the time which we have discovered
            #        a new cache key, this just happens to be the
            #        last place where that can happen.
            #
            #        Ultimately, we should be refactoring
            #        Element._update_state() such that we know
            #        when a cache key is actually discovered.
            #
            self.__artifacts.mark_required_elements([self])

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

            if not self.__sandbox_config_supported:
                self.warn("Sandbox configuration is not supported by the platform.",
                          detail="Falling back to UID {} GID {}. Artifact will not be pushed."
                          .format(self.__sandbox_config.build_uid, self.__sandbox_config.build_gid))

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Cleanup the build directory on explicit SIGTERM
            def cleanup_rootdir():
                utils._force_rmtree(rootdir)

            with _signals.terminator(cleanup_rootdir), \
                self.__sandbox(rootdir, output_file, output_file, self.__sandbox_config) as sandbox:  # noqa

                if not self.BST_RUN_COMMANDS:
                    # Element doesn't need to run any commands in the sandbox.
                    #
                    # Disable Sandbox.run() to allow CasBasedDirectory for all
                    # sandboxes.
                    sandbox._disable_run()

                # By default, the dynamic public data is the same as the static public data.
                # The plugin's assemble() method may modify this, though.
                self.__dynamic_public = _yaml.node_copy(self.__public)

                # Call the abstract plugin methods

                # Step 1 - Configure
                self.__configure_sandbox(sandbox)
                # Step 2 - Stage
                self.stage(sandbox)
                try:
                    if self.__batch_prepare_assemble:
                        cm = sandbox.batch(self.__batch_prepare_assemble_flags,
                                           collect=self.__batch_prepare_assemble_collect)
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

                    # If there is a workspace open on this element, it will have
                    # been mounted for sandbox invocations instead of being staged.
                    #
                    # In order to preserve the correct failure state, we need to
                    # copy over the workspace files into the appropriate directory
                    # in the sandbox.
                    #
                    workspace = self._get_workspace()
                    if workspace and self.__staged_sources_directory:
                        sandbox_vroot = sandbox.get_virtual_directory()
                        path_components = self.__staged_sources_directory.lstrip(os.sep).split(os.sep)
                        sandbox_vpath = sandbox_vroot.descend(*path_components)
                        try:
                            sandbox_vpath.import_files(workspace.get_absolute_path())
                        except UtilError as e2:
                            self.warn("Failed to preserve workspace state for failed build sysroot: {}"
                                      .format(e2))

                    self.__set_build_result(success=False, description=str(e), detail=e.detail)
                    self._cache_artifact(rootdir, sandbox, e.collect)

                    raise
                else:
                    return self._cache_artifact(rootdir, sandbox, collect)
                finally:
                    cleanup_rootdir()

    def _cache_artifact(self, rootdir, sandbox, collect):

        context = self._get_context()
        buildresult = self.__build_result
        publicdata = self.__dynamic_public
        sandbox_vroot = sandbox.get_virtual_directory()
        collectvdir = None
        sandbox_build_dir = None

        cache_buildtrees = context.cache_buildtrees
        build_success = buildresult[0]

        # cache_buildtrees defaults to 'auto', only caching buildtrees
        # when necessary, which includes failed builds.
        # If only caching failed artifact buildtrees, then query the build
        # result. Element types without a build-root dir will be cached
        # with an empty buildtreedir regardless of this configuration.

        if cache_buildtrees == 'always' or (cache_buildtrees == 'auto' and not build_success):
            try:
                sandbox_build_dir = sandbox_vroot.descend(
                    *self.get_variable('build-root').lstrip(os.sep).split(os.sep))
            except VirtualDirectoryError:
                # Directory could not be found. Pre-virtual
                # directory behaviour was to continue silently
                # if the directory could not be found.
                pass

        if collect is not None:
            try:
                collectvdir = sandbox_vroot.descend(*collect.lstrip(os.sep).split(os.sep))
            except VirtualDirectoryError:
                pass

        # ensure we have cache keys
        self._assemble_done()
        keys = self.__get_cache_keys_for_commit()

        with self.timed_activity("Caching artifact"):
            artifact_size = self.__artifact.cache(rootdir, sandbox_build_dir, collectvdir,
                                                  buildresult, keys, publicdata)

        if collect is not None and collectvdir is None:
            raise ElementError(
                "Directory '{}' was not found inside the sandbox, "
                "unable to collect artifact contents"
                .format(collect))

        return artifact_size

    def _get_build_log(self):
        return self._build_log_path

    # _fetch_done()
    #
    # Indicates that fetching the sources for this element has been done.
    #
    def _fetch_done(self):
        # We are not updating the state recursively here since fetching can
        # never end up in updating them.
        self._update_state()

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
        subdir, _ = self.__pull_directories()

        if self.__strong_cached and subdir:
            # If we've specified a subdir, check if the subdir is cached locally
            if self.__artifacts.contains_subdir_artifact(self, self.__strict_cache_key, subdir):
                return False
        elif self.__strong_cached:
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

        self.__update_state_recursively()

    # _pull():
    #
    # Pull artifact from remote artifact repository into local artifact cache.
    #
    # Returns: True if the artifact has been downloaded, False otherwise
    #
    def _pull(self):
        context = self._get_context()

        def progress(percent, message):
            self.status(message)

        # Get optional specific subdir to pull and optional list to not pull
        # based off of user context
        subdir, excluded_subdirs = self.__pull_directories()

        # Attempt to pull artifact without knowing whether it's available
        pulled = self.__pull_strong(progress=progress, subdir=subdir, excluded_subdirs=excluded_subdirs)

        if not pulled and not self._cached() and not context.get_strict():
            pulled = self.__pull_weak(progress=progress, subdir=subdir, excluded_subdirs=excluded_subdirs)

        if not pulled:
            return False

        # Notify successfull download
        return True

    def _skip_source_push(self):
        if not self.__sources or self._get_workspace():
            return True
        return not (self.__sourcecache.has_push_remotes(plugin=self) and
                    self._source_cached())

    def _source_push(self):
        # try and push sources if we've got them
        if self.__sourcecache.has_push_remotes(plugin=self) and self._source_cached():
            sources = list(self.sources())
            if sources:
                source_pushed = self.__sourcecache.push(sources[-1])

                if not source_pushed:
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

        # Push all keys used for local commit
        pushed = self.__artifacts.push(self, self.__get_cache_keys_for_commit())
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
    #    directory (str): A directory to an existing sandbox, or None
    #    mounts (list): A list of (str, str) tuples, representing host/target paths to mount
    #    isolate (bool): Whether to isolate the environment like we do in builds
    #    prompt (str): A suitable prompt string for PS1
    #    command (list): An argv to launch in the sandbox
    #    usebuildtree (bool): Use the buildtree as its source
    #
    # Returns: Exit code
    #
    # If directory is not specified, one will be staged using scope
    def _shell(self, scope=None, directory=None, *, mounts=None, isolate=False, prompt=None, command=None,
               usebuildtree=False):

        with self._prepare_sandbox(scope, directory, shell=True, usebuildtree=usebuildtree) as sandbox:
            environment = self.get_environment()
            environment = copy.copy(environment)
            flags = SandboxFlags.INTERACTIVE | SandboxFlags.ROOT_READ_ONLY

            # Fetch the main toplevel project, in case this is a junctioned
            # subproject, we want to use the rules defined by the main one.
            context = self._get_context()
            project = context.get_toplevel_project()
            shell_command, shell_environment, shell_host_files = project.get_shell_config()

            if prompt is not None:
                environment['PS1'] = prompt

            # Special configurations for non-isolated sandboxes
            if not isolate:

                # Open the network, and reuse calling uid/gid
                #
                flags |= SandboxFlags.NETWORK_ENABLED | SandboxFlags.INHERIT_UID

                # Apply project defined environment vars to set for a shell
                for key, value in _yaml.node_items(shell_environment):
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
                argv = [arg for arg in command]
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
        with utils._tempdir(dir=context.builddir, prefix='workspace-{}'
                            .format(self.normal_name)) as temp:
            last_source = None
            for source in self.sources():
                last_source = source

            if last_source:
                last_source._init_workspace(temp)

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
            build_root=self.get_variable('build-root'),
            install_root=self.get_variable('install-root'),
            variables=variable_string,
            commands=self.generate_script()
        )

        os.makedirs(directory, exist_ok=True)
        script_path = os.path.join(directory, "build-" + self.normal_name)

        with self.timed_activity("Writing build script", silent_nested=True):
            with utils.save_file_atomic(script_path, "w") as script_file:
                script_file.write(script)

            os.chmod(script_path, stat.S_IEXEC | stat.S_IREAD)

    # _subst_string()
    #
    # Substitue a string, this is an internal function related
    # to how junctions are loaded and needs to be more generic
    # than the public node_subst_member()
    #
    # Args:
    #    value (str): A string value
    #
    # Returns:
    #    (str): The string after substitutions have occurred
    #
    def _subst_string(self, value):
        return self.__variables.subst(value)

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
        return self.__artifact.cached_buildtree()

    # _buildtree_exists()
    #
    # Check if artifact was created with a buildtree. This does not check
    # whether the buildtree is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildtree
    #
    def _buildtree_exists(self):
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
        sources = self.__sources
        if sources and not fetch_original:
            source = sources[-1]
            if self.__sourcecache.contains(source):
                return

            # try and fetch from source cache
            if source._get_consistency() < Consistency.CACHED and \
                    self.__sourcecache.has_fetch_remotes() and \
                    not self.__sourcecache.contains(source):
                if self.__sourcecache.pull(source):
                    return

        # We need to fetch original sources
        for source in self.sources():
            source_consistency = source._get_consistency()
            if source_consistency != Consistency.CACHED:
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
            cache_env = {
                key: value
                for key, value in self.__environment.items()
                if key not in self.__env_nocache
            }

            context = self._get_context()
            project = self._get_project()
            workspace = self._get_workspace()

            self.__cache_key_dict = {
                'artifact-version': "{}.{}".format(BST_CORE_ARTIFACT_VERSION,
                                                   self.BST_ARTIFACT_VERSION),
                'context': context.get_cache_key(),
                'project': project.get_cache_key(),
                'element': self.get_unique_key(),
                'execution-environment': self.__sandbox_config.get_unique_key(),
                'environment': cache_env,
                'sources': [s._get_unique_key(workspace is None) for s in self.__sources],
                'workspace': '' if workspace is None else workspace.get_key(self._get_project()),
                'public': self.__public,
                'cache': 'CASCache'
            }

            self.__cache_key_dict['fatal-warnings'] = sorted(project._fatal_warnings)

        cache_key_dict = self.__cache_key_dict.copy()
        cache_key_dict['dependencies'] = dependencies

        return _cachekey.generate_key(cache_key_dict)

    # Check if sources are cached, generating the source key if it hasn't been
    def _source_cached(self):
        if self.__sources:
            last_source = self.__sources[-1]
            if not last_source._key:
                last_source._generate_key(self.__sources[:-1])
            return self._get_context().sourcecache.contains(last_source)
        else:
            return True

    def _should_fetch(self, fetch_original=False):
        """ return bool of if we need to run the fetch stage for this element

        Args:
            fetch_original (bool): whether we need to original unstaged source
        """
        if (self._get_consistency() == Consistency.CACHED and fetch_original) or \
           (self._source_cached() and not fetch_original):
            return False
        else:
            return True

    #############################################################
    #                   Private Local Methods                   #
    #############################################################

    # __update_source_state()
    #
    # Updates source consistency state
    #
    def __update_source_state(self):

        # Cannot resolve source state until tracked
        if self.__tracking_scheduled:
            return

        self.__consistency = Consistency.CACHED
        workspace = self._get_workspace()

        # Special case for workspaces
        if workspace:

            # A workspace is considered inconsistent in the case
            # that its directory went missing
            #
            fullpath = workspace.get_absolute_path()
            if not os.path.exists(fullpath):
                self.__consistency = Consistency.INCONSISTENT
        else:

            # Determine overall consistency of the element
            for source in self.__sources:
                source._update_state()
                self.__consistency = min(self.__consistency, source._get_consistency())

    # __can_build_incrementally()
    #
    # Check if the element can be built incrementally, this
    # is used to decide how to stage things
    #
    # Returns:
    #    (bool): Whether this element can be built incrementally
    #
    def __can_build_incrementally(self):
        return bool(self._get_workspace())

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
        workspace = self._get_workspace()

        # We need to ensure that the prepare() method is only called
        # once in workspaces, because the changes will persist across
        # incremental builds - not desirable, for example, in the case
        # of autotools' `./configure`.
        if not (workspace and workspace.prepared):
            self.prepare(sandbox)

            if workspace:
                def mark_workspace_prepared():
                    workspace.prepared = True

                # Defer workspace.prepared setting until pending batch commands
                # have been executed.
                sandbox._callback(mark_workspace_prepared)

    def __is_cached(self, keystrength):
        if keystrength is None:
            keystrength = _KeyStrength.STRONG if self._get_context().get_strict() else _KeyStrength.WEAK

        return self.__strong_cached if keystrength == _KeyStrength.STRONG else self.__weak_cached

    # __assert_cached()
    #
    # Raises an error if the artifact is not cached.
    #
    def __assert_cached(self, keystrength=None):
        assert self.__is_cached(keystrength=keystrength), "{}: Missing artifact {}".format(
            self, self._get_brief_display_key())

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
            workspaced = self.__get_artifact_metadata_workspaced()

            # Whether this artifact's dependencies have workspaces
            workspaced_dependencies = self.__get_artifact_metadata_workspaced_dependencies()

            # Other conditions should be or-ed
            self.__tainted = (workspaced or workspaced_dependencies or
                              not self.__sandbox_config_supported)

        return self.__tainted

    # __use_remote_execution():
    #
    # Returns True if remote execution is configured and the element plugin
    # supports it.
    #
    def __use_remote_execution(self):
        return self.__remote_execution_specs and self.BST_VIRTUAL_DIRECTORY

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
    #    bare_directory (bool): Whether the directory is bare i.e. doesn't have
    #                           a separate 'root' subdir
    #
    # Yields:
    #    (Sandbox): A usable sandbox
    #
    @contextmanager
    def __sandbox(self, directory, stdout=None, stderr=None, config=None, allow_remote=True, bare_directory=False):
        context = self._get_context()
        project = self._get_project()
        platform = Platform.get_platform()

        if directory is not None and allow_remote and self.__use_remote_execution():

            self.info("Using a remote sandbox for artifact {} with directory '{}'".format(self.name, directory))

            sandbox = SandboxRemote(context, project,
                                    directory,
                                    plugin=self,
                                    stdout=stdout,
                                    stderr=stderr,
                                    config=config,
                                    specs=self.__remote_execution_specs,
                                    bare_directory=bare_directory,
                                    allow_real_directory=False)
            yield sandbox

        elif directory is not None and os.path.exists(directory):
            if allow_remote and self.__remote_execution_specs:
                self.warn("Artifact {} is configured to use remote execution but element plugin does not support it."
                          .format(self.name), detail="Element plugin '{kind}' does not support virtual directories."
                          .format(kind=self.get_kind()), warning_token="remote-failure")

                self.info("Falling back to local sandbox for artifact {}".format(self.name))

            sandbox = platform.create_sandbox(context, project,
                                              directory,
                                              plugin=self,
                                              stdout=stdout,
                                              stderr=stderr,
                                              config=config,
                                              bare_directory=bare_directory,
                                              allow_real_directory=not self.BST_VIRTUAL_DIRECTORY)
            yield sandbox

        else:
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Recursive contextmanager...
            with self.__sandbox(rootdir, stdout=stdout, stderr=stderr, config=config,
                                allow_remote=allow_remote, bare_directory=False) as sandbox:
                yield sandbox

            # Cleanup the build dir
            utils._force_rmtree(rootdir)

    def __compose_default_splits(self, defaults):
        project = self._get_project()

        element_public = _yaml.node_get(defaults, Mapping, 'public', default_value={})
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        if self.__is_junction:
            splits = _yaml.node_copy(element_splits)
        else:
            assert project._splits is not None

            splits = _yaml.node_copy(project._splits)
            # Extend project wide split rules with any split rules defined by the element
            _yaml.composite(splits, element_splits)

        _yaml.node_set(element_bst, 'split-rules', splits)
        _yaml.node_set(element_public, 'bst', element_bst)
        _yaml.node_set(defaults, 'public', element_public)

    def __init_defaults(self, plugin_conf):
        # Defaults are loaded once per class and then reused
        #
        if self.__defaults is None:
            defaults = _yaml.new_empty_node()

            if plugin_conf is not None:
                # Load the plugin's accompanying .yaml file if one was provided
                try:
                    defaults = _yaml.load(plugin_conf, os.path.basename(plugin_conf))
                except LoadError as e:
                    if e.reason != LoadErrorReason.MISSING_FILE:
                        raise e

            # Special case; compose any element-wide split-rules declarations
            self.__compose_default_splits(defaults)

            # Override the element's defaults with element specific
            # overrides from the project.conf
            project = self._get_project()
            if self.__is_junction:
                elements = project.first_pass_config.element_overrides
            else:
                elements = project.element_overrides

            overrides = _yaml.node_get(elements, Mapping, self.get_kind(), default_value=None)
            if overrides:
                _yaml.composite(defaults, overrides)

            # Set the data class wide
            type(self).__defaults = defaults

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __extract_environment(self, meta):
        default_env = _yaml.node_get(self.__defaults, Mapping, 'environment', default_value={})

        if self.__is_junction:
            environment = _yaml.new_empty_node()
        else:
            project = self._get_project()
            environment = _yaml.node_copy(project.base_environment)

        _yaml.composite(environment, default_env)
        _yaml.composite(environment, meta.environment)
        _yaml.node_final_assertions(environment)

        # Resolve variables in environment value strings
        final_env = {}
        for key, _ in self.node_items(environment):
            final_env[key] = self.node_subst_member(environment, key)

        return final_env

    def __extract_env_nocache(self, meta):
        if self.__is_junction:
            project_nocache = []
        else:
            project = self._get_project()
            project.ensure_fully_loaded()
            project_nocache = project.base_env_nocache

        default_nocache = _yaml.node_get(self.__defaults, list, 'environment-nocache', default_value=[])
        element_nocache = meta.env_nocache

        # Accumulate values from the element default, the project and the element
        # itself to form a complete list of nocache env vars.
        env_nocache = set(project_nocache + default_nocache + element_nocache)

        # Convert back to list now we know they're unique
        return list(env_nocache)

    # This will resolve the final variables to be used when
    # substituting command strings to be run in the sandbox
    #
    def __extract_variables(self, meta):
        default_vars = _yaml.node_get(self.__defaults, Mapping, 'variables',
                                      default_value={})

        project = self._get_project()
        if self.__is_junction:
            variables = _yaml.node_copy(project.first_pass_config.base_variables)
        else:
            project.ensure_fully_loaded()
            variables = _yaml.node_copy(project.base_variables)

        _yaml.composite(variables, default_vars)
        _yaml.composite(variables, meta.variables)
        _yaml.node_final_assertions(variables)

        for var in ('project-name', 'element-name', 'max-jobs'):
            provenance = _yaml.node_get_provenance(variables, var)
            if provenance and not provenance.is_synthetic:
                raise LoadError(LoadErrorReason.PROTECTED_VARIABLE_REDEFINED,
                                "{}: invalid redefinition of protected variable '{}'"
                                .format(provenance, var))

        return variables

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    def __extract_config(self, meta):

        # The default config is already composited with the project overrides
        config = _yaml.node_get(self.__defaults, Mapping, 'config', default_value={})
        config = _yaml.node_copy(config)

        _yaml.composite(config, meta.config)
        _yaml.node_final_assertions(config)

        return config

    # Sandbox-specific configuration data, to be passed to the sandbox's constructor.
    #
    def __extract_sandbox_config(self, meta):
        if self.__is_junction:
            sandbox_config = _yaml.new_node_from_dict({
                'build-uid': 0,
                'build-gid': 0
            })
        else:
            project = self._get_project()
            project.ensure_fully_loaded()
            sandbox_config = _yaml.node_copy(project._sandbox)

        # Get the platform to ask for host architecture
        platform = Platform.get_platform()
        host_arch = platform.get_host_arch()
        host_os = platform.get_host_os()

        # The default config is already composited with the project overrides
        sandbox_defaults = _yaml.node_get(self.__defaults, Mapping, 'sandbox', default_value={})
        sandbox_defaults = _yaml.node_copy(sandbox_defaults)

        _yaml.composite(sandbox_config, sandbox_defaults)
        _yaml.composite(sandbox_config, meta.sandbox)
        _yaml.node_final_assertions(sandbox_config)

        # Sandbox config, unlike others, has fixed members so we should validate them
        _yaml.node_validate(sandbox_config, ['build-uid', 'build-gid', 'build-os', 'build-arch'])

        build_arch = self.node_get_member(sandbox_config, str, 'build-arch', default=None)
        if build_arch:
            build_arch = Platform.canonicalize_arch(build_arch)
        else:
            build_arch = host_arch

        return SandboxConfig(
            self.node_get_member(sandbox_config, int, 'build-uid'),
            self.node_get_member(sandbox_config, int, 'build-gid'),
            self.node_get_member(sandbox_config, str, 'build-os', default=host_os),
            build_arch)

    # This makes a special exception for the split rules, which
    # elements may extend but whos defaults are defined in the project.
    #
    def __extract_public(self, meta):
        base_public = _yaml.node_get(self.__defaults, Mapping, 'public', default_value={})
        base_public = _yaml.node_copy(base_public)

        base_bst = _yaml.node_get(base_public, Mapping, 'bst', default_value={})
        base_splits = _yaml.node_get(base_bst, Mapping, 'split-rules', default_value={})

        element_public = _yaml.node_copy(meta.public)
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        # Allow elements to extend the default splits defined in their project or
        # element specific defaults
        _yaml.composite(base_splits, element_splits)

        _yaml.node_set(element_bst, 'split-rules', base_splits)
        _yaml.node_set(element_public, 'bst', element_bst)

        _yaml.node_final_assertions(element_public)

        # Also, resolve any variables in the public split rules directly
        for domain, splits in self.node_items(base_splits):
            splits = [
                self.__variables.subst(split.strip())
                for split in splits
            ]
            _yaml.node_set(base_splits, domain, splits)

        return element_public

    def __init_splits(self):
        bstdata = self.get_public_data('bst')
        splits = self.node_get_member(bstdata, dict, 'split-rules')
        self.__splits = {
            domain: re.compile('^(?:' + '|'.join([utils._glob2re(r) for r in rules]) + ')$')
            for domain, rules in self.node_items(splits)
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

        files_vdir, _ = self.__artifact.get_files()

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
            bstdata = self.get_public_data('bst')
            whitelist = _yaml.node_get(bstdata, list, 'overlap-whitelist', default_value=[])
            whitelist_expressions = [utils._glob2re(self.__variables.subst(exp.strip())) for exp in whitelist]
            expression = ('^(?:' + '|'.join(whitelist_expressions) + ')$')
            self.__whitelist_regex = re.compile(expression)
        return self.__whitelist_regex.match(os.path.join(os.sep, path))

    # __get_artifact_metadata_keys():
    #
    # Retrieve the strong and weak keys from the given artifact.
    #
    # Args:
    #     key (str): The artifact key, or None for the default key
    #
    # Returns:
    #     (str): The strong key
    #     (str): The weak key
    #
    def __get_artifact_metadata_keys(self, key=None):

        metadata_keys = self.__metadata_keys

        strong_key, weak_key, metadata_keys = self.__artifact.get_metadata_keys(key, metadata_keys)

        # Update keys if needed
        if metadata_keys:
            self.__metadata_keys = metadata_keys

        return (strong_key, weak_key)

    # __get_artifact_metadata_dependencies():
    #
    # Retrieve the hash of dependency strong keys from the given artifact.
    #
    # Args:
    #     key (str): The artifact key, or None for the default key
    #
    # Returns:
    #     (dict): A dictionary of element names and their strong keys
    #
    def __get_artifact_metadata_dependencies(self, key=None):

        metadata = [self.__metadata_dependencies, self.__metadata_keys]
        meta, meta_deps, meta_keys = self.__artifact.get_metadata_dependencies(key, *metadata)

        # Update deps if needed
        if meta_deps:
            self.__metadata_dependencies = meta_deps
            # Update keys if needed, no need to check if deps not updated
            if meta_keys:
                self.__metadata_keys = meta_keys

        return meta

    # __get_artifact_metadata_workspaced():
    #
    # Retrieve the hash of dependency strong keys from the given artifact.
    #
    # Args:
    #     key (str): The artifact key, or None for the default key
    #
    # Returns:
    #     (bool): Whether the given artifact was workspaced
    #

    def __get_artifact_metadata_workspaced(self, key=None):

        metadata = [self.__metadata_workspaced, self.__metadata_keys]
        workspaced, meta_workspaced, meta_keys = self.__artifact.get_metadata_workspaced(key, *metadata)

        # Update workspaced if needed
        if meta_workspaced:
            self.__metadata_workspaced = meta_workspaced
            # Update keys if needed, no need to check if workspaced not updated
            if meta_keys:
                self.__metadata_keys = meta_keys

        return workspaced

    # __get_artifact_metadata_workspaced_dependencies():
    #
    # Retrieve the hash of dependency strong keys from the given artifact.
    #
    # Args:
    #     key (str): The artifact key, or None for the default key
    #
    # Returns:
    #     (list): List of which dependencies are workspaced
    #
    def __get_artifact_metadata_workspaced_dependencies(self, key=None):

        metadata = [self.__metadata_workspaced_dependencies, self.__metadata_keys]
        workspaced, meta_workspaced_deps,\
            meta_keys = self.__artifact.get_metadata_workspaced_dependencies(key, *metadata)

        # Update workspaced if needed
        if meta_workspaced_deps:
            self.__metadata_workspaced_dependencies = meta_workspaced_deps
            # Update keys if needed, no need to check if workspaced not updated
            if meta_keys:
                self.__metadata_keys = meta_keys

        return workspaced

    # __load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    def __load_public_data(self):
        assert self.__dynamic_public is None

        self.__dynamic_public = self.__artifact.load_public_data()

    def __load_build_result(self, keystrength):
        self.__assert_cached(keystrength=keystrength)
        assert self.__build_result is None

        # _get_cache_key with _KeyStrength.STRONG returns self.__cache_key, which can be `None`
        # leading to a failed assertion from get_artifact_directory() using get_artifact_name(),
        # so explicility pass self.__strict_cache_key
        key = self.__weak_cache_key if keystrength is _KeyStrength.WEAK else self.__strict_cache_key

        self.__build_result = self.__artifact.load_build_result(key)

    def __get_build_result(self, keystrength):
        if keystrength is None:
            keystrength = _KeyStrength.STRONG if self._get_context().get_strict() else _KeyStrength.WEAK

        if self.__build_result is None:
            self.__load_build_result(keystrength)

        return self.__build_result

    def __cached_success(self, keystrength):
        if not self.__is_cached(keystrength=keystrength):
            return False

        success, _, _ = self.__get_build_result(keystrength=keystrength)
        return success

    def __get_cache_keys_for_commit(self):
        keys = []

        # tag with strong cache key based on dependency versions used for the build
        keys.append(self._get_cache_key(strength=_KeyStrength.STRONG))

        # also store under weak cache key
        keys.append(self._get_cache_key(strength=_KeyStrength.WEAK))

        return utils._deduplicate(keys)

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
    def __pull_strong(self, *, progress=None, subdir=None, excluded_subdirs=None):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)
        key = self.__strict_cache_key
        if not self.__artifacts.pull(self, key, progress=progress, subdir=subdir,
                                     excluded_subdirs=excluded_subdirs):
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
    #     progress (callable): The progress callback, if any
    #     subdir (str): The optional specific subdir to pull
    #     excluded_subdirs (list): The optional list of subdirs to not pull
    #
    # Returns:
    #     (bool): Whether or not the pull was successful
    #
    def __pull_weak(self, *, progress=None, subdir=None, excluded_subdirs=None):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)
        if not self.__artifacts.pull(self, weak_key, progress=progress, subdir=subdir,
                                     excluded_subdirs=excluded_subdirs):
            return False

        # extract strong cache key from this newly fetched artifact
        self._pull_done()

        # create tag for strong cache key
        key = self._get_cache_key(strength=_KeyStrength.STRONG)
        self.__artifacts.link_key(self, weak_key, key)

        return True

    # __pull_directories():
    #
    # Which directories to include or exclude given the current
    # context
    #
    # Returns:
    #     subdir (str): The optional specific subdir to include, based
    #                   on user context
    #     excluded_subdirs (list): The optional list of subdirs to not
    #                              pull, referenced against subdir value
    #
    def __pull_directories(self):
        context = self._get_context()

        # Current default exclusions on pull
        excluded_subdirs = ["buildtree"]
        subdir = ''

        # If buildtrees are to be pulled, remove the value from exclusion list
        # and set specific subdir
        if context.pull_buildtrees:
            subdir = "buildtree"
            excluded_subdirs.remove(subdir)

        return (subdir, excluded_subdirs)

    # __cache_sources():
    #
    # Caches the sources into the local CAS
    #
    def __cache_sources(self):
        sources = self.__sources
        if sources and not self._source_cached():
            sources[-1]._cache(sources[:-1])

    # __update_state_recursively()
    #
    # Update the state of all reverse dependencies, recursively.
    #
    def __update_state_recursively(self):
        queue = _UniquePriorityQueue()
        queue.push(self._unique_id, self)

        while queue:
            element = queue.pop()

            old_ready_for_runtime = element.__ready_for_runtime
            element._update_state()

            if element.__ready_for_runtime != old_ready_for_runtime:
                for rdep in element.__reverse_dependencies:
                    queue.push(rdep._unique_id, rdep)


def _overlap_error_detail(f, forbidden_overlap_elements, elements):
    if forbidden_overlap_elements:
        return ("/{}: {} {} not permitted to overlap other elements, order {} \n"
                .format(f, " and ".join(forbidden_overlap_elements),
                        "is" if len(forbidden_overlap_elements) == 1 else "are",
                        " above ".join(reversed(elements))))
    else:
        return ""
