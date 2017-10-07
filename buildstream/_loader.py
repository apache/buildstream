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
import copy
from functools import cmp_to_key
from collections import Mapping, namedtuple

from . import LoadError, LoadErrorReason
from . import _yaml
from ._yaml import CompositeTypeError

from ._metaelement import MetaElement
from ._metasource import MetaSource
from ._profile import Topics, profile_start, profile_end


#################################################
#                 Local Types                   #
#################################################
#
# List of symbols we recognize
#
class Symbol():
    FILENAME = "filename"
    KIND = "kind"
    DEPENDS = "depends"
    SOURCES = "sources"
    CONFIG = "config"
    VARIABLES = "variables"
    ENVIRONMENT = "environment"
    ENV_NOCACHE = "environment-nocache"
    PUBLIC = "public"
    TYPE = "type"
    BUILD = "build"
    RUNTIME = "runtime"
    ALL = "all"
    DIRECTORY = "directory"


# A simple dependency object
#
class Dependency():
    def __init__(self, owner_name, name, filename=None,
                 dep_type=None, provenance=None):
        self.owner = owner_name
        self.name = name
        self.filename = filename
        self.dep_type = dep_type
        self.provenance = provenance


# A transient object breaking down what is loaded
# allowing us to do complex operations in multiple
# passes
#
class LoadElement():

    def __init__(self, data, filename, basedir, elements):

        self.filename = filename
        self.data = data
        self.name = filename
        self.elements = elements

        # These are shared with the owning Loader object
        self.basedir = basedir

        # Ensure the root node is valid
        _yaml.node_validate(self.data, [
            'kind', 'depends', 'sources',
            'variables', 'environment', 'environment-nocache',
            'config', 'public', 'description',
        ])

        # Cache dependency tree to detect circular dependencies
        self.dep_cache = None

        # Dependencies
        self.deps = extract_depends_from_node(self.name, self.data)

    #############################################
    #        Routines used by the Loader        #
    #############################################

    # Checks if this element depends on another element, directly
    # or indirectly.
    #
    def depends(self, other):

        self.ensure_depends_cache()
        return self.dep_cache.get(other.name) is not None

    def ensure_depends_cache(self):

        if self.dep_cache:
            return

        self.dep_cache = {}
        for dep in self.deps:
            elt = self.elements[dep.name]

            # Ensure the cache of the element we depend on
            elt.ensure_depends_cache()

            # We depend on this element
            self.dep_cache[dep.name] = True

            # And we depend on everything this element depends on
            self.dep_cache.update(elt.dep_cache)


# Creates an array of dependency dicts from a given dict node 'data',
# allows both strings and dicts for expressing the dependency and
# throws a comprehensive LoadError in the case that the data is malformed.
#
# After extracting depends, they are removed from the data node
#
# Returns a normalized array of Dependency objects
def extract_depends_from_node(owner, data):
    depends = _yaml.node_get(data, list, Symbol.DEPENDS, default_value=[])
    output_deps = []

    for dep in depends:
        dep_provenance = _yaml.node_get_provenance(data, key=Symbol.DEPENDS, indices=[depends.index(dep)])

        if isinstance(dep, str):
            dependency = Dependency(owner, dep, filename=dep, provenance=dep_provenance)

        elif isinstance(dep, Mapping):
            _yaml.node_validate(dep, ['filename', 'type'])

            # Make type optional, for this we set it to None after
            dep_type = _yaml.node_get(dep, str, Symbol.TYPE, default_value="")
            if not dep_type or dep_type == Symbol.ALL:
                dep_type = None
            elif dep_type not in [Symbol.BUILD, Symbol.RUNTIME]:
                provenance = _yaml.node_get_provenance(dep, key=Symbol.TYPE)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "%s: Dependency type '%s' is not 'build', 'runtime' or 'all'" %
                                (str(provenance), dep_type))

            filename = _yaml.node_get(dep, str, Symbol.FILENAME)
            dependency = Dependency(owner, filename, filename=filename,
                                    dep_type=dep_type, provenance=dep_provenance)

        else:
            index = depends.index(dep)
            provenance = _yaml.node_get_provenance(data, key=Symbol.DEPENDS, indices=[index])

            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "%s: List '%s' element %d is not a list or dict" %
                            (str(provenance), Symbol.DEPENDS, index))

        output_deps.append(dependency)

    # Now delete "depends", we dont want it anymore
    del data[Symbol.DEPENDS]

    return output_deps


#################################################
#                   The Loader                  #
#################################################
#
# The Loader class does the heavy lifting of parsing a target
# bst file and creating a tree of LoadElements
#
class Loader():

    def __init__(self, basedir, filenames, options):

        # Ensure we have an absolute path for the base directory
        #
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        for filename in filenames:
            if os.path.isabs(filename):
                # XXX Should this just be an assertion ?
                # Expect that the caller gives us the right thing at least ?
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "Target '%s' was not specified as a relative "
                                "path to the base project directory: %s" %
                                (filename, basedir))

        self.options = options   # Project options (OptionPool)
        self.basedir = basedir   # Base project directory
        self.targets = filenames   # Target bst elements

        self.meta_elements = {}  # Dict of resolved meta elements by name
        self.elements = {}       # Dict of elements

    ########################################
    #           Main Entry Point           #
    ########################################

    # load():
    #
    # Loads the project based on the parameters given to the constructor
    #
    # Args:
    #    rewritable (bool): Whether the loaded files should be rewritable
    #                       this is a bit more expensive due to deep copies
    #    ticker (callable): An optional function for tracking load progress
    #
    # Raises: LoadError
    #
    # Returns: The toplevel LoadElement
    def load(self, rewritable=False, ticker=None):

        # First pass, recursively load files and populate our table of LoadElements
        #
        for target in self.targets:
            profile_start(Topics.LOAD_PROJECT, target)
            self.load_file(target, rewritable, ticker)
            profile_end(Topics.LOAD_PROJECT, target)

        #
        # Now that we've resolve the dependencies, scan them for circular dependencies
        #

        # Set up a dummy element that depends on all top-level targets
        # to resolve potential circular dependencies between them
        DummyTarget = namedtuple('DummyTarget', ['name', 'deps'])
        dummy = DummyTarget(name='', deps=[self.elements[e] for e in self.targets])
        self.elements[''] = dummy

        profile_key = "_".join(t for t in self.targets)
        profile_start(Topics.CIRCULAR_CHECK, profile_key)
        self.check_circular_deps('')
        profile_end(Topics.CIRCULAR_CHECK, profile_key)

        #
        # Sort direct dependencies of elements by their dependency ordering
        #
        for target in self.targets:
            profile_start(Topics.SORT_DEPENDENCIES, target)
            self.sort_dependencies(target)
            profile_end(Topics.SORT_DEPENDENCIES, target)

        # Finally, wrap what we have into LoadElements and return the target
        #
        return [self.collect_element(target) for target in self.targets]

    ########################################
    #             Loading Files            #
    ########################################

    # Recursively load bst files
    #
    def load_file(self, filename, rewritable, ticker):

        # Silently ignore already loaded files
        if filename in self.elements:
            return self.elements[filename]

        # Call the ticker
        if ticker:
            ticker(filename)

        # Load the data and process any conditional statements therein
        fullpath = os.path.join(self.basedir, filename)
        data = _yaml.load(fullpath, shortname=filename, copy_tree=rewritable)
        self.options.process_node(data)

        element = LoadElement(data, filename, self.basedir, self.elements)

        self.elements[filename] = element

        # Load all dependency files for the new LoadElement
        for dep in element.deps:
            self.load_file(dep.filename, rewritable, ticker)

        return element

    ########################################
    #     Checking Circular Dependencies   #
    ########################################
    #
    # Detect circular dependencies on LoadElements with
    # dependencies already resolved.
    #
    def check_circular_deps(self, element_name, check_elements=None, validated=None):

        if check_elements is None:
            check_elements = {}
        if validated is None:
            validated = {}

        element = self.elements[element_name]

        # Skip already validated branches
        if validated.get(element_name) is not None:
            return

        if check_elements.get(element_name) is not None:
            raise LoadError(LoadErrorReason.CIRCULAR_DEPENDENCY,
                            "Circular dependency detected for element: %s" %
                            element.filename)

        # Push / Check each dependency / Pop
        check_elements[element_name] = True
        for dep in element.deps:
            self.check_circular_deps(dep.name, check_elements, validated)
        del check_elements[element_name]

        # Eliminate duplicate paths
        validated[element_name] = True

    ########################################
    #            Element Sorting           #
    ########################################
    #
    # Sort dependencies of each element by their dependencies,
    # so that direct dependencies which depend on other direct
    # dependencies (directly or indirectly) appear later in the
    # list.
    #
    # This avoids the need for performing multiple topological
    # sorts throughout the build process.
    def sort_dependencies(self, element_name, visited=None):
        if visited is None:
            visited = {}

        if visited.get(element_name) is not None:
            return

        element = self.elements[element_name]
        for dep in element.deps:
            self.sort_dependencies(dep.name, visited=visited)

        def dependency_cmp(dep_a, dep_b):
            element_a = self.elements[dep_a.name]
            element_b = self.elements[dep_b.name]

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

            # This wont ever happen
            return 0

        # Now dependency sort, we ensure that if any direct dependency
        # directly or indirectly depends on another direct dependency,
        # it is found later in the list.
        element.deps.sort(key=cmp_to_key(dependency_cmp))

        visited[element_name] = True

    ########################################
    #          Element Collection          #
    ########################################
    # Collect the toplevel elements we have, resolve their deps and return !
    #
    def collect_element(self, element_name):

        element = self.elements[element_name]

        # Return the already built one, if we already built it
        meta_element = self.meta_elements.get(element_name)
        if meta_element:
            return meta_element

        data = element.data
        elt_provenance = _yaml.node_get_provenance(data)
        meta_sources = []

        sources = _yaml.node_get(data, list, Symbol.SOURCES, default_value=[])

        # Safe loop calling into _yaml.node_get() for each element ensures
        # we have good error reporting
        for i in range(len(sources)):
            source = _yaml.node_get(data, Mapping, Symbol.SOURCES, indices=[i])
            provenance = _yaml.node_get_provenance(source)
            kind = _yaml.node_get(source, str, Symbol.KIND)
            del source[Symbol.KIND]

            # Directory is optional
            directory = _yaml.node_get(source, str, Symbol.DIRECTORY, default_value='')
            if directory:
                del source[Symbol.DIRECTORY]
            else:
                directory = None

            index = sources.index(source)
            source_name = "{}-{}".format(element_name, index)

            meta_source = MetaSource(source_name, kind, source, directory,
                                     provenance.node,
                                     provenance.toplevel,
                                     provenance.filename)
            meta_sources.append(meta_source)

        kind = _yaml.node_get(data, str, Symbol.KIND)
        meta_element = MetaElement(element_name, kind,
                                   elt_provenance, meta_sources,
                                   _yaml.node_get(data, Mapping, Symbol.CONFIG, default_value={}),
                                   _yaml.node_get(data, Mapping, Symbol.VARIABLES, default_value={}),
                                   _yaml.node_get(data, Mapping, Symbol.ENVIRONMENT, default_value={}),
                                   _yaml.node_get(data, list, Symbol.ENV_NOCACHE, default_value=[]),
                                   _yaml.node_get(data, Mapping, Symbol.PUBLIC, default_value={}))

        # Cache it now, make sure it's already there before recursing
        self.meta_elements[element_name] = meta_element

        # Descend
        for dep in element.deps:
            meta_dep = self.collect_element(dep.name)
            if dep.dep_type != 'runtime':
                meta_element.build_dependencies.append(meta_dep)
            if dep.dep_type != 'build':
                meta_element.dependencies.append(meta_dep)

        return meta_element
