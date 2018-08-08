#
#  Copyright (C) 2018 Codethink Limited
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
from functools import cmp_to_key
from collections import Mapping, namedtuple
import tempfile
import shutil

from .._exceptions import LoadError, LoadErrorReason
from .. import Consistency
from .. import _yaml
from ..element import Element
from .._profile import Topics, profile_start, profile_end
from .._platform import Platform
from .._includes import Includes

from .types import Symbol, Dependency
from .loadelement import LoadElement
from . import MetaElement
from . import MetaSource


# Loader():
#
# The Loader class does the heavy lifting of parsing target
# bst files and ultimately transforming them into a list of MetaElements
# with their own MetaSources, ready for instantiation by the core.
#
# Args:
#    context (Context): The Context object
#    project (Project): The toplevel Project object
#    parent (Loader): A parent Loader object, in the case this is a junctioned Loader
#    tempdir (str): A directory to cleanup with the Loader, given to the loader by a parent
#                   loader in the case that this loader is a subproject loader.
#
class Loader():

    def __init__(self, context, project, *, parent=None, tempdir=None):

        # Ensure we have an absolute path for the base directory
        basedir = project.element_path
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        #
        # Public members
        #
        self.project = project   # The associated Project

        #
        # Private members
        #
        self._context = context
        self._options = project.options      # Project options (OptionPool)
        self._basedir = basedir              # Base project directory
        self._first_pass_options = project.first_pass_config.options  # Project options (OptionPool)
        self._tempdir = tempdir              # A directory to cleanup
        self._parent = parent                # The parent loader

        self._meta_elements = {}  # Dict of resolved meta elements by name
        self._elements = {}       # Dict of elements
        self._loaders = {}        # Dict of junction loaders

        self._includes = Includes(self, copy_tree=True)

    # load():
    #
    # Loads the project based on the parameters given to the constructor
    #
    # Args:
    #    rewritable (bool): Whether the loaded files should be rewritable
    #                       this is a bit more expensive due to deep copies
    #    ticker (callable): An optional function for tracking load progress
    #    targets (list of str): Target, element-path relative bst filenames in the project
    #    fetch_subprojects (bool): Whether to fetch subprojects while loading
    #
    # Raises: LoadError
    #
    # Returns: The toplevel LoadElement
    def load(self, targets, rewritable=False, ticker=None, fetch_subprojects=False):

        for filename in targets:
            if os.path.isabs(filename):
                # XXX Should this just be an assertion ?
                # Expect that the caller gives us the right thing at least ?
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "Target '{}' was not specified as a relative "
                                "path to the base project directory: {}"
                                .format(filename, self._basedir))

        # First pass, recursively load files and populate our table of LoadElements
        #
        deps = []

        for target in targets:
            profile_start(Topics.LOAD_PROJECT, target)
            junction, name, loader = self._parse_name(target, rewritable, ticker,
                                                      fetch_subprojects=fetch_subprojects)
            loader._load_file(name, rewritable, ticker, fetch_subprojects)
            deps.append(Dependency(name, junction=junction))
            profile_end(Topics.LOAD_PROJECT, target)

        #
        # Now that we've resolve the dependencies, scan them for circular dependencies
        #

        # Set up a dummy element that depends on all top-level targets
        # to resolve potential circular dependencies between them
        DummyTarget = namedtuple('DummyTarget', ['name', 'full_name', 'deps'])

        dummy = DummyTarget(name='', full_name='', deps=deps)
        self._elements[''] = dummy

        profile_key = "_".join(t for t in targets)
        profile_start(Topics.CIRCULAR_CHECK, profile_key)
        self._check_circular_deps('')
        profile_end(Topics.CIRCULAR_CHECK, profile_key)

        ret = []
        #
        # Sort direct dependencies of elements by their dependency ordering
        #
        for target in targets:
            profile_start(Topics.SORT_DEPENDENCIES, target)
            junction, name, loader = self._parse_name(target, rewritable, ticker,
                                                      fetch_subprojects=fetch_subprojects)
            loader._sort_dependencies(name)
            profile_end(Topics.SORT_DEPENDENCIES, target)
            # Finally, wrap what we have into LoadElements and return the target
            #
            ret.append(loader._collect_element(name))

        return ret

    # cleanup():
    #
    # Remove temporary checkout directories of subprojects
    #
    def cleanup(self):
        if self._parent and not self._tempdir:
            # already done
            return

        # recurse
        for loader in self._loaders.values():
            # value may be None with nested junctions without overrides
            if loader is not None:
                loader.cleanup()

        if not self._parent:
            # basedir of top-level loader is never a temporary directory
            return

        # safe guard to not accidentally delete directories outside builddir
        if self._tempdir.startswith(self._context.builddir + os.sep):
            if os.path.exists(self._tempdir):
                shutil.rmtree(self._tempdir)

    # get_element_for_dep():
    #
    # Gets a cached LoadElement by Dependency object
    #
    # This is used by LoadElement
    #
    # Args:
    #    dep (Dependency): The dependency to search for
    #
    # Returns:
    #    (LoadElement): The cached LoadElement
    #
    def get_element_for_dep(self, dep):
        loader = self._get_loader_for_dep(dep)
        return loader._elements[dep.name]

    ###########################################
    #            Private Methods              #
    ###########################################

    # _load_file():
    #
    # Recursively load bst files
    #
    # Args:
    #    filename (str): The element-path relative bst file
    #    rewritable (bool): Whether we should load in round trippable mode
    #    ticker (callable): A callback to report loaded filenames to the frontend
    #    fetch_subprojects (bool): Whether to fetch subprojects while loading
    #
    # Returns:
    #    (LoadElement): A loaded LoadElement
    #
    def _load_file(self, filename, rewritable, ticker, fetch_subprojects):

        # Silently ignore already loaded files
        if filename in self._elements:
            return self._elements[filename]

        # Call the ticker
        if ticker:
            ticker(filename)

        # Load the data and process any conditional statements therein
        fullpath = os.path.join(self._basedir, filename)
        try:
            node = _yaml.load(fullpath, shortname=filename, copy_tree=rewritable, project=self.project)
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_FILE:
                # If we can't find the file, try to suggest plausible
                # alternatives by stripping the element-path from the given
                # filename, and verifying that it exists.
                message = "Could not find element '{}' in elements directory '{}'".format(filename, self._basedir)
                detail = None
                elements_dir = os.path.relpath(self._basedir, self.project.directory)
                element_relpath = os.path.relpath(filename, elements_dir)
                if filename.startswith(elements_dir) and os.path.exists(os.path.join(self._basedir, element_relpath)):
                    detail = "Did you mean '{}'?".format(element_relpath)
                raise LoadError(LoadErrorReason.MISSING_FILE,
                                message, detail=detail) from e
            elif e.reason == LoadErrorReason.LOADING_DIRECTORY:
                # If a <directory>.bst file exists in the element path,
                # let's suggest this as a plausible alternative.
                message = str(e)
                detail = None
                if os.path.exists(os.path.join(self._basedir, filename + '.bst')):
                    element_name = filename + '.bst'
                    detail = "Did you mean '{}'?\n".format(element_name)
                raise LoadError(LoadErrorReason.LOADING_DIRECTORY,
                                message, detail=detail) from e
            else:
                raise
        kind = _yaml.node_get(node, str, Symbol.KIND)
        if kind == "junction":
            self._first_pass_options.process_node(node)
        else:
            self.project.ensure_fully_loaded()

            self._includes.process(node)

            self._options.process_node(node)

        element = LoadElement(node, filename, self)

        self._elements[filename] = element

        # Load all dependency files for the new LoadElement
        for dep in element.deps:
            if dep.junction:
                self._load_file(dep.junction, rewritable, ticker, fetch_subprojects)
                loader = self._get_loader(dep.junction, rewritable=rewritable, ticker=ticker,
                                          fetch_subprojects=fetch_subprojects)
            else:
                loader = self

            dep_element = loader._load_file(dep.name, rewritable, ticker, fetch_subprojects)

            if _yaml.node_get(dep_element.node, str, Symbol.KIND) == 'junction':
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Cannot depend on junction"
                                .format(dep.provenance))

        return element

    # _check_circular_deps():
    #
    # Detect circular dependencies on LoadElements with
    # dependencies already resolved.
    #
    # Args:
    #    element_name (str): The element-path relative element name to check
    #
    # Raises:
    #    (LoadError): In case there was a circular dependency error
    #
    def _check_circular_deps(self, element_name, check_elements=None, validated=None):

        if check_elements is None:
            check_elements = {}
        if validated is None:
            validated = {}

        element = self._elements[element_name]

        # element name must be unique across projects
        # to be usable as key for the check_elements and validated dicts
        element_name = element.full_name

        # Skip already validated branches
        if validated.get(element_name) is not None:
            return

        if check_elements.get(element_name) is not None:
            raise LoadError(LoadErrorReason.CIRCULAR_DEPENDENCY,
                            "Circular dependency detected for element: {}"
                            .format(element.name))

        # Push / Check each dependency / Pop
        check_elements[element_name] = True
        for dep in element.deps:
            loader = self._get_loader_for_dep(dep)
            loader._check_circular_deps(dep.name, check_elements, validated)
        del check_elements[element_name]

        # Eliminate duplicate paths
        validated[element_name] = True

    # _sort_dependencies():
    #
    # Sort dependencies of each element by their dependencies,
    # so that direct dependencies which depend on other direct
    # dependencies (directly or indirectly) appear later in the
    # list.
    #
    # This avoids the need for performing multiple topological
    # sorts throughout the build process.
    #
    # Args:
    #    element_name (str): The element-path relative element name to sort
    #
    def _sort_dependencies(self, element_name, visited=None):
        if visited is None:
            visited = {}

        element = self._elements[element_name]

        # element name must be unique across projects
        # to be usable as key for the visited dict
        element_name = element.full_name

        if visited.get(element_name) is not None:
            return

        for dep in element.deps:
            loader = self._get_loader_for_dep(dep)
            loader._sort_dependencies(dep.name, visited=visited)

        def dependency_cmp(dep_a, dep_b):
            element_a = self.get_element_for_dep(dep_a)
            element_b = self.get_element_for_dep(dep_b)

            # Sort on inter element dependency first
            if element_a.depends(element_b):
                return 1
            elif element_b.depends(element_a):
                return -1

            # If there are no inter element dependencies, place
            # runtime only dependencies last
            if dep_a.dep_type != dep_b.dep_type:
                if dep_a.dep_type == Symbol.RUNTIME:
                    return 1
                elif dep_b.dep_type == Symbol.RUNTIME:
                    return -1

            # All things being equal, string comparison.
            if dep_a.name > dep_b.name:
                return 1
            elif dep_a.name < dep_b.name:
                return -1

            # Sort local elements before junction elements
            # and use string comparison between junction elements
            if dep_a.junction and dep_b.junction:
                if dep_a.junction > dep_b.junction:
                    return 1
                elif dep_a.junction < dep_b.junction:
                    return -1
            elif dep_a.junction:
                return -1
            elif dep_b.junction:
                return 1

            # This wont ever happen
            return 0

        # Now dependency sort, we ensure that if any direct dependency
        # directly or indirectly depends on another direct dependency,
        # it is found later in the list.
        element.deps.sort(key=cmp_to_key(dependency_cmp))

        visited[element_name] = True

    # _collect_element()
    #
    # Collect the toplevel elements we have
    #
    # Args:
    #    element_name (str): The element-path relative element name to sort
    #
    # Returns:
    #    (MetaElement): A recursively loaded MetaElement
    #
    def _collect_element(self, element_name):

        element = self._elements[element_name]

        # Return the already built one, if we already built it
        meta_element = self._meta_elements.get(element_name)
        if meta_element:
            return meta_element

        node = element.node
        elt_provenance = _yaml.node_get_provenance(node)
        meta_sources = []

        sources = _yaml.node_get(node, list, Symbol.SOURCES, default_value=[])
        element_kind = _yaml.node_get(node, str, Symbol.KIND)

        # Safe loop calling into _yaml.node_get() for each element ensures
        # we have good error reporting
        for i in range(len(sources)):
            source = _yaml.node_get(node, Mapping, Symbol.SOURCES, indices=[i])
            kind = _yaml.node_get(source, str, Symbol.KIND)
            del source[Symbol.KIND]

            # Directory is optional
            directory = _yaml.node_get(source, str, Symbol.DIRECTORY, default_value=None)
            if directory:
                del source[Symbol.DIRECTORY]

            index = sources.index(source)
            meta_source = MetaSource(element_name, index, element_kind, kind, source, directory)
            meta_sources.append(meta_source)

        meta_element = MetaElement(self.project, element_name, element_kind,
                                   elt_provenance, meta_sources,
                                   _yaml.node_get(node, Mapping, Symbol.CONFIG, default_value={}),
                                   _yaml.node_get(node, Mapping, Symbol.VARIABLES, default_value={}),
                                   _yaml.node_get(node, Mapping, Symbol.ENVIRONMENT, default_value={}),
                                   _yaml.node_get(node, list, Symbol.ENV_NOCACHE, default_value=[]),
                                   _yaml.node_get(node, Mapping, Symbol.PUBLIC, default_value={}),
                                   _yaml.node_get(node, Mapping, Symbol.SANDBOX, default_value={}),
                                   element_kind == 'junction')

        # Cache it now, make sure it's already there before recursing
        self._meta_elements[element_name] = meta_element

        # Descend
        for dep in element.deps:
            loader = self._get_loader_for_dep(dep)
            meta_dep = loader._collect_element(dep.name)
            if dep.dep_type != 'runtime':
                meta_element.build_dependencies.append(meta_dep)
            if dep.dep_type != 'build':
                meta_element.dependencies.append(meta_dep)

        return meta_element

    # _get_loader():
    #
    # Return loader for specified junction
    #
    # Args:
    #    filename (str): Junction name
    #    fetch_subprojects (bool): Whether to fetch subprojects while loading
    #
    # Raises: LoadError
    #
    # Returns: A Loader or None if specified junction does not exist
    def _get_loader(self, filename, *, rewritable=False, ticker=None, level=0, fetch_subprojects=False):
        # return previously determined result
        if filename in self._loaders:
            loader = self._loaders[filename]

            if loader is None:
                # do not allow junctions with the same name in different
                # subprojects
                raise LoadError(LoadErrorReason.CONFLICTING_JUNCTION,
                                "Conflicting junction {} in subprojects, define junction in {}"
                                .format(filename, self.project.name))

            return loader

        if self._parent:
            # junctions in the parent take precedence over junctions defined
            # in subprojects
            loader = self._parent._get_loader(filename, rewritable=rewritable, ticker=ticker,
                                              level=level + 1, fetch_subprojects=fetch_subprojects)
            if loader:
                self._loaders[filename] = loader
                return loader

        try:
            self._load_file(filename, rewritable, ticker, fetch_subprojects)
        except LoadError as e:
            if e.reason != LoadErrorReason.MISSING_FILE:
                # other load error
                raise

            if level == 0:
                # junction element not found in this or ancestor projects
                raise
            else:
                # mark junction as not available to allow detection of
                # conflicting junctions in subprojects
                self._loaders[filename] = None
                return None

        # meta junction element
        meta_element = self._collect_element(filename)
        if meta_element.kind != 'junction':
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Expected junction but element kind is {}".format(filename, meta_element.kind))

        platform = Platform.get_platform()
        element = Element._new_from_meta(meta_element, platform.artifactcache)
        element._preflight()

        for source in element.sources():
            # Handle the case where a subproject needs to be fetched
            #
            if source.get_consistency() == Consistency.RESOLVED:
                if fetch_subprojects:
                    if ticker:
                        ticker(filename, 'Fetching subproject from {} source'.format(source.get_kind()))
                    source._fetch()
                else:
                    detail = "Try fetching the project with `bst fetch {}`".format(filename)
                    raise LoadError(LoadErrorReason.SUBPROJECT_FETCH_NEEDED,
                                    "Subproject fetch needed for junction: {}".format(filename),
                                    detail=detail)

            # Handle the case where a subproject has no ref
            #
            elif source.get_consistency() == Consistency.INCONSISTENT:
                detail = "Try tracking the junction element with `bst track {}`".format(filename)
                raise LoadError(LoadErrorReason.SUBPROJECT_INCONSISTENT,
                                "Subproject has no ref for junction: {}".format(filename),
                                detail=detail)

        # Stage sources
        os.makedirs(self._context.builddir, exist_ok=True)
        basedir = tempfile.mkdtemp(prefix="{}-".format(element.normal_name), dir=self._context.builddir)
        element._stage_sources_at(basedir, mount_workspaces=False)

        # Load the project
        project_dir = os.path.join(basedir, element.path)
        try:
            from .._project import Project
            project = Project(project_dir, self._context, junction=element,
                              parent_loader=self, tempdir=basedir)
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_PROJECT_CONF:
                raise LoadError(reason=LoadErrorReason.INVALID_JUNCTION,
                                message="Could not find the project.conf file for {}. "
                                        "Expecting a project at path '{}'"
                                .format(element, element.path or '.')) from e
            else:
                raise

        loader = project.loader
        self._loaders[filename] = loader

        return loader

    # _get_loader_for_dep():
    #
    # Gets the appropriate Loader for a Dependency object
    #
    # Args:
    #    dep (Dependency): A Dependency object
    #
    # Returns:
    #    (Loader): The Loader object to use for this Dependency
    #
    def _get_loader_for_dep(self, dep):
        if dep.junction:
            # junction dependency, delegate to appropriate loader
            return self._loaders[dep.junction]
        else:
            return self

    # _parse_name():
    #
    # Get junction and base name of element along with loader for the sub-project
    #
    # Args:
    #   name (str): Name of target
    #   rewritable (bool): Whether the loaded files should be rewritable
    #                      this is a bit more expensive due to deep copies
    #   ticker (callable): An optional function for tracking load progress
    #   fetch_subprojects (bool): Whether to fetch subprojects while loading
    #
    # Returns:
    #   (tuple): - (str): name of the junction element
    #            - (str): name of the element
    #            - (Loader): loader for sub-project
    #
    def _parse_name(self, name, rewritable, ticker, fetch_subprojects=False):
        # We allow to split only once since deep junctions names are forbidden.
        # Users who want to refer to elements in sub-sub-projects are required
        # to create junctions on the top level project.
        junction_path = name.rsplit(':', 1)
        if len(junction_path) == 1:
            return None, junction_path[-1], self
        else:
            self._load_file(junction_path[-2], rewritable, ticker, fetch_subprojects)
            loader = self._get_loader(junction_path[-2], rewritable=rewritable, ticker=ticker,
                                      fetch_subprojects=fetch_subprojects)
            return junction_path[-2], junction_path[-1], loader
