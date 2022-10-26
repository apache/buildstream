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

import os
from contextlib import suppress

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from .. import _yaml
from ..element import Element
from ..node import Node
from .._profile import Topics, PROFILER
from .._includes import Includes
from .._utils import valid_chars_name
from ..types import _KeyStrength

from .types import Symbol
from . import loadelement
from .loadelement import LoadElement, Dependency, DependencyType, extract_depends_from_node


# Loader():
#
# The Loader class does the heavy lifting of parsing target
# bst files and ultimately transforming them into a list of LoadElements
# ready for instantiation by the core.
#
# Args:
#    project (Project): The toplevel Project object
#    parent (Loader): A parent Loader object, in the case this is a junctioned Loader
#    provenance_node (Node): The provenance of the reference to this project's junction
#
class Loader:
    def __init__(self, project, *, parent=None, provenance_node=None):

        # Ensure we have an absolute path for the base directory
        basedir = project.element_path
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        #
        # Public members
        #
        self.load_context = project.load_context  # The LoadContext
        self.project = project  # The associated Project
        self.provenance_node = provenance_node  # The provenance of whence this loader was instantiated
        self.loaded = None  # The number of loaded Elements

        #
        # Private members
        #
        self._options = project.options  # Project options (OptionPool)
        self._basedir = basedir  # Base project directory
        self._first_pass_options = project.first_pass_config.options  # Project options (OptionPool)
        self._parent = parent  # The parent loader
        self._alternative_parents = []  # Overridden parent loaders

        self._meta_elements = {}  # Dict of resolved meta elements by name
        self._elements = {}  # Dict of elements
        self._links = {}  # Dict of link target target paths indexed by link element paths
        self._loaders = {}  # Dict of junction loaders
        self._loader_search_provenances = {}  # Dictionary of provenance nodes of ongoing child loader searches

        self._includes = Includes(self, copy_tree=True)

        assert project.name is not None

        self.load_context.register_loader(self)

    # The __str__ of a Loader is used to clearly identify the Loader,
    # the junction is was loaded as, and the provenance causing the
    # junction to be loaded.
    #
    def __str__(self):
        project_name = self.project.name

        if self.project.junction:
            junction_name = self.project.junction._get_full_name()
            if self.provenance_node:
                provenance = "({}): {}".format(junction_name, self.provenance_node.get_provenance())
            else:
                provenance = "({})".format(junction_name)
        else:
            provenance = "(toplevel)"

        return "{} {}".format(project_name, provenance)

    # load():
    #
    # Loads the project based on the parameters given to the constructor
    #
    # Args:
    #    targets (list of str): Target, element-path relative bst filenames in the project
    #
    # Raises: LoadError
    #
    # Returns:
    #    (list): The corresponding LoadElement instances matching the `targets`
    #
    def load(self, targets):

        for filename in targets:
            if os.path.isabs(filename):
                # XXX Should this just be an assertion ?
                # Expect that the caller gives us the right thing at least ?
                raise LoadError(
                    "Target '{}' was not specified as a relative "
                    "path to the base project directory: {}".format(filename, self._basedir),
                    LoadErrorReason.INVALID_DATA,
                )

        # First pass, recursively load files and populate our table of LoadElements
        #
        target_elements = []

        for target in targets:
            with PROFILER.profile(Topics.LOAD_PROJECT, target):
                _junction, name, loader = self._parse_name(target, None)
                element = loader._load_file(name, None)
                target_elements.append(element)

        #
        # Now that we've resolved the dependencies, scan them for circular dependencies
        #

        # Set up a dummy element that depends on all top-level targets
        # to resolve potential circular dependencies between them
        dummy_target = LoadElement(Node.from_dict({}), "", self)

        # Pylint is not very happy with Cython and can't understand 'dependencies' is a list
        dummy_target.dependencies.extend(  # pylint: disable=no-member
            Dependency(element, DependencyType.RUNTIME) for element in target_elements
        )

        with PROFILER.profile(Topics.CIRCULAR_CHECK, "_".join(targets)):
            self._check_circular_deps(dummy_target)

        #
        # Sort direct dependencies of elements by their dependency ordering
        #

        # Keep a list of all visited elements, to not sort twice the same
        visited_elements = set()

        for element in target_elements:
            loader = element._loader
            with PROFILER.profile(Topics.SORT_DEPENDENCIES, element.name):
                loadelement.sort_dependencies(element, visited_elements)

        self._clean_caches()

        # Cache how many Elements have just been loaded
        if self.load_context.task:
            self.loaded = self.load_context.task.current_progress

        return target_elements

    # get_loader():
    #
    # Obtains the appropriate loader for the specified junction
    #
    # If `load_subprojects` is enabled, then this function will
    # either return the desired loader or raise a LoadError. If
    # `load_subprojects` is disabled, then it can also return None
    # in the case that a loader could not be found. In either case,
    # a non-existant file in a loaded project will result in a LoadError.
    #
    # Args:
    #   name (str): Name of junction, may have multiple `:` in the name
    #   provenance_node (Node): The provenance from where this loader was requested
    #   load_subprojects (bool): Whether to load subprojects on demand
    #
    # Returns:
    #   (Loader): loader for sub-project
    #
    def get_loader(self, name, provenance_node, *, load_subprojects=True):
        junction_path = name.split(":")
        loader = self

        #
        # In this case we are attempting to load a subproject element via the
        # command line instead of referencing the subproject through a project
        # element or otherwise.
        #
        if provenance_node is None and load_subprojects:
            self.project.ensure_fully_loaded()

        circular_provenance_node = self._loader_search_provenances.get(name, None)
        if circular_provenance_node and load_subprojects:

            assert provenance_node

            detail = None
            if circular_provenance_node is not provenance_node:
                detail = "Already searching for '{}' at: {}".format(name, circular_provenance_node.get_provenance())
            raise LoadError(
                "{}: Circular reference while searching for '{}'".format(provenance_node.get_provenance(), name),
                LoadErrorReason.CIRCULAR_REFERENCE,
                detail=detail,
            )

        if load_subprojects and provenance_node:
            self._loader_search_provenances[name] = provenance_node

        for junction_name in junction_path:
            loader = loader._get_loader(junction_name, provenance_node, load_subprojects=load_subprojects)

        if load_subprojects and provenance_node:
            del self._loader_search_provenances[name]

        return loader

    # ancestors()
    #
    # This will traverse all active loaders in the ancestry for which this
    # project is reachable using a relative path.
    #
    # Yields:
    #     (Loader): Each loader in the ancestry
    #
    def ancestors(self):
        traversed = {}

        def foreach_parent(parent):
            while parent:
                if parent in traversed:
                    return
                traversed[parent] = True
                yield parent
                parent = parent._parent

        # Yield from the direct/active ancestry
        yield from foreach_parent(self._parent)

        # Yield from alternative parents which have been replaced by
        # overrides in the ancestry.
        for parent in self._alternative_parents:
            yield from foreach_parent(parent)

    ###########################################
    #            Private Methods              #
    ###########################################

    # _load_file_no_deps():
    #
    # Load a bst file as a LoadElement
    #
    # This loads a bst file into a LoadElement but does no work to resolve
    # the element's dependencies.  The dependencies must be resolved properly
    # before the LoadElement makes its way out of the loader.
    #
    # Args:
    #    filename (str): The element-path relative bst file
    #    provenance_node (Node): The location from where the file was referred to, or None
    #
    # Returns:
    #    (LoadElement): A partially-loaded LoadElement
    #
    def _load_file_no_deps(self, filename, provenance_node=None):

        self._assert_element_name(filename, provenance_node)

        # Load the data and process any conditional statements therein
        fullpath = os.path.join(self._basedir, filename)
        try:
            node = _yaml.load(
                fullpath, shortname=filename, copy_tree=self.load_context.rewritable, project=self.project
            )
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_FILE:

                if self.project.junction:
                    message = "Could not find element '{}' in project referred to by junction element '{}'".format(
                        filename, self.project.junction.name
                    )
                else:
                    message = "Could not find element '{}' in elements directory '{}'".format(filename, self._basedir)

                if provenance_node:
                    message = "{}: {}".format(provenance_node.get_provenance(), message)

                # If we can't find the file, try to suggest plausible
                # alternatives by stripping the element-path from the given
                # filename, and verifying that it exists.
                detail = None
                elements_dir = os.path.relpath(self._basedir, self.project.directory)
                element_relpath = os.path.relpath(filename, elements_dir)
                if filename.startswith(elements_dir) and os.path.exists(os.path.join(self._basedir, element_relpath)):
                    detail = "Did you mean '{}'?".format(element_relpath)

                raise LoadError(message, LoadErrorReason.MISSING_FILE, detail=detail) from e

            # Otherwise, we don't know the reason, so just raise
            raise

        kind = node.get_str(Symbol.KIND)
        if kind in ("junction", "link"):
            self._first_pass_options.process_node(node)
        else:
            self.project.ensure_fully_loaded()

            self._includes.process(node)

        element = LoadElement(node, filename, self)

        self._elements[filename] = element

        #
        # Update link caches in the ancestry
        #
        if element.link_target is not None:
            link_path = filename
            target_path = element.link_target.as_str()  # pylint: disable=no-member

            # First resolve the link in this loader's cache
            #
            self._resolve_link(link_path, target_path)

            # Now resolve the link in parent project loaders
            #
            loader = self
            while loader._parent:
                junction = loader.project.junction
                link_path = junction.name + ":" + link_path
                target_path = junction.name + ":" + target_path

                # Resolve the link
                loader = loader._parent
                loader._resolve_link(link_path, target_path)

        return element

    # _resolve_link():
    #
    # Resolves a link in the loader's link cache.
    #
    # This will first insert the new link -> target relationship
    # into the cache, and will also update any existing targets
    # which might have pointed to this link, to point to the new
    # target instead.
    #
    # Args:
    #    link_path (str): The local project relative real path to a link
    #    target_path (str): The new target for this link
    #
    def _resolve_link(self, link_path, target_path):
        self._links[link_path] = target_path

        for cached_link_path, cached_target_path in self._links.items():
            if self._expand_link(cached_target_path) == link_path:
                self._links[cached_link_path] = target_path

    # _expand_link():
    #
    # Expands any links in the provided path and returns a real path with
    # known link elements substituted for their targets.
    #
    # Args:
    #    path (str): A project relative path
    #
    # Returns:
    #    (str): The same path with any links expanded
    #
    def _expand_link(self, path):

        # FIXME: This simply returns the first link, maybe
        #        this needs to be more iterative, or sorted by
        #        number of path components, or smth
        for link, target in self._links.items():
            if path.startswith(link):
                return target + path[len(link) :]

        return path

    # _load_one_file():
    #
    # A helper function to load a single file within the _load_file() process,
    # this allows us to handle redirections more consistently.
    #
    # Args:
    #    filename (str): The element-path relative bst file
    #    provenance_node (Node): The location from where the file was referred to, or None
    #    load_subprojects (bool): Whether to load subprojects
    #
    # Returns:
    #    (LoadElement): A LoadElement, which might be shallow loaded or fully loaded.
    #
    def _load_one_file(self, filename, provenance_node, *, load_subprojects=True):

        element = None

        # First check the cache, the cache might contain shallow loaded
        # elements.
        #
        try:
            element = self._elements[filename]

            # If the cached element has already entered the loop which loads
            # it's dependencies, it is fully loaded and any further checks in
            # this function are expected to have already been performed.
            #
            if element.fully_loaded:
                return element

        except KeyError:

            # Shallow load if it's not yet loaded.
            element = self._load_file_no_deps(filename, provenance_node)

        # Check if there was an override for this element
        #
        override = self._search_for_override_element(filename)
        if override:
            #
            # If there was an override for the element, then it was
            # implicitly fully loaded by _search_for_override_element(),
            #
            return override

        # If this element is a link then we need to resolve it, and return
        # the linked element instead of this one.
        #
        if element.link_target is not None:
            link_target = element.link_target.as_str()  # pylint: disable=no-member
            _, filename, loader = self._parse_name(link_target, element.link_target, load_subprojects=load_subprojects)

            #
            # Redirect the loading of the file and it's dependencies to the appropriate loader,
            # which might or might not be the same loader.
            #
            return loader._load_file(filename, element.link_target, load_subprojects=load_subprojects)

        return element

    # _load_file():
    #
    # Semi-Iteratively load bst files
    #
    # The "Semi-" qualification is because where junctions get involved there
    # is a measure of recursion, though this is limited only to the points at
    # which junctions are crossed.
    #
    # Args:
    #    filename (str): The element-path relative bst file
    #    provenance_node (Node): The location from where the file was referred to, or None
    #    load_subprojects (bool): Whether to load subprojects
    #
    # Returns:
    #    (LoadElement): A loaded LoadElement
    #
    def _load_file(self, filename, provenance_node, *, load_subprojects=True):

        top_element = self._load_one_file(filename, provenance_node, load_subprojects=load_subprojects)

        # Already loaded dependencies for a fully loaded element, early return.
        #
        if top_element.fully_loaded:
            return top_element

        #
        # Mark the top element here as "fully loaded", so that we will avoid trying to
        # load it's dependencies more than once.
        #
        top_element.mark_fully_loaded()

        dependencies = extract_depends_from_node(top_element.node)
        # The loader queue is a stack of tuples
        # [0] is the LoadElement instance
        # [1] is a stack of Dependency objects to load
        # [2] is a list of dependency names used to warn when all deps are loaded
        loader_queue = [(top_element, list(reversed(dependencies)), [])]

        # Load all dependency files for the new LoadElement
        while loader_queue:
            if loader_queue[-1][1]:
                current_element = loader_queue[-1]

                # Process the first dependency of the last loaded element
                dep = current_element[1].pop()
                # And record its name for checking later
                current_element[2].append(dep.name)

                if dep.junction:
                    loader = self.get_loader(dep.junction, dep.node)
                    dep_element = loader._load_file(dep.name, dep.node)

                else:

                    dep_element = self._load_one_file(dep.name, dep.node, load_subprojects=load_subprojects)

                    # If the loaded element is not fully loaded, queue up the dependencies to be loaded in this loop.
                    #
                    if not dep_element.fully_loaded:

                        # Mark the dep_element as fully_loaded, as we're already queueing it's deps
                        dep_element.mark_fully_loaded()

                        dep_deps = extract_depends_from_node(dep_element.node)
                        loader_queue.append((dep_element, list(reversed(dep_deps)), []))

                        # Pylint is not very happy about Cython and can't understand 'node' is a 'MappingNode'
                        if dep_element.node.get_str(Symbol.KIND) == "junction":  # pylint: disable=no-member
                            raise LoadError(
                                "{}: Cannot depend on junction".format(dep.node.get_provenance()),
                                LoadErrorReason.INVALID_DATA,
                            )

                # We've now resolved the element for this dependency, lets set the resolved
                # LoadElement on the dependency and append the dependency to the owning
                # LoadElement dependency list.
                dep.set_element(dep_element)
                current_element[0].dependencies.append(dep)  # pylint: disable=no-member
            else:
                # And pop the element off the queue
                loader_queue.pop()

        # Nothing more in the queue, return the top level element we loaded.
        return top_element

    # _check_circular_deps():
    #
    # Detect circular dependencies on LoadElements with
    # dependencies already resolved.
    #
    # Args:
    #    element (str): The element to check
    #
    # Raises:
    #    (LoadError): In case there was a circular dependency error
    #
    @staticmethod
    def _check_circular_deps(top_element):

        sequence = [top_element]
        sequence_indices = [0]
        check_elements = set(sequence)
        validated = set()

        while sequence:
            this_element = sequence[-1]
            index = sequence_indices[-1]
            if index < len(this_element.dependencies):
                element = this_element.dependencies[index].element
                sequence_indices[-1] = index + 1
                if element in check_elements:
                    # Create `chain`, the loop of element dependencies from this
                    # element back to itself, by trimming everything before this
                    # element from the sequence under consideration.
                    chain = [element.full_name for element in sequence[sequence.index(element) :]]
                    chain.append(element.full_name)
                    raise LoadError(
                        ("Circular dependency detected at element: {}\n" + "Dependency chain: {}").format(
                            element.full_name, " -> ".join(chain)
                        ),
                        LoadErrorReason.CIRCULAR_DEPENDENCY,
                    )
                if element not in validated:
                    # We've not already validated this element, so let's
                    # descend into it to check it out
                    sequence.append(element)
                    sequence_indices.append(0)
                    check_elements.add(element)
                # Otherwise we'll head back around the loop to validate the
                # next dependency in this entry
            else:
                # Done with entry, pop it off, indicate we're no longer
                # in its chain, and mark it valid
                sequence.pop()
                sequence_indices.pop()
                check_elements.remove(this_element)
                validated.add(this_element)

    # _search_for_local_override():
    #
    # Search this project's active override list for an override, while
    # considering any link elements.
    #
    # Args:
    #    override_path (str): The real relative path to search for
    #
    # Returns:
    #    (ScalarNode): The overridding node from this project's junction, or None
    #
    def _search_for_local_override(self, override_path):
        junction = self.project.junction
        if junction is None:
            return None

        # Try the override without any link substitutions first
        with suppress(KeyError):
            return junction.overrides[override_path]

        #
        # If we did not get an exact match here, we might still have
        # an override where a link was used to specify the override.
        #
        for override_key, override_node in junction.overrides.items():
            resolved_path = self._expand_link(override_key)
            if resolved_path == override_path:
                return override_node

        return None

    # _search_for_overrides():
    #
    # Search for parent loaders which have an override for the specified element,
    # returning a list of loaders with the highest level overriding loader at the
    # end of the list, and the closest ancestor being at the beginning of the list.
    #
    # Args:
    #    filename (str): The local element name
    #
    # Returns:
    #    (list): A list of loaders which override this element
    #
    def _search_for_overrides(self, filename):
        loader = self
        override_path = filename

        # Collect any overrides to this junction in the ancestry
        #
        overriding_loaders = []
        while loader._parent:
            junction = loader.project.junction
            override_node = loader._search_for_local_override(override_path)
            if override_node:
                overriding_loaders.append((loader._parent, override_node))

            override_path = junction.name + ":" + override_path
            loader = loader._parent

        return overriding_loaders

    # _search_for_override_loader():
    #
    # Search parent projects an override of the junction specified by @filename,
    # returning the loader object which should be used in place of the local
    # junction specified by @filename.
    #
    # This function is called once for each direct child while looking up
    # child loaders, after which point the child loader is cached in the `_loaders`
    # table. This function also has the side effect of recording alternative parents
    # of a child loader in the case that the child loader is overridden.
    #
    # Args:
    #    filename (str): Junction name
    #
    # Returns:
    #    (Loader): The loader to use, in case @filename was overridden, otherwise None.
    #
    def _search_for_override_loader(self, filename):

        overriding_loaders = self._search_for_overrides(filename)

        # If there are any overriding loaders, use the highest one in
        # the ancestry to lookup the loader for this project.
        #
        if overriding_loaders:
            overriding_loader, override_node = overriding_loaders[-1]
            loader = overriding_loader.get_loader(override_node.as_str(), override_node)

            #
            # Record alternative loaders which were overridden.
            #
            # When a junction is overridden by another higher priority junction,
            # the resulting loader is still reachable with the original element paths,
            # which will now traverse override redirections.
            #
            # In order to iterate over every project/loader in the ancestry which can
            # reach the actually selected loader, we need to keep track of the parent
            # loaders of all overridden junctions.
            #
            if loader is not self:
                loader._alternative_parents.append(self)

            del overriding_loaders[-1]
            loader._alternative_parents.extend(l for l, _ in overriding_loaders)

            return loader

        # No overrides were found in the ancestry
        #
        return None

    # _search_for_override_element():
    #
    # Search parent projects an override of the element specified by @filename,
    # returning the loader object which should be used in place of the local
    # element specified by @filename.
    #
    # Args:
    #    filename (str): Junction name
    #
    # Returns:
    #    (Loader): The loader to use, in case @filename was overridden, otherwise None.
    #
    def _search_for_override_element(self, filename):
        element = None

        # If there are any overriding loaders, use the highest one in
        # the ancestry to lookup the element which should be used in place
        # of @filename.
        #
        overriding_loaders = self._search_for_overrides(filename)
        if overriding_loaders:
            overriding_loader, override_node = overriding_loaders[-1]

            _, filename, loader = overriding_loader._parse_name(override_node.as_str(), override_node)
            element = loader._load_file(filename, override_node)

        return element

    # _get_loader():
    #
    # Return loader for specified junction
    #
    # Args:
    #    filename (str): Junction name
    #    load_subprojects (bool): Whether to load subprojects
    #    provenance_node (Node): The location from where the file was referred to, or None
    #
    # Raises: LoadError
    #
    # Returns: A Loader or None if specified junction does not exist
    #
    def _get_loader(self, filename, provenance_node, *, load_subprojects=True):
        loader = None

        # return previously determined result
        if filename in self._loaders:
            return self._loaders[filename]

        # Local function to conditionally resolve the provenance prefix string
        def provenance_str():
            if provenance_node is not None:
                return "{}: ".format(provenance_node.get_provenance())
            return ""

        #
        # Search the ancestry for an overridden loader to use in place
        # of using the locally defined junction.
        #
        override_loader = self._search_for_override_loader(filename)
        if override_loader:
            self._loaders[filename] = override_loader
            return override_loader

        #
        # Load the junction file
        #
        self._load_file(filename, provenance_node, load_subprojects=load_subprojects)

        # At this point we've loaded the LoadElement
        load_element = self._elements[filename]

        # If the loaded element is a link, then just follow it
        # immediately and move on to the target.
        #
        if load_element.link_target:
            _, filename, loader = self._parse_name(
                load_element.link_target.as_str(), load_element.link_target, load_subprojects=load_subprojects
            )
            return loader.get_loader(filename, load_element.link_target, load_subprojects=load_subprojects)

        # If we're only performing a lookup, we're done here.
        #
        if not load_subprojects:
            return None

        if load_element.kind != "junction":
            raise LoadError(
                "{}{}: Expected junction but element kind is {}".format(provenance_str(), filename, load_element.kind),
                LoadErrorReason.INVALID_DATA,
            )

        # We check that junctions have no dependencies a little
        # early. This is cheating, since we don't technically know
        # that junctions aren't allowed to have dependencies.
        #
        # However, this makes progress reporting more intuitive
        # because we don't need to load dependencies of an element
        # that shouldn't have any, and therefore don't need to
        # duplicate the load count for elements that shouldn't be.
        #
        # We also fail slightly earlier (since we don't need to go
        # through the entire loading process), which is nice UX. It
        # would be nice if this could be done for *all* element types,
        # but since we haven't loaded those yet that's impossible.
        if load_element.dependencies:
            # Use the first dependency in the list as provenance
            p = load_element.dependencies[0].node.get_provenance()
            raise LoadError(
                "{}: Dependencies are forbidden for 'junction' elements".format(p), LoadErrorReason.INVALID_JUNCTION
            )

        element = Element._new_from_load_element(load_element)

        # Handle the case where a subproject has no ref
        #
        if not element._has_all_sources_resolved():
            detail = "Try tracking the junction element with `bst source track {}`".format(filename)
            raise LoadError(
                "{}Subproject has no ref for junction: {}".format(provenance_str(), filename),
                LoadErrorReason.SUBPROJECT_INCONSISTENT,
                detail=detail,
            )

        # Handle the case where a subproject needs to be fetched
        #
        element._query_source_cache()
        if element._should_fetch():
            self.load_context.fetch_subprojects([element])

        sources = list(element.sources())
        if len(sources) == 1 and sources[0]._get_local_path():
            # Optimization for junctions with a single local source
            basedir = sources[0]._get_local_path()
        else:
            # Stage sources
            element._set_required()

            # Note: We use _KeyStrength.WEAK here because junctions
            # cannot have dependencies, therefore the keys are
            # equivalent.
            #
            # Since the element has not necessarily been given a
            # strong cache key at this point (in a non-strict build
            # that is set *after* we complete building/pulling, which
            # we haven't yet for this element),
            # element._get_cache_key() can fail if used with the
            # default _KeyStrength.STRONG.
            basedir = os.path.join(
                self.project.directory, ".bst", "staged-junctions", filename, element._get_cache_key(_KeyStrength.WEAK)
            )
            if not os.path.exists(basedir):
                os.makedirs(basedir, exist_ok=True)
                element._stage_sources_at(basedir)

        # Load the project
        project_dir = os.path.join(basedir, element.path)
        try:
            from .._project import Project  # pylint: disable=cyclic-import

            project = Project(
                project_dir,
                self.load_context.context,
                junction=element,
                parent_loader=self,
                search_for_project=False,
                provenance_node=provenance_node,
            )
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_PROJECT_CONF:
                message = (
                    provenance_str() + "Could not find the project.conf file in the project "
                    "referred to by junction element '{}'.".format(element.name)
                )
                if element.path:
                    message += " Was expecting it at path '{}' in the junction's source.".format(element.path)
                raise LoadError(message=message, reason=LoadErrorReason.INVALID_JUNCTION) from e

            # Otherwise, we don't know the reason, so just raise
            raise

        loader = project.loader
        self._loaders[filename] = loader

        # Now we've loaded a junction and it's project, we need to try to shallow
        # load the overrides of this project and any projects in the ancestry which
        # have overrides referring to this freshly loaded project.
        #
        # This is to ensure that link elements have been resolved as much as possible
        # before we try to look for an override.
        #
        iter_loader = loader
        while iter_loader._parent:
            iter_loader._shallow_load_overrides()
            iter_loader = iter_loader._parent

        return loader

    # _shallow_load_overrides():
    #
    # Loads any of the override elements on this loader's junction
    #
    def _shallow_load_overrides(self):
        if not self.project.junction:
            return

        junction = self.project.junction

        # Iterate over the keys, we want to ensure that links are resolved for
        # override paths specified in junctions, while the targets of these paths
        # are not consequential.
        #
        for override_path, override_target in junction.overrides.items():

            # Ensure that we resolve indirect links, in case that shallow loading
            # an element results in loading a link, we need to discover if it's
            # target is also a link.
            #
            path = override_path
            provenance_node = override_target
            while path is not None:
                path, provenance_node = self._shallow_load_path(path, provenance_node)

    # _shallow_load_path()
    #
    # Perform a shallow load of an element by it's relative path, this is
    # used to load elements which might be specified by their path and might
    # not be used in the resulting load, like paths to elements overridden by
    # junctions.
    #
    # It is only important to shallow load these referenced elements in case
    # they are links which need to be known later on.
    #
    # Args:
    #    path (str): The path to load
    #    provenance_node (Node): The node to use for provenance
    #
    # Returns:
    #    (str): The target of the loaded link element, if it was a link element
    #           and it could be loaded presently, otherwise None.
    #    (ScalarNode): The link target real node, if a link target was returned
    #
    def _shallow_load_path(self, path, provenance_node):
        if ":" in path:
            junction, element_name = path.rsplit(":", 1)
            target_loader = self.get_loader(junction, provenance_node, load_subprojects=False)

            # Subproject not loaded, discard this shallow load attempt
            #
            if target_loader is None:
                return None, None
        else:
            junction = None
            element_name = path
            target_loader = self

        # If the element is already loaded in the target loader, then there
        # is no need for a shallow load.
        try:
            element = target_loader._elements[element_name]
        except KeyError:
            # Shallow load the the element.
            element = target_loader._load_file_no_deps(element_name, provenance_node)

        if element.link_target:
            link_target = element.link_target.as_str()
            if junction:
                return "{}:{}".format(junction, link_target), element.link_target

            return link_target, element.link_target

        return None, None

    # _parse_name():
    #
    # Get junction and base name of element along with loader for the sub-project
    #
    # Args:
    #   name (str): Name of target
    #   provenance_node (Node): The provenance node
    #   load_subprojects (bool): Whether to load subprojects
    #
    # Returns:
    #   (tuple): - (str): name of the junction element
    #            - (str): name of the element
    #            - (Loader): loader for sub-project
    #
    def _parse_name(self, name, provenance_node, *, load_subprojects=True):
        # We allow to split only once since deep junctions names are forbidden.
        # Users who want to refer to elements in sub-sub-projects are required
        # to create junctions on the top level project.
        junction_path = name.rsplit(":", 1)
        if len(junction_path) == 1:
            return None, junction_path[-1], self
        else:
            loader = self.get_loader(junction_path[-2], provenance_node, load_subprojects=load_subprojects)
            return junction_path[-2], junction_path[-1], loader

    # _warn():
    #
    # Print a warning message, checks warning_token against project configuration
    #
    # Args:
    #     brief (str): The brief message
    #     warning_token (str): An optional configurable warning assosciated with this warning,
    #                          this will cause PluginError to be raised if this warning is configured as fatal.
    #
    # Raises:
    #     (:class:`.LoadError`): When warning_token is considered fatal by the project configuration
    #
    def _warn(self, brief, *, warning_token=None):
        if warning_token:
            if self.project._warning_is_fatal(warning_token):
                raise LoadError(brief, warning_token)

        self.load_context.context.messenger.warn(brief)

    # _assert_element_name():
    #
    # Raises an error if any of the specified elements have invalid names.
    #
    # Valid filenames should end with ".bst" extension.
    #
    # Args:
    #    filename (str): The element name
    #    provenance_node (Node): The provenance node, or None
    #
    # Raises:
    #     (:class:`.LoadError`): If the element name is invalid
    #
    def _assert_element_name(self, filename, provenance_node):
        error_message = None
        error_reason = None

        if not filename.endswith(".bst"):
            error_message = "Element '{}' does not have expected file extension `.bst`".format(filename)
            error_reason = LoadErrorReason.BAD_ELEMENT_SUFFIX
        elif not valid_chars_name(filename):
            error_message = "Element '{}' has invalid characters.".format(filename)
            error_reason = LoadErrorReason.BAD_CHARACTERS_IN_NAME

        if error_message:
            if provenance_node is not None:
                error_message = "{}: {}".format(provenance_node.get_provenance(), error_message)
            raise LoadError(error_message, error_reason)

    # _clean_caches()
    #
    # Clean internal loader caches, recursively
    #
    # When loading the elements, the loaders use caches in order to not load the
    # same element twice. These are kept after loading and prevent garbage
    # collection. Cleaning them explicitely is required.
    #
    def _clean_caches(self):
        for loader in self._loaders.values():
            # value may be None with nested junctions without overrides
            if loader is not None:
                loader._clean_caches()

        self._meta_elements = {}
        self._elements = {}
