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
import re
import copy
import inspect
from collections import Mapping
from contextlib import contextmanager
from enum import Enum
import tempfile
import shutil

from . import _yaml
from ._yaml import CompositePolicy
from ._variables import Variables
from .exceptions import _BstError
from . import LoadError, LoadErrorReason, ElementError
from ._sandboxbwrap import SandboxBwrap
from . import Sandbox, SandboxFlags
from . import Plugin, Consistency
from . import utils
from . import _signals


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

    def __init__(self, context, project, artifacts, meta):

        super().__init__(meta.name, context, project, meta.provenance, "element")

        self.normal_name = os.path.splitext(self.name.replace(os.sep, '-'))[0]
        """A normalized element name

        This is the original element without path separators or
        the extension, it's used mainly for composing log file names
        and creating directory names and such.
        """

        self.__runtime_dependencies = []  # Direct runtime dependency Elements
        self.__build_dependencies = []    # Direct build dependency Elements
        self.__sources = []               # List of Sources
        self.__cache_key = None           # Our cached cache key
        self.__artifacts = artifacts      # Artifact cache
        self.__cached = None              # Whether we have a cached artifact

        # Ensure we have loaded this class's defaults
        self.__init_defaults()

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

        # Compile splitters
        self.__init_splits()

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__config = self.__extract_config(meta)
        self.configure(self.__config)

    def __lt__(self, other):
        return self.name < other.name

    def sources(self):
        """A generator function to enumerate the element sources

        Yields:
           (:class:`.Source`): The sources of this element
        """
        for source in self.__sources:
            yield source

    def dependencies(self, scope, recurse=True, visited=None):
        """dependencies(scope, recurse=True)

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
        did_recurse = False
        if visited is None:
            visited = []
        else:
            did_recurse = True

        if self.name in visited:
            return
        visited.append(self.name)

        if recurse or not did_recurse:
            if scope == Scope.ALL:
                for dep in self.__build_dependencies:
                    for elt in dep.dependencies(Scope.ALL, recurse=recurse, visited=visited):
                        yield elt
                for dep in self.__runtime_dependencies:
                    if dep not in self.__build_dependencies:
                        for elt in dep.dependencies(Scope.ALL, recurse=recurse, visited=visited):
                            yield elt
            elif scope == Scope.BUILD:
                for dep in self.__build_dependencies:
                    for elt in dep.dependencies(Scope.RUN, recurse=recurse, visited=visited):
                        yield elt
            elif scope == Scope.RUN:
                for dep in self.__runtime_dependencies:
                    for elt in dep.dependencies(Scope.RUN, recurse=recurse, visited=visited):
                        yield elt

        # Yeild self only at the end, after anything needed has been traversed
        if (recurse or did_recurse) and (scope == Scope.ALL or scope == Scope.RUN):
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

    def stage_artifact(self, sandbox, path=None, splits=None, orphans=True):
        """Stage this element's output artifact in the sandbox

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           path (str): An optional sandbox relative path
           splits (list): An optional list of domains to stage files from
           orphans (bool): Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): If the element has not yet produced an artifact.

        Returns:
           This returns two lists, the first list contains any files which
           were overwritten in `dest` and the second list contains any
           files which were not staged as they would replace a non empty
           directory in `dest`

        Note::

           Directories in `dest` are replaced with files from `src`,
           unless the existing directory in `dest` is not empty in which
           case the path will be reported in the return value.

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
            artifact = self.__artifacts.extract(self)

            # Hard link it into the staging area
            #
            basedir = sandbox.get_directory()
            stagedir = basedir \
                if path is None \
                else os.path.join(basedir, path.lstrip(os.sep))

            files = self.__compute_splits(splits, orphans)
            overwrites, ignored = utils.link_files(artifact, stagedir, files=files)

        return overwrites, ignored

    def stage_dependency_artifacts(self, sandbox, scope, path=None, splits=None, orphans=True):
        """Stage element dependencies in scope

        This is primarily a convenience wrapper around
        :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>`
        which takes care of staging all the dependencies in `scope` and issueing the
        appropriate warnings.

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           scope (:class:`.Scope`): The scope to stage dependencies in
           path (str): An optional sandbox relative path
           splits (list): An optional list of domains to stage files from
           orphans (bool): Whether to include files not spoken for by split domains

        Raises:
           (:class:`.ElementError`): If any of the dependencies in `scope` have not
                                     yet produced artifacts.
        """
        overwrites = {}
        ignored = {}

        for dep in self.dependencies(scope):
            o, i = dep.stage_artifact(sandbox, path=path, splits=splits, orphans=orphans)
            if o:
                overwrites[dep.name] = o
            if i:
                ignored[dep.name] = i

        if overwrites:
            detail = "Staged files overwrite existing files in staging area:\n"
            for key, value in overwrites.items():
                detail += "\nFrom {}:\n".format(key)
                detail += "  " + "  ".join(["/" + f + "\n" for f in value])
            self.warn("Overlapping files", detail=detail)

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
            commands = self.node_get_member(bstdata, list, 'integration-commands', default_value=[])
            for i in range(len(commands)):
                cmd = self.node_subst_list_element(bstdata, 'integration-commands', [i])
                self.status("Running integration command", detail=cmd)
                exitcode = sandbox.run(['sh', '-c', '-e', cmd], 0, env=environment, cwd='/')
                if exitcode != 0:
                    raise ElementError("Command '{}' failed with exitcode {}".format(cmd, exitcode))

    def stage_sources(self, sandbox, directory):
        """Stage this element's sources to a directory

        Args:
           sandbox (:class:`.Sandbox`): The build sandbox
           directory (str): An absolute path within the sandbox to stage the sources at
        """

        sandbox_root = sandbox.get_directory()
        host_directory = os.path.join(sandbox_root, directory.lstrip(os.sep))

        with self.timed_activity("Staging sources", silent_nested=True):
            for source in self.__sources:
                source._stage(host_directory)

        # Ensure deterministic mtime of sources at build time
        utils._set_deterministic_mtime(host_directory)

    def get_public_data(self, domain):
        """Fetch public data on this element

        Args:
           domain (str): A public domain name to fetch data for

        Returns:
           (dict): The public data dictionary for the given domain
        """
        return self.__public.get(domain)

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
    # Args:
    #    recalcualte (bool): Whether to forcefully recalculate
    #
    # Returns:
    #    (list): The minimum consistency of the elements sources
    #
    # If the element has no sources, this returns Consistency.CACHED
    def _consistency(self, recalculate=False):

        # The source objects already cache the consistency state, it
        # should not be expensive to iterate over the sources to get at it
        consistency = Consistency.CACHED
        for source in self.__sources:
            source_consistency = source._get_consistency(recalculate=recalculate)
            consistency = min(consistency, source_consistency)
        return consistency

    # _force_inconsistent():
    #
    # Force an element state to be inconsistent. Cache keys are unset, Artifacts appear
    # to be not cached and any sources appear to be inconsistent.
    #
    # This is used across the pipeline in sessions where the
    # elements in question are going to be tracked, causing the
    # pipeline to rebuild safely by ensuring cache key recalculation
    # and reinterrogation of element state after tracking of elements
    # succeeds.
    #
    def _force_inconsistent(self):
        self.__cached = None
        self.__cache_key = None
        for source in self.__sources:
            source._force_inconsistent()

    # _cached():
    #
    # Returns:
    #    (bool): Whether this element is already present in
    #            the artifact cache
    #
    def _cached(self):

        if self.__cached is None and self._get_cache_key() is not None:
            self.__cached = self.__artifacts.contains(self)

        return False if self.__cached is None else self.__cached

    # _assert_cached()
    #
    # Raises an error if the artifact is not cached.
    def _assert_cached(self):
        if not self._cached():
            raise ElementError("{}: Missing artifact {}"
                               .format(self, self._get_display_key()))

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

        # It is not really necessary to check if the Source object's
        # local mirror has the ref cached locally or not, it's only important
        # to know if the source has a ref specified or not, in order to
        # produce a cache key.
        #
        if self._consistency() == Consistency.INCONSISTENT:
            return None

        if self.__cache_key is None:

            # No cache keys for dependencies which have no cache keys
            dependencies = [e._get_cache_key() for e in self._direct_deps(Scope.BUILD)]
            for dep in dependencies:
                if dep is None:
                    return None

            # Filter out nocache variables from the element's environment
            cache_env = {
                key: value
                for key, value in self.node_items(self.__environment)
                if key not in self.__env_nocache
            }

            # Integration commands imposed on depending elements do not effect
            # a given element's cache key, the sum of an element's dependency
            # integration commands however does effect the cache key.
            integration = [
                {
                    'elt': e.name,
                    'commands': e.get_public_data('bst').get('integration-commands', [])
                }
                for e in self.dependencies(Scope.BUILD)
                if e.get_public_data('bst') is not None
            ]

            context = self.get_context()
            project = self.get_project()
            self.__cache_key = utils._generate_key({
                'context': context._get_cache_key(),
                'project': project._get_cache_key(),
                'element': self.get_unique_key(),
                'environment': cache_env,
                'sources': [s.get_unique_key() for s in self.__sources],
                'dependencies': dependencies,
                'integration': integration
            })

        return self.__cache_key

    # _get_display_key():
    #
    # Returns an abbreviated cache key for display purposes
    #
    # Returns:
    #    (str): An abbreviated hex digest cache key for this Element, or zeros
    #
    # Zeros are returned if information for the cache key is missing.
    #
    def _get_display_key(self):
        context = self.get_context()
        cache_key = self._get_cache_key()
        if cache_key:
            length = min(len(cache_key), context.log_key_length)
            return cache_key[0:length]

        return ("{:?<" + str(context.log_key_length) + "}").format('')

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
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Cleanup the build directory on explicit SIGTERM
            def cleanup_rootdir():
                shutil.rmtree(rootdir)

            with _signals.terminator(cleanup_rootdir), \
                self.__sandbox(rootdir, output_file, output_file) as sandbox:  # nopep8

                sandbox_root = sandbox.get_directory()

                # Call the abstract plugin methods
                try:
                    # Step 1 - Configure
                    self.configure_sandbox(sandbox)
                    # Step 2 - Stage
                    self.stage(sandbox)
                    # Step 3 - Assemble
                    collect = self.assemble(sandbox)
                except _BstError as e:
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
                with self.timed_activity("Caching Artifact"):
                    self.__artifacts.commit(self, collectdir)

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
        key = self._get_display_key()
        if pid is None:
            pid = os.getpid()

        action = action_name.lower()
        logfile = "{key}-{action}.{pid}.log".format(
            key=key, action=action, pid=pid)

        directory = os.path.join(context.logdir, project.name, self.normal_name)

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
                yield fullpath
            self._set_log_handle(None)

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
    def _prepare_sandbox(self, scope, directory):

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
    #
    # If directory is not specified, one will be staged using scope
    def _shell(self, scope=None, directory=None):

        with self._prepare_sandbox(scope, directory) as sandbox:

            # Override the element environment with some of
            # the host environment and use that for the shell environment.
            #
            # XXX Hard code should be removed
            environment = self.get_environment()
            environment = copy.copy(environment)
            overrides = ['DISPLAY', 'DBUS_SESSION_BUS_ADDRESS']
            for override in overrides:
                if os.environ.get(override) is not None:
                    environment[override] = os.environ.get(override)

            # Run shells with network enabled and readonly root.
            exitcode = sandbox.run(['sh', '-i'],
                                   SandboxFlags.NETWORK_ENABLED,
                                   env=environment)

    #############################################################
    #                   Private Local Methods                   #
    #############################################################
    @contextmanager
    def __sandbox(self, directory, stdout=None, stderr=None):
        context = self.get_context()
        project = self.get_project()

        if directory is not None and os.path.exists(directory):

            # We'll want a factory function and some decision making about
            # which sandbox implementation to use, when we have more than
            # one sandbox implementation.
            #
            sandbox = SandboxBwrap(context, project, directory, stdout=stdout, stderr=stderr)

            yield sandbox

        else:
            os.makedirs(context.builddir, exist_ok=True)
            rootdir = tempfile.mkdtemp(prefix="{}-".format(self.normal_name), dir=context.builddir)

            # Recursive contextmanager...
            with self.__sandbox(rootdir, stdout=stdout, stderr=stderr) as sandbox:
                yield sandbox

            # Cleanup the build dir
            shutil.rmtree(rootdir)

    def __compose_default_splits(self, defaults):
        project = self.get_project()
        project_splits = _yaml.node_chain_copy(project._splits)

        element_public = _yaml.node_get(defaults, Mapping, 'public', default_value={})
        element_bst = _yaml.node_get(element_public, Mapping, 'bst', default_value={})
        element_splits = _yaml.node_get(element_bst, Mapping, 'split-rules', default_value={})

        # Extend project wide split rules with any split rules defined by the element
        _yaml.composite(project_splits, element_splits,
                        policy=CompositePolicy.ARRAY_APPEND,
                        typesafe=True)

        element_bst['split-rules'] = project_splits
        element_public['bst'] = element_bst
        defaults['public'] = element_public

    def __init_defaults(self):

        # Defaults are loaded once per class and then reused
        #
        if not self.__defaults_set:

            # Get the yaml file in the same directory as the plugin
            plugin_file = inspect.getfile(type(self))
            plugin_dir = os.path.dirname(plugin_file)
            plugin_conf_name = "{}.yaml".format(self.get_kind())
            plugin_conf = os.path.join(plugin_dir, plugin_conf_name)

            # Load the plugin's accompanying .yaml file if one was provided
            defaults = {}
            try:
                defaults = _yaml.load(plugin_conf, plugin_conf_name)
            except LoadError as e:
                if e.reason != LoadErrorReason.MISSING_FILE:
                    raise e

            # Special case; compose any element-wide split-rules declarations
            self.__compose_default_splits(defaults)

            # Override the element's defaults with element specific
            # overrides from the project.conf
            project = self.get_project()
            elements = project._elements
            overrides = elements.get(self.get_kind())
            if overrides:
                _yaml.composite(defaults, overrides, typesafe=True)

            # Set the data class wide
            type(self).__defaults = defaults
            type(self).__defaults_set = True

    # This will resolve the final environment to be used when
    # creating sandboxes for this element
    #
    def __extract_environment(self, meta):
        project = self.get_project()
        default_env = _yaml.node_get(self.__defaults, Mapping, 'environment', default_value={})

        environment = _yaml.node_chain_copy(project._environment)
        _yaml.composite(environment, default_env, typesafe=True)
        _yaml.composite(environment, meta.environment, typesafe=True)

        # Resolve variables in environment value strings
        final_env = {}
        for key, value in self.node_items(environment):
            final_env[key] = self.node_subst_member(environment, key)

        return final_env

    def __extract_env_nocache(self, meta):
        project = self.get_project()
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
        project = self.get_project()
        default_vars = _yaml.node_get(self.__defaults, Mapping, 'variables', default_value={})

        variables = _yaml.node_chain_copy(project._variables)
        _yaml.composite(variables, default_vars, typesafe=True)
        _yaml.composite(variables, meta.variables, typesafe=True)

        return variables

    # This will resolve the final configuration to be handed
    # off to element.configure()
    #
    def __extract_config(self, meta):

        # The default config is already composited with the project overrides
        config = _yaml.node_get(self.__defaults, Mapping, 'config', default_value={})
        config = _yaml.node_chain_copy(config)

        _yaml.composite(config, meta.config, typesafe=True)

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
        _yaml.composite(base_splits, element_splits,
                        policy=CompositePolicy.ARRAY_APPEND,
                        typesafe=True)

        element_bst['split-rules'] = base_splits
        element_public['bst'] = element_bst

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
            domain: re.compile('^(?:' + '|'.join(rules) + ')$')
            for domain, rules in self.node_items(splits)
        }

    def __compute_splits(self, splits, orphans):
        basedir = self.__artifacts.extract(self)

        # No splitting requested, just report complete artifact
        if orphans and not splits:
            for filename in utils.list_relative_paths(basedir):
                yield filename
            return

        element_domains = list(self.__splits.keys())
        include_domains = element_domains
        if splits:
            include_domains = [
                domain for domain in splits if domain in element_domains
            ]

        element_files = [
            os.path.join(os.sep, filename)
            for filename in utils.list_relative_paths(basedir)
        ]

        for filename in element_files:
            include_file = False
            claimed_file = False

            for domain in element_domains:
                if self.__splits[domain].match(filename):
                    claimed_file = True
                    if domain in include_domains:
                        include_file = True

            if orphans and not claimed_file:
                include_file = True

            if include_file:
                yield filename.lstrip(os.sep)
