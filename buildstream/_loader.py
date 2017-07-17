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
from collections import Mapping

from . import LoadError, LoadErrorReason
from . import _yaml
from ._yaml import CompositePolicy, CompositeTypeError, CompositeOverrideError

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
    VARIANT = "variant"
    VARIANTS = "variants"
    PROJECT_VARIANT = "project-variant"
    ARCHES = "arches"
    HOST_ARCHES = "host-arches"
    SOURCES = "sources"
    CONFIG = "config"
    VARIABLES = "variables"
    ENVIRONMENT = "environment"
    ENV_NOCACHE = "environment-nocache"
    PUBLIC = "public"
    TYPE = "type"
    BUILD = "build"
    RUNTIME = "runtime"
    DIRECTORY = "directory"


# A simple dependency object
#
class Dependency():
    def __init__(self, owner_name, name, variant_name=None, filename=None,
                 dep_type=None, provenance=None):
        self.owner = owner_name
        self.name = name
        self.variant_name = variant_name
        self.filename = filename
        self.dep_type = dep_type
        self.provenance = provenance


# Holds a variant dictionary and normalized Dependency list
# for later compositing, after resolving which variants to choose
#
class Variant():
    def __init__(self, owner, data, project_variants):
        self.data = data
        self.name = _yaml.node_get(self.data, str, Symbol.VARIANT)
        self.dependencies = extract_depends_from_node(owner, self.data)

        # Assert valid project variants
        assert_project_variant(self.data, project_variants)

        del self.data[Symbol.VARIANT]


# VariantDisagreement is raised to indicate that 2 elements
# depend on a given element in a way that conflicts
#
class VariantDisagreement(Exception):
    def __init__(self, element_config1, element_config2, variant=None):
        path1 = element_config1.make_path()

        if variant:
            path2 = "Expected variant {}".format(variant)
        else:
            path2 = element_config2.make_path()
        super(VariantDisagreement, self).__init__(
            "Variant disagreement occurred.\n  {}\n  {}"
            .format(path1, path2))


# VariantInvalid is raised to indicate that a nonexisting
# variant name on an element was requested
#
class VariantInvalid(Exception):
    def __init__(self, dependency, element, variant_name):
        message = "Variant '{}' is invalid for element {}" \
                  .format(variant_name, element.name)
        if dependency:
            message = "{}: {}".format(dependency.provenance, message)

        super(VariantInvalid, self).__init__(message)


# A utility object wrapping the LoadElement, this represents
# a hypothetical configuration of an element, it describes:
#
#  o The dependency pulling in the element
#  o The chosen variant
#  o The dependencies the element has when configured for the given variant
#
class LoadElementConfig():
    def __init__(self, parent_config, element, variant_name=None):
        self.parent_config = parent_config
        self.element = element
        self.filename = element.filename
        self.variant_name = variant_name
        self.deps = element.deps_for_variant(variant_name)

    def __str__(self):
        if self.variant_name:
            return "{} ({})".format(self.filename, self.variant_name)

        return self.filename

    def make_path(self):
        path = str(self)
        if self.parent_config:
            path = self.parent_config.make_path() + ' -> ' + path
        return path


# resolve_arch()
#
# Composites the data node with the active arch dict and discards
# the arches dict from the data node afterwards, this is shared
# with project.py
#
def resolve_arch(data, host_arch, target_arch=None):

    def resolve_single_arch_conditional(symbol, active_arch):
        arches = _yaml.node_get(data, Mapping, symbol, default_value={})

        arch = {}
        if arches:
            arch = _yaml.node_get(arches, Mapping, active_arch, default_value={})

        if arch:
            try:
                _yaml.composite_dict(data, arch,
                                     policy=CompositePolicy.ARRAY_APPEND,
                                     typesafe=True)
            except CompositeTypeError as e:
                provenance = _yaml.node_get_provenance(arch, key=active_arch)
                raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                                "%s: Arch %s specifies type '%s' for path '%s', expected '%s'" %
                                (str(provenance),
                                 active_arch,
                                 e.actual_type.__name__,
                                 e.path,
                                 e.expected_type.__name__)) from e

        del data[symbol]

    resolve_single_arch_conditional(Symbol.HOST_ARCHES, active_arch=host_arch)
    resolve_single_arch_conditional(Symbol.ARCHES, active_arch=target_arch or host_arch)


def assert_project_variant(node, project_variants):
    variant = _yaml.node_get(node, str,
                             Symbol.PROJECT_VARIANT,
                             default_value="") or None
    if variant and variant not in project_variants:
        provenance = _yaml.node_get_provenance(node, key=Symbol.PROJECT_VARIANT)
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "{}: Specified invalid project variant '{}'".format(provenance, variant))


# A transient object breaking down what is loaded
# allowing us to do complex operations in multiple
# passes
#
class LoadElement():

    def __init__(self, data, filename, basedir,
                 host_arch, target_arch,
                 elements, project_variants):

        self.filename = filename
        self.data = data
        self.host_arch = host_arch
        self.target_arch = target_arch
        self.name = filename
        self.elements = elements

        # These are shared with the owning Loader object
        self.basedir = basedir

        # Process arch conditionals
        resolve_arch(self.data, self.host_arch, self.target_arch)

        # Assert valid project variant, if any
        assert_project_variant(self.data, project_variants)

        # Dependency objects after resolving variants
        self.variant_name = None
        self.deps = []
        self.dep_cache = None

        # Base dependencies
        self.base_deps = extract_depends_from_node(self.name, self.data)

        # Load the Variants
        self.variants = []
        variants_node = _yaml.node_get(self.data, list, Symbol.VARIANTS, default_value=[])
        for variant_node in variants_node:
            index = variants_node.index(variant_node)
            variant_node = _yaml.node_get(self.data, Mapping, Symbol.VARIANTS, indices=[index])
            variant = Variant(self.name, variant_node, project_variants)

            # Process arch conditionals on individual variants
            resolve_arch(variant.data, self.host_arch, self.target_arch)
            self.variants.append(variant)

        if len(self.variants) == 1:
            provenance = _yaml.node_get_provenance(self.data, key=Symbol.VARIANTS)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "%s: Only one variant declared, an element "
                            "declaring variants must declare at least two variants" %
                            str(provenance))

        # Strip em from the data now
        del self.data[Symbol.VARIANTS]

    #############################################
    #        Routines used by the Loader        #
    #############################################

    # Checks if this element depends on another element, directly
    # or indirectly. This does NOT follow variants and is only
    # useful after variants are resolved.
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

    # Fetch a Variant by name
    #
    def lookup_variant(self, variant_name):
        for variant in self.variants:
            if variant.name == variant_name:
                return variant

    # deps_for_variant()
    #
    # Fetches the set of Dependency objects for a given variant name
    #
    def deps_for_variant(self, variant_name):
        deps = copy.copy(self.base_deps)

        variant = None
        if variant_name:
            variant = self.lookup_variant(variant_name)

        # If the Dependency is already mentioned in the base dependencies
        # a variant may modify it by overriding the dependency variant
        if variant:

            for variant_dep in variant.dependencies:
                override = False
                for dep in deps:
                    if dep.filename == variant_dep.filename:
                        index = deps.index(dep)
                        deps[index] = variant_dep
                        override = True
                        break

                # Dependency not already declared, append new one
                if not override:
                    deps.append(variant_dep)

        # Return the list of dependencies for this variant
        return deps

    # Apply the chosen variant into the element data
    #
    def apply_element_config(self, element_config):

        # Save the final decision on Dependencies
        self.element_config = element_config
        self.variant_name = element_config.variant_name
        self.deps = element_config.deps

        variant = None
        if self.variant_name:
            variant = self.lookup_variant(self.variant_name)

        if variant:
            provenance = _yaml.node_get_provenance(variant.data)

            # Composite anything from the variant data into the element data
            #
            # Possibly this should not be typesafe, since branch names can
            # possibly be strings or interpreted by YAML as integers (for
            # numeric branch names)
            #
            try:
                _yaml.composite_dict(self.data, variant.data,
                                     policy=CompositePolicy.ARRAY_APPEND,
                                     typesafe=True)
            except CompositeTypeError as e:
                raise LoadError(
                    LoadErrorReason.ILLEGAL_COMPOSITE,
                    "%s: Variant '%s' specifies type '%s' for path '%s', expected '%s'" %
                    (str(provenance),
                     element_config.variant_name,
                     e.actual_type.__name__, e.path,
                     e.expected_type.__name__)) from e


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
            # Make variant optional, for this we set it to None after
            variant = _yaml.node_get(dep, str, Symbol.VARIANT, default_value="")
            if not variant:
                variant = None

            # Make type optional, for this we set it to None after
            dep_type = _yaml.node_get(dep, str, Symbol.TYPE, default_value="")
            if not dep_type:
                dep_type = None
            elif dep_type not in [Symbol.BUILD, Symbol.RUNTIME]:
                provenance = _yaml.node_get_provenance(dep, key=Symbol.TYPE)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "%s: Dependency type '%s' is not 'build' or 'runtime'" %
                                (str(provenance), dep_type))

            filename = _yaml.node_get(dep, str, Symbol.FILENAME)
            dependency = Dependency(owner, filename, variant_name=variant, filename=filename,
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

    def __init__(self, basedir, filename, variant, host_arch, target_arch, project_variants):

        # Ensure we have an absolute path for the base directory
        #
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        if os.path.isabs(filename):
            # XXX Should this just be an assertion ?
            # Expect that the caller gives us the right thing at least ?
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "Target '%s' was not specified as a relative "
                            "path to the base project directory: %s" %
                            (filename, basedir))

        # Base project directory
        self.basedir = basedir

        # Target bst filename
        self.target_filename = filename
        self.target = filename

        # Optional variant
        self.target_variant = variant

        # Project Variant
        self.project_variants = project_variants
        self.project_variant = None
        self.project_variant_requester = None

        self.host_arch = host_arch
        self.target_arch = target_arch

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
        profile_start(Topics.LOAD_PROJECT, self.target_filename)

        try:
            target = self.load_file(self.target_filename, rewritable, ticker)
            if self.target_variant and target.lookup_variant(self.target_variant) is None:
                raise VariantInvalid(None, target, self.target_variant)
        except VariantInvalid as e:
            raise LoadError(LoadErrorReason.INVALID_VARIANT, str(e)) from e

        profile_end(Topics.LOAD_PROJECT, self.target_filename)

        #
        # Deal with variants
        #
        profile_start(Topics.VARIANTS, self.target_filename)
        self.resolve_variants()
        profile_end(Topics.VARIANTS, self.target_filename)

        #
        # Now that we've resolve the dependencies, scan them for circular dependencies
        #
        profile_start(Topics.CIRCULAR_CHECK, self.target_filename)
        self.check_circular_deps(self.target)
        profile_end(Topics.CIRCULAR_CHECK, self.target_filename)

        #
        # Resolve the project variant, if any
        #
        self.resolve_project_variant(self.target)

        #
        # Sort direct dependencies of elements by their dependency ordering
        #
        profile_start(Topics.SORT_DEPENDENCIES, self.target_filename)
        self.sort_dependencies(self.target)
        profile_end(Topics.SORT_DEPENDENCIES, self.target_filename)

        # Finally, wrap what we have into LoadElements and return the target
        #
        return self.collect_element(self.target)

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

        fullpath = os.path.join(self.basedir, filename)

        # Load the element and track it in our elements table
        data = _yaml.load(fullpath, shortname=filename, copy_tree=rewritable)
        element = LoadElement(data, filename, self.basedir,
                              self.host_arch, self.target_arch,
                              self.elements, self.project_variants)

        self.elements[filename] = element

        # Load all possible dependency files for the new LoadElement
        for dep in element.base_deps:
            self.load_dependency_file(dep, rewritable, ticker)

        for variant in element.variants:
            for dep in variant.dependencies:
                self.load_dependency_file(dep, rewritable, ticker)

        return element

    def load_dependency_file(self, dependency, rewritable, ticker):

        element = self.load_file(dependency.filename, rewritable, ticker)

        # Check for invalid variant dependencies
        if dependency.variant_name and element.lookup_variant(dependency.variant_name) is None:
            raise VariantInvalid(dependency, element, dependency.variant_name)

    ########################################
    #          Resolving Variants          #
    ########################################
    #
    # The first rule of variants is that for any given element provided by
    # itself as a pipeline target, all variants of that element must be
    # buildable and not present any variant conflict.
    #
    # However, any variant of a given element that is not the target may
    # end up being built differently - this is because siblings in the pipeline
    # may prefer a variant of a dependency for which the given element's
    # dependency was ambivalent.
    #
    # Considering that variants can effect what and how an element depends
    # on other elements; resolving the variants is a trial and error activity,
    # even if this is not true for the target element (as stated as the first
    # rule), it is true of every other element in a given pipeline.
    #
    # As such, resolving the variants is a recursive process of trial and error
    #
    #  1.) Construct a "variant tree"
    #
    #      The variant tree is a tree of elements dicts, these refer to the
    #      element filename and contain an array of variants; each member of
    #      the variant array holds an array of the dependencies which would be
    #      chosen if the given variant of the given element were chosen.
    #
    #  2.) Starting at the top level, try to resolve the
    #
    #      For each element; collect an array of its variants; each member of
    #      the variant array speaks for the dependencies of the given element
    #
    def resolve_variants(self):
        target_variant = self.target_variant
        target_element = self.elements[self.target]

        # If a target was not specified, this is an explicit request for the
        # first variant
        if not target_variant and target_element.variants:
            target_variant = target_element.variants[0].name

        # Recurse until the cows come home !
        #
        toplevel_config = LoadElementConfig(None, target_element, target_variant)
        try:
            pool, _ = self.try_element_configuration(toplevel_config, {}, {})

        except VariantDisagreement as e:
            raise LoadError(LoadErrorReason.VARIANT_DISAGREEMENT, str(e)) from e

        # Now apply the chosen variant configurations
        #
        for _, element_config in pool.items():
            element_config.element.apply_element_config(element_config)

    #
    # try_element_configuration()
    #
    # Args:
    #   element_config (LoadElementConfig): the element to try
    #   pool (dict): A dict of LoadElementConfig objects
    #   restruction_pool: A dict of variant names explicitly required
    #
    # Returns:
    #   A new configuration
    #
    # With a given configuration in context, reports whether the configuration
    # is a valid one for the given element and all of the possible elements on
    # which this element depends, returning a new configuration comprised of
    # the given configuration and the first valid configuration of its
    # dependencies
    #
    def try_element_configuration(self, element_config, pool, restriction_pool):

        if element_config.filename in pool:
            config = pool[element_config.filename]

            # The configuration pool can have only one selected configuration
            # for each element, handle intersections and conflicts.
            #
            if config.element is element_config.element:

                if config.variant_name != element_config.variant_name:

                    # Two different variants of the same element should be reached
                    # on a path of variant agreement.
                    raise VariantDisagreement(element_config, config)
                else:
                    # A path converges on the same element configuration,
                    # no need to recurse as we already have a result for this.
                    return (pool, restriction_pool)

        if element_config.filename in restriction_pool:
            restrict_variant = restriction_pool[element_config.filename]

            if element_config.variant_name and element_config.variant_name != restrict_variant:
                raise VariantDisagreement(element_config, None, restrict_variant)

        # Now add ourselves to the pool and recurse into the dependency list
        new_pool = dict(pool)
        new_pool[element_config.filename] = element_config

        # Add restriction pool to go along with this pool
        #
        new_restriction_pool = dict(restriction_pool)
        for dep in element_config.deps:
            if dep.variant_name:
                new_restriction_pool[dep.name] = dep.variant_name

        return self.configure_dependency_variants(element_config, element_config.deps,
                                                  new_pool, new_restriction_pool)

    def configure_dependency_variants(self, parent_config, deps, pool, restriction_pool):

        # This is just the end of the list
        if not deps:
            return (pool, restriction_pool)

        # Loop over the possible variants for this dependency
        dependency = deps[0]
        element = self.elements[dependency.name]

        # First create one list of element configurations to try, one for
        # each possible variant under this element configuration
        #
        element_configs_to_try = []
        if dependency.variant_name:
            config = LoadElementConfig(parent_config, element, dependency.variant_name)
            element_configs_to_try.append(config)
        elif len(element.variants) == 0:
            config = LoadElementConfig(parent_config, element, None)
            element_configs_to_try.append(config)
        else:
            for variant in element.variants:
                config = LoadElementConfig(parent_config, element, variant.name)
                element_configs_to_try.append(config)

        # Loop over every possible element configuration for this dependency
        #
        result_pool = None
        result_restrict = None
        last_error = None

        for element_config in element_configs_to_try:

            # Reset the attempted new pool for each try
            result_pool = None
            result_restrict = None

            try:
                # If this configuration of the this element succeeds...
                try_pool, try_restrict = self.try_element_configuration(element_config, pool, restriction_pool)

                # ... Then recurse into sibling elements
                result_pool, result_restrict = self.configure_dependency_variants(parent_config, deps[1:],
                                                                                  try_pool, try_restrict)

            except VariantDisagreement as e:
                last_error = e
                continue

            # If we've reached here without any disagreement, then we've found the
            # first valid configuration, which should take priority over any others.
            break

        # If unable to find any valid configuration, raise a VariantDisagreement
        if not result_pool:
            raise last_error

        return (result_pool, result_restrict)

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
    #         Resolve Project Variant      #
    ########################################
    def resolve_project_variant(self, element_name):
        element = self.elements[element_name]
        project_variant = _yaml.node_get(element.data, str,
                                         Symbol.PROJECT_VARIANT,
                                         default_value="") or None

        if project_variant:
            if not self.project_variant:
                self.project_variant = project_variant
                self.project_variant_requester = element_name
            elif project_variant != self.project_variant:
                request1 = "{} requested project variant '{}'" \
                           .format(self.project_variant_requester,
                                   self.project_variant)
                request2 = "{} requested project variant '{}'" \
                           .format(element_name, project_variant)
                raise LoadError(LoadErrorReason.VARIANT_DISAGREEMENT,
                                "Project variant disagreement occurred.\n  {}\n  {}"
                                .format(request1, request2))

        for dep in element.deps:
            self.resolve_project_variant(dep.name)

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
        meta_element = MetaElement(element_name, kind, element.variant_name,
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
