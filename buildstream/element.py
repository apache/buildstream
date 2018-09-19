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

  For the purpose of ``bst source bundle``, an Element may optionally implement this.


Class Reference
---------------
"""

import os
import re
import stat
import copy
from collections import Mapping, OrderedDict
from contextlib import contextmanager
from enum import Enum
import tempfile
import time
import shutil

from . import _yaml
from ._variables import Variables
from ._versions import BST_CORE_ARTIFACT_VERSION
from ._exceptions import BstError, LoadError, LoadErrorReason, ImplError, ErrorDomain
from .utils import UtilError
from . import Plugin, Consistency
from . import SandboxFlags
from . import utils
from . import _cachekey
from . import _signals
from . import _site
from ._platform import Platform
from .sandbox._config import SandboxConfig


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


class Scope(Enum):
    """Types of scope for a given element"""

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


class ElementError(BstError):
    """This exception should be raised by :class:`.Element` implementations
    to report errors to the user.

    Args:
       message (str): The error message to report to the user
       detail (str): A possibly multiline, more detailed error message
       reason (str): An optional machine readable reason string, used for test cases
       temporary (bool): An indicator to whether the error may occur if the operation was run again. (*Since: 1.2*)
    """
    def __init__(self, message, *, detail=None, reason=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.ELEMENT, reason=reason, temporary=temporary)


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = {}               # The defaults from the yaml file and project
    __defaults_set = False        # Flag, in case there are no defaults at all
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

    def __init__(self, context, project, artifacts, meta, plugin_conf):

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
        self.__sources = []                     # List of Sources
        self.__weak_cache_key = None            # Our cached weak cache key
        self.__strict_cache_key = None          # Our cached cache key for strict builds
        self.__artifacts = artifacts            # Artifact cache
        self.__consistency = Consistency.INCONSISTENT  # Cached overall consistency state
        self.__cached = None                    # Whether we have a cached artifact
        self.__strong_cached = None             # Whether we have a cached artifact
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

        # hash tables of loaded artifact metadata, hashed by key
        self.__metadata_keys = {}                     # Strong and weak keys for this key
        self.__metadata_dependencies = {}             # Dictionary of dependency strong keys
        self.__metadata_workspaced = {}               # Boolean of whether it's workspaced
        self.__metadata_workspaced_dependencies = {}  # List of which dependencies are workspaced

        # Ensure we have loaded this class's defaults
        self.__init_defaults(plugin_conf)

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(meta)
        variables['element-name'] = self.name
        self.__variables = Variables(variables)

        # Collect the composited environment now that we have variables
        env = self.__extract_environment(meta)
        self.__environment = env

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

        # Extract Sandbox config
        self.__sandbox_config = self.__extract_sandbox_config(meta)

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
        pass

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
        - The cwd is `self.get_variable('build_root')/self.normal_name`.
        - $PREFIX is set to `self.get_variable('install_root')`.
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

    def dependencies(self, scope, *, recurse=True, visited=None, recursed=False):
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
        if visited is None:
            visited = {}

        full_name = self._get_full_name()

        scope_set = set((Scope.BUILD, Scope.RUN)) if scope == Scope.ALL else set((scope,))

        if full_name in visited and scope_set.issubset(visited[full_name]):
            return

        should_yield = False
        if full_name not in visited:
            visited[full_name] = scope_set
            should_yield = True
        else:
            visited[full_name] |= scope_set

        if recurse or not recursed:
            if scope == Scope.ALL:
                for dep in self.__build_dependencies:
                    yield from dep.dependencies(Scope.ALL, recurse=recurse,
                                                visited=visited, recursed=True)

                for dep in self.__runtime_dependencies:
                    if dep not in self.__build_dependencies:
                        yield from dep.dependencies(Scope.ALL, recurse=recurse,
                                                    visited=visited, recursed=True)

            elif scope == Scope.BUILD:
                for dep in self.__build_dependencies:
                    yield from dep.dependencies(Scope.RUN, recurse=recurse,
                                                visited=visited, recursed=True)

            elif scope == Scope.RUN:
                for dep in self.__runtime_dependencies:
                    yield from dep.dependencies(Scope.RUN, recurse=recurse,
                                                visited=visited, recursed=True)

        # Yeild self only at the end, after anything needed has been traversed
        if should_yield and (recurse or recursed) and (scope == Scope.ALL or scope == Scope.RUN):
            yield self

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

    def node_subst_member(self, node, member_name, default=utils._sentinel):
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
            raise LoadError(e.reason, '{}: {}'.format(provenance, str(e))) from e

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
                raise LoadError(e.reason, '{}: {}'.format(provenance, str(e))) from e
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
            raise LoadError(e.reason, '{}: {}'.format(provenance, str(e))) from e

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
            # Get the extracted artifact
            artifact_base, _ = self.__extract()
            artifact = os.path.join(artifact_base, 'files')

            # Hard link it into the staging area
            #
            basedir = sandbox.get_directory()
            stagedir = basedir \
                if path is None \
                else os.path.join(basedir, path.lstrip(os.sep))

            files = list(self.__compute_splits(include, exclude, orphans))

            # We must not hardlink files whose mtimes we want to update
            if update_mtimes:
                link_files = [f for f in files if f not in update_mtimes]
                copy_files = [f for f in files if f in update_mtimes]
            else:
                link_files = files
                copy_files = []

            link_result = utils.link_files(artifact, stagedir, files=link_files,
                                           report_written=True)
            copy_result = utils.copy_files(artifact, stagedir, files=copy_files,
                                           report_written=True)

            cur_time = time.time()

            for f in copy_result.files_written:
                os.utime(os.path.join(stagedir, f), times=(cur_time, cur_time))

        return link_result.combine(copy_result)

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
        old_dep_keys = {}
        workspace = self._get_workspace()

        if self.__can_build_incrementally() and workspace.last_successful:
            old_dep_keys = self.__get_artifact_metadata_dependencies(workspace.last_successful)

        for dep in self.dependencies(scope):
            # If we are workspaced, and we therefore perform an
            # incremental build, we must ensure that we update the mtimes
            # of any files created by our dependencies since the last
            # successful build.
            to_update = None
            if workspace and old_dep_keys:
                dep.__assert_cached()

                if dep.name in old_dep_keys:
                    key_new = dep._get_cache_key()
                    key_old = old_dep_keys[dep.name]

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
            overlap_error = overlap_warning = False
            error_detail = warning_detail = "Staged files overwrite existing files in staging area:\n"
            for f, elements in overlaps.items():
                overlap_error_elements = []
                overlap_warning_elements = []
                # The bottom item overlaps nothing
                overlapping_elements = elements[1:]
                for elm in overlapping_elements:
                    element = self.search(scope, elm)
                    element_project = element._get_project()
                    if not element.__file_is_whitelisted(f):
                        if element_project.fail_on_overlap:
                            overlap_error_elements.append(elm)
                            overlap_error = True
                        else:
                            overlap_warning_elements.append(elm)
                            overlap_warning = True

                warning_detail += _overlap_error_detail(f, overlap_warning_elements, elements)
                error_detail += _overlap_error_detail(f, overlap_error_elements, elements)

            if overlap_warning:
                self.warn("Non-whitelisted overlaps detected", detail=warning_detail)
            if overlap_error:
                raise ElementError("Non-whitelisted overlaps detected and fail-on-overlaps is set",
                                   detail=error_detail, reason="overlap-error")

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
            commands = self.node_get_member(bstdata, list, 'integration-commands', [])
            for i in range(len(commands)):
                cmd = self.node_subst_list_element(bstdata, 'integration-commands', [i])
                self.status("Running integration command", detail=cmd)
                exitcode = sandbox.run(['sh', '-e', '-c', cmd], 0, env=environment, cwd='/')
                if exitcode != 0:
                    raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))

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

        data = self.__dynamic_public.get(domain)
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

        self.__dynamic_public[domain] = data

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
        if varname in self.__variables.variables:
            return self.__variables.variables[varname]

        return None

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _new_from_meta():
    #
    # Recursively instantiate a new Element instance, it's sources
    # and it's dependencies from a meta element.
    #
    # Args:
    #    artifacts (ArtifactCache): The artifact cache
    #    meta (MetaElement): The meta element
    #
    # Returns:
    #    (Element): A newly created Element instance
    #
    @classmethod
    def _new_from_meta(cls, meta, artifacts):

        if not meta.first_pass:
            meta.project.ensure_fully_loaded()

        if meta in cls.__instantiated_elements:
            return cls.__instantiated_elements[meta]

        element = meta.project.create_element(artifacts, meta, first_pass=meta.first_pass)
        cls.__instantiated_elements[meta] = element

        # Instantiate sources
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
            dependency = Element._new_from_meta(meta_dep, artifacts)
            element.__runtime_dependencies.append(dependency)
        for meta_dep in meta.build_dependencies:
            dependency = Element._new_from_meta(meta_dep, artifacts)
            element.__build_dependencies.append(dependency)

        return element

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
        return self.__cached

    # _buildable():
    #
    # Returns:
    #    (bool): Whether this element can currently be built
    #
    def _buildable(self):
        if self._get_consistency() != Consistency.CACHED:
            return False

        for dependency in self.dependencies(Scope.BUILD):
            # In non-strict mode an element's strong cache key may not be available yet
            # even though an artifact is available in the local cache. This can happen
            # if the pull job is still pending as the remote cache may have an artifact
            # that matches the strict cache key, which is preferred over a locally
            # cached artifact with a weak cache key match.
            if not dependency._cached() or not dependency._get_cache_key(strength=_KeyStrength.STRONG):
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
            return

        if self.__weak_cache_key is None:
            # Calculate weak cache key
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

            self.__weak_cache_key = self.__calculate_cache_key(dependencies)

            if self.__weak_cache_key is None:
                # Weak cache key could not be calculated yet
                return

        if not context.get_strict():
            # Full cache query in non-strict mode requires both the weak and
            # strict cache keys. However, we need to determine as early as
            # possible whether a build is pending to discard unstable cache keys
            # for workspaced elements. For this cache check the weak cache keys
            # are sufficient. However, don't update the `cached` attributes
            # until the full cache query below.
            cached = self.__artifacts.contains(self, self.__weak_cache_key)
            if (not self.__assemble_scheduled and not self.__assemble_done and
                    not cached and not self._pull_pending()):
                # For uncached workspaced elements, assemble is required
                # even if we only need the cache key
                if self._is_required() or self._get_workspace():
                    self._schedule_assemble()
                    return

        if self.__strict_cache_key is None:
            dependencies = [
                e.__strict_cache_key for e in self.dependencies(Scope.BUILD)
            ]
            self.__strict_cache_key = self.__calculate_cache_key(dependencies)

            if self.__strict_cache_key is None:
                # Strict cache key could not be calculated yet
                return

        # Query caches now that the weak and strict cache keys are available
        key_for_cache_lookup = self.__strict_cache_key if context.get_strict() else self.__weak_cache_key
        if not self.__cached:
            self.__cached = self.__artifacts.contains(self, key_for_cache_lookup)
        if not self.__strong_cached:
            self.__strong_cached = self.__artifacts.contains(self, self.__strict_cache_key)

        if (not self.__assemble_scheduled and not self.__assemble_done and
                not self.__cached and not self._pull_pending()):
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
                self.__cache_key = self.__calculate_cache_key(dependencies)

            if self.__cache_key is None:
                # Strong cache key could not be calculated yet
                return

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
    # the element and it's sources.
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
            raise ElementError("{}: {}".format(self, e), reason=e.reason) from e

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

        self._update_state()

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
        for source in self.__sources:
            old_ref = source.get_ref()
            new_ref = source._track()
            refs.append((source._get_unique_id(), new_ref))

            # Complimentary warning that the new ref will be unused.
            if old_ref != new_ref and self._get_workspace():
                detail = "This source has an open workspace.\n" \
                    + "To start using the new reference, please close the existing workspace."
                source.warn("Updated reference will be ignored as source has open workspace", detail=detail)

        return refs

    # _prepare_sandbox():
    #
    # This stages things for either _shell() (below) or also
    # is used to stage things by the `bst checkout` codepath
    #
    @contextmanager
    def _prepare_sandbox(self, scope, directory, deps='run', integrate=True):
        with self.__sandbox(directory, config=self.__sandbox_config) as sandbox:

            # Configure always comes first, and we need it.
            self.configure_sandbox(sandbox)

            # Stage something if we need it
            if not directory:
                if scope == Scope.BUILD:
                    self.stage(sandbox)
                elif scope == Scope.RUN:
                    # Stage deps in the sandbox root
                    if deps == 'run':
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
        sandbox_root = sandbox.get_directory()
        host_directory = os.path.join(sandbox_root, directory.lstrip(os.sep))
        self._stage_sources_at(host_directory, mount_workspaces=mount_workspaces)

    # _stage_sources_at():
    #
    # Stage this element's sources to a directory
    #
    # Args:
    #     directory (str): An absolute path to stage the sources at
    #     mount_workspaces (bool): mount workspaces if True, copy otherwise
    #
    def _stage_sources_at(self, directory, mount_workspaces=True):
        with self.timed_activity("Staging sources", silent_nested=True):

            if os.path.isdir(directory) and os.listdir(directory):
                raise ElementError("Staging directory '{}' is not empty".format(directory))

            workspace = self._get_workspace()
            if workspace:
                # If mount_workspaces is set and we're doing incremental builds,
                # the workspace is already mounted into the sandbox.
                if not (mount_workspaces and self.__can_build_incrementally()):
                    with self.timed_activity("Staging local files at {}".format(workspace.path)):
                        workspace.stage(directory)
            else:
                # No workspace, stage directly
                for source in self.sources():
                    source._stage(directory)

        # Ensure deterministic mtime of sources at build time
        utils._set_deterministic_mtime(directory)
        # Ensure deterministic owners of sources at build time
        utils._set_deterministic_user(directory)

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

        self._update_state()

        if self._get_workspace() and self._cached():
            #
            # Note that this block can only happen in the
            # main process, since `self._cached()` cannot
            # be true when assembly is completed in the task.
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
        assert not self._cached()

        context = self._get_context()
        with self._output_file() as output_file:

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Cleanup the build directory on explicit SIGTERM
            def cleanup_rootdir():
                utils._force_rmtree(rootdir)

            with _signals.terminator(cleanup_rootdir), \
                self.__sandbox(rootdir, output_file, output_file, self.__sandbox_config) as sandbox:  # nopep8

                sandbox_root = sandbox.get_directory()

                # By default, the dynamic public data is the same as the static public data.
                # The plugin's assemble() method may modify this, though.
                self.__dynamic_public = _yaml.node_copy(self.__public)

                # Call the abstract plugin methods
                try:
                    # Step 1 - Configure
                    self.configure_sandbox(sandbox)
                    # Step 2 - Stage
                    self.stage(sandbox)
                    # Step 3 - Prepare
                    self.__prepare(sandbox)
                    # Step 4 - Assemble
                    collect = self.assemble(sandbox)
                except BstError as e:
                    # If an error occurred assembling an element in a sandbox,
                    # then tack on the sandbox directory to the error
                    e.sandbox = rootdir

                    # If there is a workspace open on this element, it will have
                    # been mounted for sandbox invocations instead of being staged.
                    #
                    # In order to preserve the correct failure state, we need to
                    # copy over the workspace files into the appropriate directory
                    # in the sandbox.
                    #
                    workspace = self._get_workspace()
                    if workspace and self.__staged_sources_directory:
                        sandbox_root = sandbox.get_directory()
                        sandbox_path = os.path.join(sandbox_root,
                                                    self.__staged_sources_directory.lstrip(os.sep))
                        try:
                            utils.copy_files(workspace.path, sandbox_path)
                        except UtilError as e:
                            self.warn("Failed to preserve workspace state for failed build sysroot: {}"
                                      .format(e))

                    raise

                collectdir = os.path.join(sandbox_root, collect.lstrip(os.sep))
                if not os.path.exists(collectdir):
                    raise ElementError(
                        "Directory '{}' was not found inside the sandbox, "
                        "unable to collect artifact contents"
                        .format(collect))

                # At this point, we expect an exception was raised leading to
                # an error message, or we have good output to collect.

                # Create artifact directory structure
                assembledir = os.path.join(rootdir, 'artifact')
                filesdir = os.path.join(assembledir, 'files')
                logsdir = os.path.join(assembledir, 'logs')
                metadir = os.path.join(assembledir, 'meta')
                os.mkdir(assembledir)
                os.mkdir(filesdir)
                os.mkdir(logsdir)
                os.mkdir(metadir)

                # Hard link files from collect dir to files directory
                utils.link_files(collectdir, filesdir)

                # Copy build log
                log_filename = context.get_log_filename()
                if log_filename:
                    shutil.copyfile(log_filename, os.path.join(logsdir, 'build.log'))

                # Store public data
                _yaml.dump(_yaml.node_sanitize(self.__dynamic_public), os.path.join(metadir, 'public.yaml'))

                # ensure we have cache keys
                self._assemble_done()

                # Store keys.yaml
                _yaml.dump(_yaml.node_sanitize({
                    'strong': self._get_cache_key(),
                    'weak': self._get_cache_key(_KeyStrength.WEAK),
                }), os.path.join(metadir, 'keys.yaml'))

                # Store dependencies.yaml
                _yaml.dump(_yaml.node_sanitize({
                    e.name: e._get_cache_key() for e in self.dependencies(Scope.BUILD)
                }), os.path.join(metadir, 'dependencies.yaml'))

                # Store workspaced.yaml
                _yaml.dump(_yaml.node_sanitize({
                    'workspaced': True if self._get_workspace() else False
                }), os.path.join(metadir, 'workspaced.yaml'))

                # Store workspaced-dependencies.yaml
                _yaml.dump(_yaml.node_sanitize({
                    'workspaced-dependencies': [
                        e.name for e in self.dependencies(Scope.BUILD)
                        if e._get_workspace()
                    ]
                }), os.path.join(metadir, 'workspaced-dependencies.yaml'))

                with self.timed_activity("Caching artifact"):
                    artifact_size = utils._get_dir_size(assembledir)
                    self.__artifacts.commit(self, assembledir, self.__get_cache_keys_for_commit())

            # Finally cleanup the build dir
            cleanup_rootdir()

        return artifact_size

    # _pull_pending()
    #
    # Check whether the artifact will be pulled.
    #
    # Returns:
    #   (bool): Whether a pull operation is pending
    #
    def _pull_pending(self):
        if self._get_workspace():
            # Workspace builds are never pushed to artifact servers
            return False

        if self.__strong_cached:
            # Artifact already in local cache
            return False

        # Pull is pending if artifact remote server available
        # and pull has not been attempted yet
        return self.__artifacts.has_fetch_remotes(element=self) and not self.__pull_done

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

        self._update_state()

    def _pull_strong(self, *, progress=None):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)

        key = self.__strict_cache_key
        if not self.__artifacts.pull(self, key, progress=progress):
            return False

        # update weak ref by pointing it to this newly fetched artifact
        self.__artifacts.link_key(self, key, weak_key)

        return True

    def _pull_weak(self, *, progress=None):
        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)

        if not self.__artifacts.pull(self, weak_key, progress=progress):
            return False

        # extract strong cache key from this newly fetched artifact
        self._pull_done()

        # create tag for strong cache key
        key = self._get_cache_key(strength=_KeyStrength.STRONG)
        self.__artifacts.link_key(self, weak_key, key)

        return True

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

        # Attempt to pull artifact without knowing whether it's available
        pulled = self._pull_strong(progress=progress)

        if not pulled and not self._cached() and not context.get_strict():
            pulled = self._pull_weak(progress=progress)

        if not pulled:
            return False

        # Notify successfull download
        return True

    # _skip_push():
    #
    # Determine whether we should create a push job for this element.
    #
    # Returns:
    #   (bool): True if this element does not need a push job to be created
    #
    def _skip_push(self):
        if not self.__artifacts.has_push_remotes(element=self):
            # No push remotes for this element's project
            return True

        if not self._cached():
            return True

        # Do not push tained artifact
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
    #
    # Returns: Exit code
    #
    # If directory is not specified, one will be staged using scope
    def _shell(self, scope=None, directory=None, *, mounts=None, isolate=False, prompt=None, command=None):

        with self._prepare_sandbox(scope, directory) as sandbox:
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
            for source in self.sources():
                source._init_workspace(temp)

            # Now hardlink the files into the workspace target.
            utils.link_files(temp, workspace.path)

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
            # that it's directory went missing
            #
            fullpath = workspace.get_absolute_path()
            if not os.path.exists(fullpath):
                self.__consistency = Consistency.INCONSISTENT
        else:

            # Determine overall consistency of the element
            for source in self.__sources:
                source._update_state()
                source_consistency = source._get_consistency()
                self.__consistency = min(self.__consistency, source_consistency)

    # __calculate_cache_key():
    #
    # Calculates the cache key
    #
    # Returns:
    #    (str): A hex digest cache key for this Element, or None
    #
    # None is returned if information for the cache key is missing.
    #
    def __calculate_cache_key(self, dependencies):
        # No cache keys for dependencies which have no cache keys
        if None in dependencies:
            return None

        # Generate dict that is used as base for all cache keys
        if self.__cache_key_dict is None:
            # Filter out nocache variables from the element's environment
            cache_env = {
                key: value
                for key, value in self.node_items(self.__environment)
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
                'cache': type(self.__artifacts).__name__
            }

            # fail-on-overlap setting cannot affect elements without dependencies
            if project.fail_on_overlap and dependencies:
                self.__cache_key_dict['fail-on-overlap'] = True

        cache_key_dict = self.__cache_key_dict.copy()
        cache_key_dict['dependencies'] = dependencies

        return _cachekey.generate_key(cache_key_dict)

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
                workspace.prepared = True

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
            workspaced = self.__get_artifact_metadata_workspaced()

            # Whether this artifact's dependencies have workspaces
            workspaced_dependencies = self.__get_artifact_metadata_workspaced_dependencies()

            # Other conditions should be or-ed
            self.__tainted = workspaced or workspaced_dependencies

        return self.__tainted

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
    #
    # Yields:
    #    (Sandbox): A usable sandbox
    #
    @contextmanager
    def __sandbox(self, directory, stdout=None, stderr=None, config=None):
        context = self._get_context()
        project = self._get_project()
        platform = Platform.get_platform()

        if directory is not None and os.path.exists(directory):
            sandbox = platform.create_sandbox(context, project,
                                              directory,
                                              stdout=stdout,
                                              stderr=stderr,
                                              config=config)
            yield sandbox

        else:
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Recursive contextmanager...
            with self.__sandbox(rootdir, stdout=stdout, stderr=stderr, config=config) as sandbox:
                yield sandbox

            # Cleanup the build dir
            utils._force_rmtree(rootdir)

    def __compose_default_splits(self, defaults):
        project = self._get_project()

        element_public = _yaml.node_get(defaults, Mapping, 'public', default_value={})
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        if self.__is_junction:
            splits = _yaml.node_chain_copy(element_splits)
        else:
            assert project._splits is not None

            splits = _yaml.node_chain_copy(project._splits)
            # Extend project wide split rules with any split rules defined by the element
            _yaml.composite(splits, element_splits)

        element_bst['split-rules'] = splits
        element_public['bst'] = element_bst
        defaults['public'] = element_public

    def __init_defaults(self, plugin_conf):

        # Defaults are loaded once per class and then reused
        #
        if not self.__defaults_set:

            # Load the plugin's accompanying .yaml file if one was provided
            defaults = {}
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

            overrides = elements.get(self.get_kind())
            if overrides:
                _yaml.composite(defaults, overrides)

            # Set the data class wide
            type(self).__defaults = defaults
            type(self).__defaults_set = True

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __extract_environment(self, meta):
        default_env = _yaml.node_get(self.__defaults, Mapping, 'environment', default_value={})

        if self.__is_junction:
            environment = {}
        else:
            project = self._get_project()
            environment = _yaml.node_chain_copy(project.base_environment)

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
            variables = _yaml.node_chain_copy(project.first_pass_config.base_variables)
        else:
            project.ensure_fully_loaded()
            variables = _yaml.node_chain_copy(project.base_variables)

        _yaml.composite(variables, default_vars)
        _yaml.composite(variables, meta.variables)
        _yaml.node_final_assertions(variables)

        for var in ('project-name', 'element-name', 'max-jobs'):
            provenance = _yaml.node_get_provenance(variables, var)
            if provenance and provenance.filename != '':
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
        config = _yaml.node_chain_copy(config)

        _yaml.composite(config, meta.config)
        _yaml.node_final_assertions(config)

        return config

    # Sandbox-specific configuration data, to be passed to the sandbox's constructor.
    #
    def __extract_sandbox_config(self, meta):
        if self.__is_junction:
            sandbox_config = {'build-uid': 0,
                              'build-gid': 0}
        else:
            project = self._get_project()
            project.ensure_fully_loaded()
            sandbox_config = _yaml.node_chain_copy(project._sandbox)

        # The default config is already composited with the project overrides
        sandbox_defaults = _yaml.node_get(self.__defaults, Mapping, 'sandbox', default_value={})
        sandbox_defaults = _yaml.node_chain_copy(sandbox_defaults)

        _yaml.composite(sandbox_config, sandbox_defaults)
        _yaml.composite(sandbox_config, meta.sandbox)
        _yaml.node_final_assertions(sandbox_config)

        # Sandbox config, unlike others, has fixed members so we should validate them
        _yaml.node_validate(sandbox_config, ['build-uid', 'build-gid'])

        return SandboxConfig(self.node_get_member(sandbox_config, int, 'build-uid'),
                             self.node_get_member(sandbox_config, int, 'build-gid'))

    # This makes a special exception for the split rules, which
    # elements may extend but whos defaults are defined in the project.
    #
    def __extract_public(self, meta):
        base_public = _yaml.node_get(self.__defaults, Mapping, 'public', default_value={})
        base_public = _yaml.node_chain_copy(base_public)

        base_bst = _yaml.node_get(base_public, Mapping, 'bst', default_value={})
        base_splits = _yaml.node_get(base_bst, Mapping, 'split-rules', default_value={})

        element_public = _yaml.node_chain_copy(meta.public)
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        # Allow elements to extend the default splits defined in their project or
        # element specific defaults
        _yaml.composite(base_splits, element_splits)

        element_bst['split-rules'] = base_splits
        element_public['bst'] = element_bst

        _yaml.node_final_assertions(element_public)

        # Also, resolve any variables in the public split rules directly
        for domain, splits in self.node_items(base_splits):
            base_splits[domain] = [
                self.__variables.subst(split.strip())
                for split in splits
            ]

        return element_public

    def __init_splits(self):
        bstdata = self.get_public_data('bst')
        splits = bstdata.get('split-rules')
        self.__splits = {
            domain: re.compile('^(?:' + '|'.join([utils._glob2re(r) for r in rules]) + ')$')
            for domain, rules in self.node_items(splits)
        }

    def __compute_splits(self, include=None, exclude=None, orphans=True):
        artifact_base, _ = self.__extract()
        basedir = os.path.join(artifact_base, 'files')

        # No splitting requested, just report complete artifact
        if orphans and not (include or exclude):
            for filename in utils.list_relative_paths(basedir):
                yield filename
            return

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

        # FIXME: Instead of listing the paths in an extracted artifact,
        #        we should be using a manifest loaded from the artifact
        #        metadata.
        #
        element_files = [
            os.path.join(os.sep, filename)
            for filename in utils.list_relative_paths(basedir)
        ]

        for filename in element_files:
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

            if include_file and not exclude_file:
                yield filename.lstrip(os.sep)

    def __file_is_whitelisted(self, pattern):
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
        return self.__whitelist_regex.match(pattern)

    # __extract():
    #
    # Extract an artifact and return the directory
    #
    # Args:
    #    key (str): The key for the artifact to extract,
    #               or None for the default key
    #
    # Returns:
    #    (str): The path to the extracted artifact
    #    (str): The chosen key
    #
    def __extract(self, key=None):

        if key is None:
            context = self._get_context()
            key = self.__strict_cache_key

            # Use weak cache key, if artifact is missing for strong cache key
            # and the context allows use of weak cache keys
            if not context.get_strict() and not self.__artifacts.contains(self, key):
                key = self._get_cache_key(strength=_KeyStrength.WEAK)

        return (self.__artifacts.extract(self, key), key)

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

        # Now extract it and possibly derive the key
        artifact_base, key = self.__extract(key)

        # Now try the cache, once we're sure about the key
        if key in self.__metadata_keys:
            return (self.__metadata_keys[key]['strong'],
                    self.__metadata_keys[key]['weak'])

        # Parse the expensive yaml now and cache the result
        meta_file = os.path.join(artifact_base, 'meta', 'keys.yaml')
        meta = _yaml.load(meta_file)
        strong_key = meta['strong']
        weak_key = meta['weak']

        assert key == strong_key or key == weak_key

        self.__metadata_keys[strong_key] = meta
        self.__metadata_keys[weak_key] = meta
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

        # Extract it and possibly derive the key
        artifact_base, key = self.__extract(key)

        # Now try the cache, once we're sure about the key
        if key in self.__metadata_dependencies:
            return self.__metadata_dependencies[key]

        # Parse the expensive yaml now and cache the result
        meta_file = os.path.join(artifact_base, 'meta', 'dependencies.yaml')
        meta = _yaml.load(meta_file)

        # Cache it under both strong and weak keys
        strong_key, weak_key = self.__get_artifact_metadata_keys(key)
        self.__metadata_dependencies[strong_key] = meta
        self.__metadata_dependencies[weak_key] = meta
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

        # Extract it and possibly derive the key
        artifact_base, key = self.__extract(key)

        # Now try the cache, once we're sure about the key
        if key in self.__metadata_workspaced:
            return self.__metadata_workspaced[key]

        # Parse the expensive yaml now and cache the result
        meta_file = os.path.join(artifact_base, 'meta', 'workspaced.yaml')
        meta = _yaml.load(meta_file)
        workspaced = meta['workspaced']

        # Cache it under both strong and weak keys
        strong_key, weak_key = self.__get_artifact_metadata_keys(key)
        self.__metadata_workspaced[strong_key] = workspaced
        self.__metadata_workspaced[weak_key] = workspaced
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

        # Extract it and possibly derive the key
        artifact_base, key = self.__extract(key)

        # Now try the cache, once we're sure about the key
        if key in self.__metadata_workspaced_dependencies:
            return self.__metadata_workspaced_dependencies[key]

        # Parse the expensive yaml now and cache the result
        meta_file = os.path.join(artifact_base, 'meta', 'workspaced-dependencies.yaml')
        meta = _yaml.load(meta_file)
        workspaced = meta['workspaced-dependencies']

        # Cache it under both strong and weak keys
        strong_key, weak_key = self.__get_artifact_metadata_keys(key)
        self.__metadata_workspaced_dependencies[strong_key] = workspaced
        self.__metadata_workspaced_dependencies[weak_key] = workspaced
        return workspaced

    # __load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    def __load_public_data(self):
        self.__assert_cached()
        assert self.__dynamic_public is None

        # Load the public data from the artifact
        artifact_base, _ = self.__extract()
        metadir = os.path.join(artifact_base, 'meta')
        self.__dynamic_public = _yaml.load(os.path.join(metadir, 'public.yaml'))

    def __get_cache_keys_for_commit(self):
        keys = []

        # tag with strong cache key based on dependency versions used for the build
        keys.append(self._get_cache_key(strength=_KeyStrength.STRONG))

        # also store under weak cache key
        keys.append(self._get_cache_key(strength=_KeyStrength.WEAK))

        return utils._deduplicate(keys)


def _overlap_error_detail(f, forbidden_overlap_elements, elements):
    if forbidden_overlap_elements:
        return ("/{}: {} {} not permitted to overlap other elements, order {} \n"
                .format(f, " and ".join(forbidden_overlap_elements),
                        "is" if len(forbidden_overlap_elements) == 1 else "are",
                        " above ".join(reversed(elements))))
    else:
        return ""
