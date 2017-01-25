#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

import os
import sys
import copy
import inspect
from contextlib import contextmanager
from enum import Enum
import tempfile
import shutil

from . import _yaml
from ._variables import Variables
from . import LoadError, LoadErrorReason, ElementError
from . import Sandbox
from . import Plugin, Consistency
from . import utils


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


class Element(Plugin):
    """Element()

    Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """
    __defaults = {}          # The defaults from the yaml file and project
    __defaults_set = False   # Flag, in case there are no defaults at all

    def __init__(self, display_name, context, project, artifacts, meta):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__(display_name, context, project, provenance, "element")

        self.name = meta.name
        """The element name"""

        self.__runtime_dependencies = []  # Direct runtime dependency Elements
        self.__build_dependencies = []    # Direct build dependency Elements
        self.__sources = []               # List of Sources
        self.__cache_key = None           # Our cached cache key
        self.__artifacts = artifacts      # Artifact cache
        self.__cached = False             # Whether we have a cached artifact

        # Ensure we have loaded this class's defaults
        self.__init_defaults()

        # Collect the composited environment
        env = self.__extract_environment(meta)
        self.__environment = env

        # Collect the composited variables and resolve them
        variables = self.__extract_variables(meta)
        self.__variables = Variables(variables)

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__config = self.__extract_config(meta)
        self.configure(self.__config)

    def __lt__(self, other):
        return self.name < other.name

    def dependencies(self, scope, visiting=None):
        """dependencies(scope)

        A generator function which lists the dependencies of the given element
        deterministically, starting with the basemost elements in the given scope.

        Args:
           scope (:class:`.Scope`): The scope to iterate in

        Returns:
           (list): The dependencies in *scope*, in deterministic staging order
        """

        # A little reentrancy protection, this loop could be
        # optimized but not bothering at this point.
        #
        if visiting is None:
            visiting = []
        if self.name in visiting:
            return
        visiting.append(self.name)

        if scope == Scope.ALL:
            for dep in self.__build_dependencies:
                for elt in dep.dependencies(Scope.ALL, visiting=visiting):
                    yield elt
            for dep in self.__runtime_dependencies:
                if dep not in self.__build_dependencies:
                    for elt in dep.dependencies(Scope.ALL, visiting=visiting):
                        yield elt

        elif scope == Scope.BUILD:
            for dep in self.__build_dependencies:
                for elt in dep.dependencies(Scope.RUN, visiting=visiting):
                    yield elt

        elif scope == Scope.RUN:
            for dep in self.__runtime_dependencies:
                for elt in dep.dependencies(Scope.RUN, visiting=visiting):
                    yield elt

        # Yeild self only at the end, after anything needed has been traversed
        if (scope == Scope.ALL or scope == Scope.RUN):
            yield self

    def node_subst_member(self, node, member_name, default_value=None):
        """Fetch the value of a string node member, substituting any variables
        in the loaded value with the element contextual variables.

        Args:
           node (dict): A dictionary loaded from YAML
           member_name (str): The name of the member to fetch
           default_value (str): A value to return when *member_name* is not specified in *node*

        Returns:
           The value of *member_name* in *node*, otherwise *default_value*

        Raises:
           :class:`.LoadError`: When *member_name* is not found and no *default_value* was provided

        This is essentially the same as :func:`~buildstream.plugin.Plugin.node_get_member`
        except that it assumes the expected type is a string and will also perform variable
        substitutions.

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node', substituting any
          # variables in the returned string
          name = self.node_subst_member(node, 'name')
        """
        value = self.node_get_member(node, str, member_name, default_value=default_value)
        return self.__variables.subst(value)

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

    def stage(self, sandbox, path=None):
        """Stage this element's output in the sandbox

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           path (str): An optional sandbox relative path

        Raises:
           (:class:`.ElementError`): If the element output does not exist

        **Example:**

        .. code:: python

          # Stage the dependencies for a build of 'self'
          for dep in self.dependencies(Scope.BUILD):
              dep.stage(sandbox)
        """
        project = self.get_project()
        key = self._get_cache_key()

        # Time to use the artifact, check once more that it's there
        self._assert_cached()

        with self.timed_activity("Staging {}/{}/{}".format(project.name, self.name, key)):
            # Get the extracted artifact
            artifact = self.__artifacts.extract(project.name, self.name, key)

            # Hard link it into the staging area
            #
            # XXX For now assuming that it's a read-only location
            basedir = sandbox.executor.fs_root
            stagedir = basedir \
                if path is None \
                else os.path.join(basedir, path.lstrip(os.sep))
            utils.link_files(artifact, stagedir)

    def stage_sources(self, sandbox, path=None):
        """Stage this element's source input

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           path (str): An optional sandbox relative path

        **Example:**

        .. code:: python

          # Stage the sources of 'self' to the /build directory
          # in the sandbox
          self.stage_sources(sandbox, '/build')
        """
        basedir = sandbox.executor.fs_root
        stagedir = basedir \
            if path is None \
            else os.path.join(basedir, path.lstrip(os.sep))
        for source in self.__sources:
            source._stage(stagedir)

    #############################################################
    #                  Abstract Element Methods                 #
    #############################################################
    def assemble(self, sandbox):
        """Assemble the output artifact

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox

        Returns:
           (str): A sandbox relative path to collect

        Raises:
           (:class:`.ElementError`): When the element raises an error

        Elements must implement this method to create an output
        artifact from it's sources and dependencies.
        """
        raise ImplError("element plugin '{kind}' does not implement assemble()".format(
            kind=self.get_kind()))

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _add_source():
    #
    # Adds a source, for pipeline construction
    #
    def _add_source(self, source):
        self.__sources.append(source)

    # _sources():
    #
    # Generator function for the element sources
    #
    def _sources(self):
        for source in self.__sources:
            yield source

    # _add_dependency()
    #
    # Adds a dependency
    #
    def _add_dependency(self, dependency, scope):
        if scope != Scope.RUN:
            self.__build_dependencies.append(dependency)
        if scope != Scope.BUILD:
            self.__runtime_dependencies.append(dependency)

    # _direct_deps():
    #
    # Generator function for the element's direct dependencies
    #
    # Note this is not recursive like the public element.dependencies().
    #
    def _direct_deps(self, scope):
        if scope == Scope.RUN:
            for element in self.__runtime_dependencies:
                yield element
        elif scope != Scope.BUILD:
            for element in self.__build_dependencies:
                yield element
        else:
            for element in self.__runtime_dependencies:
                yield element
            for element in self.__build_dependencies:
                if element not in self.__runtime_dependencies:
                    yield element

    # _consistency():
    #
    # Returns:
    #    (list): The minimum consistency of the elements sources
    #
    # If the element has no sources, this returns Consistency.CACHED
    def _consistency(self):
        consistency = Consistency.CACHED
        for source in self.__sources:
            source_consistency = source._get_consistency()
            consistency = min(consistency, source_consistency)
        return consistency

    # _cached():
    #
    # Args:
    #    recalcualte (bool): Whether to forcefully recalculate
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache
    #
    def _cached(self, recalculate=False):
        project = self.get_project()
        key = self._get_cache_key()
        if (self.__cached is None or recalculate) and project is not None and key is not None:
            self.__cached = self.__artifacts.contains(project.name, self.name, key)

        return False if self.__cached is None else self.__cached

    # _assert_cached()
    #
    # Raises an error if the artifact is not cached.
    def _assert_cached(self):
        if not self._cached():
            project = self.get_project()
            key = self._get_cache_key()
            if not key:
                key = '0' * 64

            raise ElementError("{element}: Missing artifact {project}/{name}/{key}"
                               .format(element=self,
                                       project=project.name,
                                       name=self.name,
                                       key=key))

    # _set_cached():
    #
    # Forcefully set the cached state on the element.
    #
    # This is done by the Pipeline when an element successfully
    # completes a build.
    #
    def _set_cached(self):
        self.__cached = True

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

    # _get_cache_key():
    #
    # Returns the cache key, calculating it if necessary
    #
    # Returns:
    #    (str): A hex digest cache key for this Element, or None
    #
    # None is returned if information for the cache key is missing.
    #
    def _get_cache_key(self):

        if self._consistency() == Consistency.INCONSISTENT:
            return None

        if self.__cache_key is None:

            # No cache keys for dependencies which have no cache keys
            dependencies = [e._get_cache_key() for e in self.dependencies(Scope.BUILD)]
            for dep in dependencies:
                if dep is None:
                    return None

            context = self.get_context()
            self.__cache_key = utils._generate_key({
                'context': context._get_cache_key(),
                'element': self.get_unique_key(),
                'sources': [s.get_unique_key() for s in self.__sources],
                'dependencies': dependencies,
            })

        return self.__cache_key

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
        changed = []
        for source in self.__sources:
            new_ref = source._track()
            if new_ref is not None:
                changed.append((source._get_unique_id(), new_ref))

        return changed

    # _assemble():
    #
    # Internal method for calling public abstract assemble() method.
    #
    def _assemble(self):

        # Assert call ordering
        assert(not self._cached())

        context = self.get_context()
        with self._output_file() as output_file:

            # Explicitly clean it up, keep the build dir around if exceptions are raised
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.name), dir=context.builddir)

            with self.__sandbox(None, rootdir, output_file, output_file) as sandbox:

                # Call the abstract plugin method
                collect = self.assemble(sandbox)

                # Note important use of lstrip() here
                collectdir = os.path.join(rootdir, collect.lstrip(os.sep))

                # At this point, we expect an exception was raised leading to
                # an error message, or we have good output to collect.
                project = self.get_project()
                key = self._get_cache_key()
                self.__artifacts.commit(project.name,
                                        self.name,
                                        key,
                                        collectdir)

            # Finally cleanup the build dir
            shutil.rmtree(rootdir)

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
        project = self.get_project()
        context = self.get_context()
        key = self._get_cache_key()
        if pid is None:
            pid = os.getpid()

        # Just put 64 zeros if there is no key yet, this
        # happens when fetching sources only, never when building
        if not key:
            key = "{:0<64}".format('')

        action = action_name.lower()
        logfile = "{key}-{action}.{pid}.log".format(
            key=key, action=action, pid=pid)

        directory = os.path.join(context.logdir, project.name, self.name)

        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, logfile)

    # Run some element methods with logging directed to
    # a dedicated log file, here we yield the filename
    # we decided on for logging
    #
    @contextmanager
    def _logging_enabled(self, action_name):
        fullpath = self._logfile(action_name)
        with open(fullpath, 'a') as logfile:
            self._set_log_handle(logfile)
            yield fullpath
            self._set_log_handle(None)

    # Override plugin _set_log_handle(), set it for our sources too
    #
    def _set_log_handle(self, logfile):
        super()._set_log_handle(logfile)
        for source in self._sources():
            source._set_log_handle(logfile)

    # _shell():
    #
    # Connects the terminal with a shell running in a staged
    # environment
    #
    # Args:
    #    scope (Scope): Either BUILD or RUN scopes are valid, or None
    #    directory (str): A directory to an existing sandbox, or None
    #
    # If directory is not specified, one will be staged using scope
    def _shell(self, scope=None, directory=None):
        with self.__sandbox(scope, directory, sys.stdout, sys.stderr) as sandbox:
            self.__run_shell(sandbox)

    #############################################################
    #                   Private Local Methods                   #
    #############################################################
    @contextmanager
    def __sandbox(self, scope, directory, stdout, stderr):
        environment = utils._node_sanitize(self.__environment)
        if directory is not None and os.path.exists(directory):

            # sandbox.executor.debug = True
            sandbox = Sandbox(fs_root=directory,
                              env=environment,
                              stdout=stdout,
                              stderr=stderr)

            # root is temp directory
            sandbox.executor.root_ro = False
            os.makedirs(os.path.join(directory, 'tmp'), exist_ok=True)

            mounts = []
            mounts.append({'dest': '/dev', 'type': 'host-dev'})
            mounts.append({'dest': '/proc', 'type': 'proc'})
            sandbox.set_mounts(mounts)

            yield sandbox

        else:
            context = self.get_context()
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.name), dir=context.builddir)

            # Recursive contextmanager...
            with self.__sandbox(scope, rootdir, stdout, stderr) as sandbox:

                # Stage deps in the sandbox root
                for dep in self.dependencies(scope):
                    dep.stage(sandbox)

                if scope == Scope.BUILD:
                    # Stage sources in /buildstream/build
                    self.stage_sources(sandbox, '/buildstream/build')

                    # And set the sandbox work directory too
                    sandbox.set_cwd('/buildstream/build')

                yield sandbox

            # Cleanup the build dir
            shutil.rmtree(rootdir)

    def __run_shell(self, sandbox):

        # Totally open sandbox for running a shell
        sandbox.executor.network_enable = True
        sandbox.executor.namespace_pid = False
        sandbox.executor.namespace_ipc = False
        sandbox.executor.namespace_uts = False
        sandbox.executor.namespace_cgroup = False

        # Composite the element environment on top of the host
        # environment and use that for the shell environment.
        #
        # XXX Hard code should be removed
        overrides = ['DISPLAY', 'DBUS_SESSION_BUS_ADDRESS']
        for override in overrides:
            sandbox.executor.env[override] = os.environ.get(override)

        exitcode, _, _ = sandbox.run(['/bin/sh', '-i'])
        if exitcode != 0:
            raise ElementError("Running shell failed with exitcode {}".format(exitcode))

    def __init_defaults(self):

        # Defaults are loaded once per class and then reused
        #
        if not self.__defaults_set:

            # Get the yaml file in the same directory as the plugin
            plugin_file = inspect.getfile(type(self))
            plugin_dir = os.path.dirname(plugin_file)
            plugin_conf_name = "%s.yaml" % self.get_kind()
            plugin_conf = os.path.join(plugin_dir, "%s.yaml" % self.get_kind())

            # Override some plugin defaults with project overrides
            #
            defaults = {}
            project = self.get_project()
            elements = project._elements
            overrides = elements.get(self.get_kind())

            try:
                defaults = _yaml.load(plugin_conf, plugin_conf_name)
                if overrides:
                    _yaml.composite(defaults, overrides, typesafe=True)
            except LoadError as e:
                # Ignore missing file errors, element's may omit a config file.
                if e.reason == LoadErrorReason.MISSING_FILE:
                    if overrides:
                        defaults = copy.deepcopy(overrides)
                else:
                    raise e

            # Set the data class wide
            type(self).__defaults = defaults
            self.__defaults_set = True

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __extract_environment(self, meta):
        project = self.get_project()
        default_env = _yaml.node_get(self.__defaults, dict, 'environment', default_value={})
        element_env = meta.environment

        # Overlay default_env with element_env
        default_env = copy.deepcopy(default_env)
        _yaml.composite(default_env, element_env, typesafe=True)
        element_env = default_env

        # Overlay base_env with element_env
        base_env = copy.deepcopy(project._environment)
        _yaml.composite(base_env, element_env, typesafe=True)
        element_env = base_env

        return element_env

    # This will resolve the final variables to be used when
    # substituting command strings to be run in the sandbox
    #
    def __extract_variables(self, meta):
        project = self.get_project()
        default_vars = _yaml.node_get(self.__defaults, dict, 'variables', default_value={})
        element_vars = meta.variables

        # Overlay default_vars with element_vars
        default_vars = copy.deepcopy(default_vars)
        _yaml.composite(default_vars, element_vars, typesafe=True)
        element_vars = default_vars

        # Overlay base_vars with element_vars
        base_vars = copy.deepcopy(project._variables)
        _yaml.composite(base_vars, element_vars, typesafe=True)
        element_vars = base_vars

        return element_vars

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    def __extract_config(self, meta):

        # The default config is already composited with the project overrides
        default_config = _yaml.node_get(self.__defaults, dict, 'config', default_value={})
        element_config = meta.config

        default_config = copy.deepcopy(default_config)
        _yaml.composite(default_config, element_config, typesafe=True)
        element_config = default_config

        return element_config
