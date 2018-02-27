#!/usr/bin/env python3
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
Element
=======
"""

import os
import re
import stat
import copy
from collections import Mapping, OrderedDict
from contextlib import contextmanager
from enum import Enum
import tempfile
import shutil

from . import _yaml
from ._variables import Variables
from ._exceptions import BstError, LoadError, LoadErrorReason, ImplError, ErrorDomain
from . import Plugin, Consistency
from . import SandboxFlags
from . import utils
from . import _cachekey
from . import _signals
from . import _site
from ._platform import Platform


# The base BuildStream artifact version
#
# The artifact version changes whenever the cache key
# calculation algorithm changes in an incompatible way
# or if buildstream was changed in a way which can cause
# the same cache key to produce something that is no longer
# the same.
_BST_CORE_ARTIFACT_VERSION = 1


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
    """
    def __init__(self, message, *, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.ELEMENT, reason=reason)


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = {}          # The defaults from the yaml file and project
    __defaults_set = False   # Flag, in case there are no defaults at all

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

    def __init__(self, context, project, artifacts, meta, plugin_conf):

        super().__init__(meta.name, context, project, meta.provenance, "element")

        self.normal_name = os.path.splitext(self.name.replace(os.sep, '-'))[0]
        """A normalized element name

        This is the original element without path separators or
        the extension, it's used mainly for composing log file names
        and creating directory names and such.
        """

        self.__runtime_dependencies = []        # Direct runtime dependency Elements
        self.__build_dependencies = []          # Direct build dependency Elements
        self.__sources = []                     # List of Sources
        self.__cache_key_dict = None            # Dict for cache key calculation
        self.__cache_key = None                 # Our cached cache key
        self.__weak_cache_key = None            # Our cached weak cache key
        self.__strict_cache_key = None          # Our cached cache key for strict builds
        self.__artifacts = artifacts            # Artifact cache
        self.__cached = None                    # Whether we have a cached artifact
        self.__strong_cached = None             # Whether we have a cached artifact
        self.__remotely_cached = None           # Whether we have a remotely cached artifact
        self.__remotely_strong_cached = None    # Whether we have a remotely cached artifact
        self.__assemble_scheduled = False       # Element is scheduled to be assembled
        self.__assemble_done = False            # Element is assembled
        self.__pull_failed = False              # Whether pull was attempted but failed
        self.__log_path = None                  # Path to dedicated log file or None
        self.__splits = None
        self.__whitelist_regex = None

        # Ensure we have loaded this class's defaults
        self.__init_defaults(plugin_conf)

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(meta)
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
        self.configure(self.__config)

        self.__tainted = None
        self.__workspaced_artifact = None
        self.__workspaced_dependencies_artifact = None

    def __lt__(self, other):
        return self.name < other.name

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

    def node_subst_member(self, node, member_name, default=None):
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
        return self.__variables.subst(value)

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
        return [self.__variables.subst(x) for x in value]

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
        return self.__variables.subst(value)

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
        self._assert_cached()
        return self.__compute_splits(include, exclude, orphans)

    def stage_artifact(self, sandbox, *, path=None, include=None, exclude=None, orphans=True):
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

        # Time to use the artifact, check once more that it's there
        self._assert_cached()

        with self.timed_activity("Staging {}/{}".format(self.name, self._get_display_key())):
            # Get the extracted artifact
            artifact = os.path.join(self.__extract(), 'files')

            # Hard link it into the staging area
            #
            basedir = sandbox.get_directory()
            stagedir = basedir \
                if path is None \
                else os.path.join(basedir, path.lstrip(os.sep))

            files = self.__compute_splits(include, exclude, orphans)
            result = utils.link_files(artifact, stagedir, files=files,
                                      report_written=True)

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

        for dep in self.dependencies(scope):
            result = dep.stage_artifact(sandbox,
                                        path=path,
                                        include=include,
                                        exclude=exclude,
                                        orphans=orphans)
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
                        if element_project._fail_on_overlap:
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

        self._stage_sources_in_sandbox(sandbox, directory)

    def get_public_data(self, domain):
        """Fetch public data on this element

        Args:
           domain (str): A public domain name to fetch data for

        Returns:
           (dict): The public data dictionary for the given domain

        .. note::

           This can only be called in the build phase of an element and
           never before. This may be called in
           :func:`Element.configure_sandbox() <buildstream.element.Element.configure_sandbox>`,
           :func:`Element.stage() <buildstream.element.Element.stage>` and in
           :func:`Element.assemble() <buildstream.element.Element.assemble>`

        """
        if self.__dynamic_public is None:
            self._load_public_data()

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
            self._load_public_data()

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
    #                  Abstract Element Methods                 #
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

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

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

    # _add_source():
    #
    # Adds a source, for pipeline construction
    #
    def _add_source(self, source):
        self.__sources.append(source)

    # _add_dependency()
    #
    # Adds a dependency
    #
    def _add_dependency(self, dependency, scope):
        if scope != Scope.RUN:
            self.__build_dependencies.append(dependency)
        if scope != Scope.BUILD:
            self.__runtime_dependencies.append(dependency)

    # _consistency():
    #
    # Returns:
    #    (list): The minimum consistency of the elements sources
    #
    # If the element has no sources, this returns Consistency.CACHED
    def _consistency(self):

        # The source objects already cache the consistency state, it
        # should not be expensive to iterate over the sources to get at it
        consistency = Consistency.CACHED
        for source in self.__sources:
            source_consistency = source._get_consistency()
            consistency = min(consistency, source_consistency)
        return consistency

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
        for source in self.__sources:
            source._schedule_tracking()

        self._update_state()

    # _schedule_assemble():
    #
    # This is called in the main process before the element is assembled
    # in a subprocess.
    #
    def _schedule_assemble(self):
        assert(not self.__assemble_scheduled)
        self.__assemble_scheduled = True

        for source in self.__sources:
            source._schedule_assemble()

        self._update_state()

    # _assemble_done():
    #
    # This is called in the main process after the element has been assembled
    # in a subprocess.
    #
    def _assemble_done(self):
        assert(self.__assemble_scheduled)

        for source in self.__sources:
            source._assemble_done()

        self.__assemble_scheduled = False
        self.__assemble_done = True

        self._update_state()

    # _cached():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache
    #
    def _cached(self):
        return self.__cached

    # _assert_cached()
    #
    # Raises an error if the artifact is not cached.
    #
    def _assert_cached(self):
        if not self._cached():
            raise ElementError("{}: Missing artifact {}"
                               .format(self, self._get_display_key()))

    # _remotely_cached():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the remote artifact cache
    #
    def _remotely_cached(self):
        return self.__remotely_cached

    # _tainted():
    #
    # Whether this artifact should be pushed to an artifact cache.
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
    def _tainted(self, recalculate=False):
        if recalculate or self.__tainted is None:

            # Whether this artifact has a workspace
            workspaced = self._workspaced_artifact()

            # Whether this artifact's dependencies are tainted
            workspaced_dependencies = any(
                val for key, val in
                _yaml.node_items(self._workspaced_dependencies_artifact())
            )

            # Other conditions should be or-ed
            self.__tainted = workspaced or workspaced_dependencies

        return self.__tainted

    # _buildable():
    #
    # Returns:
    #    (bool): Whether this element can currently be built
    #
    def _buildable(self):
        if self._consistency() != Consistency.CACHED:
            return False

        for dependency in self.dependencies(Scope.BUILD):
            if not (dependency._cached()):
                return False

        return True

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
            operating_system, _, _, _, machine_arch = os.uname()

            self.__cache_key_dict = {
                'artifact-version': "{}.{}".format(_BST_CORE_ARTIFACT_VERSION,
                                                   self.BST_ARTIFACT_VERSION),
                'context': context._get_cache_key(),
                'project': project._get_cache_key(),
                'element': self.get_unique_key(),

                # The execution environment may later be delegated
                # to sandboxes which support virtualization
                #
                'execution-environment': {
                    'os': operating_system,
                    'arch': machine_arch
                },
                'environment': cache_env,
                'sources': [s._get_unique_key() for s in self.__sources],
                'public': self.__public,
                'cache': type(self.__artifacts).__name__
            }

        cache_key_dict = self.__cache_key_dict.copy()
        cache_key_dict['dependencies'] = dependencies

        return _cachekey.generate_key(cache_key_dict)

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

    # _get_full_display_key():
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
    def _get_full_display_key(self):
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

    # _get_display_key():
    #
    # Returns an abbreviated cache key for display purposes
    #
    # Returns:
    #    (str): An abbreviated hex digest cache key for this Element
    #
    # Question marks are returned if information for the cache key is missing.
    #
    def _get_display_key(self):
        _, display_key, _ = self._get_full_display_key()
        return display_key

    # _get_variables()
    #
    # Fetch the internal Variables
    #
    def _get_variables(self):
        return self.__variables

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
            new_ref = source._track()
            refs.append((source._get_unique_id(), new_ref))

        return refs

    # _assemble():
    #
    # Internal method for calling public abstract assemble() method.
    #
    def _assemble(self):

        # Assert call ordering
        assert(not self._cached())

        context = self._get_context()
        with self._output_file() as output_file:

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Cleanup the build directory on explicit SIGTERM
            def cleanup_rootdir():
                utils._force_rmtree(rootdir)

            with _signals.terminator(cleanup_rootdir), \
                self.__sandbox(rootdir, output_file, output_file) as sandbox:  # nopep8

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
                    # Step 3 - Assemble
                    collect = self.assemble(sandbox)
                except BstError as e:
                    # If an error occurred assembling an element in a sandbox,
                    # then tack on the sandbox directory to the error
                    e.sandbox = rootdir
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
                if self.__log_path:
                    shutil.copyfile(self.__log_path, os.path.join(logsdir, 'build.log'))

                # Store public data
                _yaml.dump(_yaml.node_sanitize(self.__dynamic_public), os.path.join(metadir, 'public.yaml'))

                # ensure we have cache keys
                self._assemble_done()

                # Store artifact metadata
                dependencies = {
                    e.name: e._get_cache_key() for e in self.dependencies(Scope.BUILD)
                }
                workspaced_dependencies = {
                    e.name: e._workspaced() for e in self.dependencies(Scope.BUILD)
                }
                meta = {
                    'keys': {
                        'strong': self._get_cache_key(),
                        'weak': self._get_cache_key(_KeyStrength.WEAK),
                        'dependencies': dependencies
                    },
                    'workspaced': self._workspaced(),
                    'workspaced_dependencies': workspaced_dependencies
                }
                _yaml.dump(_yaml.node_sanitize(meta), os.path.join(metadir, 'artifact.yaml'))

                with self.timed_activity("Caching Artifact"):
                    self.__artifacts.commit(self, assembledir, self.__get_cache_keys_for_commit())

            # Finally cleanup the build dir
            cleanup_rootdir()

    # _pull():
    #
    # Pull artifact from remote artifact repository into local artifact cache.
    #
    # Returns: True if the artifact has been downloaded, False otherwise
    #
    def _pull(self):

        def progress(percent, message):
            self.status(message)

        weak_key = self._get_cache_key(strength=_KeyStrength.WEAK)

        if self.__remotely_strong_cached:
            key = self.__strict_cache_key
            self.__artifacts.pull(self, key, progress=progress)

            # update weak ref by pointing it to this newly fetched artifact
            self.__artifacts.link_key(self, key, weak_key)
        elif not self._get_strict() and self.__remotely_cached:
            self.__artifacts.pull(self, weak_key, progress=progress)

            # extract strong cache key from this newly fetched artifact
            self._update_state()

            # create tag for strong cache key
            key = self._get_cache_key(strength=_KeyStrength.STRONG)
            self.__artifacts.link_key(self, weak_key, key)
        else:
            raise ElementError("Attempt to pull unavailable artifact for element {}"
                               .format(self.name))

        # Notify successfull download
        display_key = self._get_display_key()
        self.info("Downloaded artifact {}".format(display_key))
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
        if self._tainted():
            return True

        # Use the strong cache key to check whether a remote already has the artifact.
        # In non-strict mode we want to push updated artifacts even if the
        # remote already has an artifact with the same weak cache key.
        key = self._get_cache_key(strength=_KeyStrength.STRONG)

        # Skip if every push remote contains this element already.
        if self.__artifacts.push_needed(self, key):
            return False
        else:
            return True

    # _push():
    #
    # Push locally cached artifact to remote artifact repository.
    #
    # Returns:
    #   (bool): True if the remote was updated, False if it already existed
    #           and no updated was required
    #
    def _push(self):
        self._assert_cached()

        if self._tainted():
            self.warn("Not pushing tainted artifact.")
            return False

        with self.timed_activity("Pushing Artifact"):
            # Push all keys used for local commit
            return self.__artifacts.push(self, self.__get_cache_keys_for_commit())

    # _logfile()
    #
    # Compose the log file for this action & pid.
    #
    # Args:
    #    action_name (str): The action name
    #    pid (int): Optional pid, current pid is assumed if not provided.
    #
    # Returns:
    #    (string): The log file full path
    #
    # Log file format, when there is a cache key, is:
    #
    #    '{logdir}/{project}/{element}/{cachekey}-{action}.{pid}.log'
    #
    # Otherwise, it is:
    #
    #    '{logdir}/{project}/{element}/{:0<64}-{action}.{pid}.log'
    #
    # This matches the order in which things are stored in the artifact cache
    #
    def _logfile(self, action_name, pid=None):
        project = self._get_project()
        context = self._get_context()
        key = self._get_display_key()
        if pid is None:
            pid = os.getpid()

        action = action_name.lower()
        logfile = "{key}-{action}.{pid}.log".format(
            key=key, action=action, pid=pid)

        directory = os.path.join(context.logdir, project.name, self.normal_name)

        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, logfile)

    # Set a source's workspace
    #
    def _set_source_workspaces(self, path):
        for source in self.sources():
            source._set_workspace(path)

    # Whether this element has a source that is workspaced.
    #
    def _workspaced(self):
        return any(source._has_workspace() for source in self.sources())

    # Get all source workspace directories.
    #
    def _workspace_dirs(self):
        for source in self.sources():
            if source._has_workspace():
                yield source._get_workspace()

    # _workspaced_artifact():
    #
    # Returns whether the current artifact is workspaced.
    #
    # Returns:
    #    (bool): Whether the current artifact is workspaced.
    #
    def _workspaced_artifact(self):

        if self.__workspaced_artifact is None:
            self._assert_cached()

            metadir = os.path.join(self.__extract(), 'meta')
            meta = _yaml.load(os.path.join(metadir, 'artifact.yaml'))
            if 'workspaced' in meta:
                self.__workspaced_artifact = meta['workspaced']
            else:
                self.__workspaced_artifact = False

        return self.__workspaced_artifact

    def _workspaced_dependencies_artifact(self):

        if self.__workspaced_dependencies_artifact is None:
            self._assert_cached()

            metadir = os.path.join(self.__extract(), 'meta')
            meta = _yaml.load(os.path.join(metadir, 'artifact.yaml'))
            if 'workspaced_dependencies' in meta:
                self.__workspaced_dependencies_artifact = meta['workspaced_dependencies']
            else:
                self.__workspaced_dependencies_artifact = {}

        return self.__workspaced_dependencies_artifact

    # Run some element methods with logging directed to
    # a dedicated log file, here we yield the filename
    # we decided on for logging
    #
    @contextmanager
    def _logging_enabled(self, action_name):
        self.__log_path = self._logfile(action_name)
        with open(self.__log_path, 'a') as logfile:

            # Write one last line to the log and flush it to disk
            def flush_log():

                # If the process currently had something happening in the I/O stack
                # then trying to reenter the I/O stack will fire a runtime error.
                #
                # So just try to flush as well as we can at SIGTERM time
                try:
                    logfile.write('\n\nAction {} for element {} forcefully terminated\n'
                                  .format(action_name, self.name))
                    logfile.flush()
                except RuntimeError:
                    os.fsync(logfile.fileno())

            self._set_log_handle(logfile)
            with _signals.terminator(flush_log):
                yield self.__log_path
            self._set_log_handle(None)
            self.__log_path = None

    # Override plugin _set_log_handle(), set it for our sources and dependencies too
    #
    # A log handle is set once in the context of a child task which will have only
    # one log, so it's not harmful to modify the state of dependencies
    def _set_log_handle(self, logfile, recurse=True):
        super()._set_log_handle(logfile)
        for source in self.sources():
            source._set_log_handle(logfile)
        if recurse:
            for dep in self.dependencies(Scope.ALL):
                dep._set_log_handle(logfile, False)

    # _prepare_sandbox():
    #
    # This stages things for either _shell() (below) or also
    # is used to stage things by the `bst checkout` codepath
    #
    @contextmanager
    def _prepare_sandbox(self, scope, directory, integrate=True):

        with self.__sandbox(directory) as sandbox:

            # Configure always comes first, and we need it.
            self.configure_sandbox(sandbox)

            # Stage something if we need it
            if not directory:
                if scope == Scope.BUILD:
                    self.stage(sandbox)
                elif scope == Scope.RUN:
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

    # _shell():
    #
    # Connects the terminal with a shell running in a staged
    # environment
    #
    # Args:
    #    scope (Scope): Either BUILD or RUN scopes are valid, or None
    #    directory (str): A directory to an existing sandbox, or None
    #    isolate (bool): Whether to isolate the environment like we do in builds
    #    prompt (str): A suitable prompt string for PS1
    #    command (list): An argv to launch in the sandbox
    #
    # Returns: Exit code
    #
    # If directory is not specified, one will be staged using scope
    def _shell(self, scope=None, directory=None, isolate=False, prompt=None, command=None):

        with self._prepare_sandbox(scope, directory) as sandbox:
            environment = self.get_environment()
            environment = copy.copy(environment)
            flags = SandboxFlags.INTERACTIVE | SandboxFlags.ROOT_READ_ONLY

            # Fetch the main toplevel project, in case this is a junctioned
            # subproject, we want to use the rules defined by the main one.
            context = self._get_context()
            project = context._get_toplevel_project()

            if prompt is not None:
                environment['PS1'] = prompt

            # Special configurations for non-isolated sandboxes
            if not isolate:

                # Open the network, and reuse calling uid/gid
                #
                flags |= SandboxFlags.NETWORK_ENABLED | SandboxFlags.INHERIT_UID

                # Use the project defined list of env vars to inherit
                for inherit in project._shell_env_inherit:
                    if os.environ.get(inherit) is not None:
                        environment[inherit] = os.environ.get(inherit)

                # Setup any project defined bind mounts
                for target, source in _yaml.node_items(project._shell_host_files):
                    if not os.path.exists(source):
                        self.warn("Not mounting non-existing host file: {}".format(source))
                    elif os.path.isdir(source):
                        self.warn("Not mounting directory listed as host file: {}".format(source))
                    else:
                        sandbox.mark_directory(target)
                        sandbox._set_mount_source(target, source)

            if command:
                argv = [arg for arg in command]
            else:
                argv = project._shell_command

            self.status("Running command", detail=" ".join(argv))

            # Run shells with network enabled and readonly root.
            return sandbox.run(argv, flags, env=environment)

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

        if mount_workspaces:
            # First, mount sources that have an open workspace
            sources_to_mount = [source for source in self.sources() if source._has_workspace()]
            for source in sources_to_mount:
                mount_point = source._get_staging_path(directory)
                mount_source = source._get_workspace_path()
                sandbox.mark_directory(mount_point)
                sandbox._set_mount_source(mount_point, mount_source)

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

            # If mount_workspaces is set, sources with workspace are mounted
            # directly inside the sandbox so no need to stage them here.
            if mount_workspaces:
                sources = [source for source in self.sources() if not source._has_workspace()]
            else:
                sources = self.sources()

            for source in sources:
                source._stage(directory)

        # Ensure deterministic mtime of sources at build time
        utils._set_deterministic_mtime(directory)
        # Ensure deterministic owners of sources at build time
        utils._set_deterministic_user(directory)

    # _get_strict()
    #
    # Convenience method to check strict build plan, since
    # the element carries it's project reference
    #
    # Returns:
    #   (bool): Whether the build plan is strict for this element
    #
    def _get_strict(self):
        project = self._get_project()
        context = self._get_context()
        return context._get_strict(project.name)

    # _pull_pending()
    #
    # Check whether the artifact will be pulled.
    #
    # Returns:
    #   (bool): Whether a pull operation is pending
    #
    def _pull_pending(self):
        if self.__pull_failed:
            # Consider this equivalent to artifact being unavailable in
            # remote cache
            return False

        if not self.__strong_cached and self.__remotely_strong_cached:
            # Pull pending using strict cache key
            return True
        elif not self.__cached and self.__remotely_cached:
            # Pull pending using weak cache key
            return True
        else:
            # No pull pending
            return False

    # _pull_failed()
    #
    # Indicate that pull was attempted but failed.
    #
    def _pull_failed(self):
        self.__pull_failed = True

    # _update_state()
    #
    # Keep track of element state. Calculate cache keys if possible and
    # check whether artifacts are cached.
    #
    # This must be called whenever the state of an element may have changed.
    #
    def _update_state(self):
        # Determine consistency of sources
        for source in self.__sources:
            source._update_state()

        if self._consistency() == Consistency.INCONSISTENT:
            # Tracking is still pending
            return

        if any([not source._stable() for source in self.__sources]):
            # If any source is not stable, discard current cache key values
            # as their correct values can only be calculated once the build is complete
            self.__cache_key_dict = None
            self.__cache_key = None
            self.__weak_cache_key = None
            self.__strict_cache_key = None
            self.__strong_cached = None
            self.__remotely_cached = None
            self.__remotely_strong_cached = None
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

        if not self._get_strict():
            # Full cache query in non-strict mode requires both the weak and
            # strict cache keys. However, we need to determine as early as
            # possible whether a build is pending to discard unstable cache keys
            # for workspaced elements. For this cache check the weak cache keys
            # are sufficient. However, don't update the `cached` attributes
            # until the full cache query below.
            cached = self.__artifacts.contains(self, self.__weak_cache_key)
            remotely_cached = self.__artifacts.remote_contains(self, self.__weak_cache_key)
            if (not self.__assemble_scheduled and not self.__assemble_done and
                not cached and not remotely_cached):
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
        key_for_cache_lookup = self.__strict_cache_key if self._get_strict() else self.__weak_cache_key
        if not self.__cached:
            self.__cached = self.__artifacts.contains(self, key_for_cache_lookup)
        if not self.__remotely_cached:
            self.__remotely_cached = self.__artifacts.remote_contains(self, key_for_cache_lookup)
        if not self.__strong_cached:
            self.__strong_cached = self.__artifacts.contains(self, self.__strict_cache_key)
        if not self.__remotely_strong_cached:
            self.__remotely_strong_cached = self.__artifacts.remote_contains(self, self.__strict_cache_key)

        if (not self.__assemble_scheduled and not self.__assemble_done and
            not self.__cached and not self.__remotely_cached):
            # Workspaced sources are considered unstable if a build is pending
            # as the build will modify the contents of the workspace.
            # Determine as early as possible if a build is pending to discard
            # unstable cache keys.
            self._schedule_assemble()
            return

        if self.__cache_key is None:
            # Calculate strong cache key
            if self._get_strict():
                self.__cache_key = self.__strict_cache_key
            elif self._pull_pending():
                # Effective strong cache key is unknown until after the pull
                pass
            elif self._cached():
                # Load the strong cache key from the artifact
                metadir = os.path.join(self.__extract(), 'meta')
                meta = _yaml.load(os.path.join(metadir, 'artifact.yaml'))
                self.__cache_key = meta['keys']['strong']
            elif self._buildable():
                # Artifact will be built, not downloaded
                dependencies = [
                    e._get_cache_key() for e in self.dependencies(Scope.BUILD)
                ]
                self.__cache_key = self.__calculate_cache_key(dependencies)

            if self.__cache_key is None:
                # Strong cache key could not be calculated yet
                return

    #############################################################
    #                   Private Local Methods                   #
    #############################################################
    @contextmanager
    def __sandbox(self, directory, stdout=None, stderr=None):
        context = self._get_context()
        project = self._get_project()
        platform = Platform.get_platform()

        if directory is not None and os.path.exists(directory):
            sandbox = platform.create_sandbox(context, project,
                                              directory,
                                              stdout=stdout,
                                              stderr=stderr)
            yield sandbox

        else:
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Recursive contextmanager...
            with self.__sandbox(rootdir, stdout=stdout, stderr=stderr) as sandbox:
                yield sandbox

            # Cleanup the build dir
            utils._force_rmtree(rootdir)

    def __compose_default_splits(self, defaults):
        project = self._get_project()
        project_splits = _yaml.node_chain_copy(project._splits)

        element_public = _yaml.node_get(defaults, Mapping, 'public', default_value={})
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        # Extend project wide split rules with any split rules defined by the element
        _yaml.composite(project_splits, element_splits)

        element_bst['split-rules'] = project_splits
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
            elements = project._elements
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
        project = self._get_project()
        default_env = _yaml.node_get(self.__defaults, Mapping, 'environment', default_value={})

        environment = _yaml.node_chain_copy(project._environment)
        _yaml.composite(environment, default_env)
        _yaml.composite(environment, meta.environment)
        _yaml.node_final_assertions(environment)

        # Resolve variables in environment value strings
        final_env = {}
        for key, value in self.node_items(environment):
            final_env[key] = self.node_subst_member(environment, key)

        return final_env

    def __extract_env_nocache(self, meta):
        project = self._get_project()
        project_nocache = project._env_nocache
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
        project = self._get_project()
        default_vars = _yaml.node_get(self.__defaults, Mapping, 'variables', default_value={})

        variables = _yaml.node_chain_copy(project._variables)
        _yaml.composite(variables, default_vars)
        _yaml.composite(variables, meta.variables)
        _yaml.node_final_assertions(variables)

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

    def __init_splits(self):
        bstdata = self.get_public_data('bst')
        splits = bstdata.get('split-rules')
        self.__splits = {
            domain: re.compile('^(?:' + '|'.join([utils._glob2re(r) for r in rules]) + ')$')
            for domain, rules in self.node_items(splits)
        }

    def __compute_splits(self, include=None, exclude=None, orphans=True):
        basedir = os.path.join(self.__extract(), 'files')

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

    def __extract(self):
        key = self.__strict_cache_key

        # Use weak cache key, if artifact is missing for strong cache key
        # and the context allows use of weak cache keys
        if not self._get_strict() and not self.__artifacts.contains(self, key):
            key = self._get_cache_key(strength=_KeyStrength.WEAK)

        return self.__artifacts.extract(self, key)

    def __get_cache_keys_for_commit(self):
        keys = []

        # tag with strong cache key based on dependency versions used for the build
        keys.append(self._get_cache_key(strength=_KeyStrength.STRONG))

        # also store under weak cache key
        keys.append(self._get_cache_key(strength=_KeyStrength.WEAK))

        return utils._deduplicate(keys)

    def _load_public_data(self):
        self._assert_cached()
        assert(self.__dynamic_public is None)

        # Load the public data from the artifact
        metadir = os.path.join(self.__extract(), 'meta')
        self.__dynamic_public = _yaml.load(os.path.join(metadir, 'public.yaml'))

    def _subst_string(self, value):
        return self.__variables.subst(value)


def _overlap_error_detail(f, forbidden_overlap_elements, elements):
    if forbidden_overlap_elements:
        return ("/{}: {} {} not permitted to overlap other elements, order {} \n"
                .format(f, " and ".join(forbidden_overlap_elements),
                        "is" if len(forbidden_overlap_elements) == 1 else "are",
                        " above ".join(reversed(elements))))
    else:
        return ""
