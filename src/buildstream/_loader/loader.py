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
from contextlib import suppress

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from .. import _yaml
from ..element import Element
from ..node import Node
from .._profile import Topics, PROFILER
from .._includes import Includes

from ._loader import valid_chars_name
from .types import Symbol
from . import loadelement
from .loadelement import LoadElement, Dependency, extract_depends_from_node
from ..types import CoreWarnings, _KeyStrength
from .._message import Message, MessageType


# Loader():
#
# The Loader class does the heavy lifting of parsing target
# bst files and ultimately transforming them into a list of LoadElements
# ready for instantiation by the core.
#
# Args:
#    project (Project): The toplevel Project object
#    parent (Loader): A parent Loader object, in the case this is a junctioned Loader
#    provenance (ProvenanceInformation): The provenance of the reference to this project's junction
#
class Loader:
    def __init__(self, project, *, parent=None, provenance=None):

        # Ensure we have an absolute path for the base directory
        basedir = project.element_path
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        #
        # Public members
        #
        self.load_context = project.load_context  # The LoadContext
        self.project = project  # The associated Project
        self.provenance = provenance  # The provenance of whence this loader was instantiated
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
        self._loaders = {}  # Dict of junction loaders
        self._loader_search_provenances = {}  # Dictionary of provenances of ongoing child loader searches

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
            if self.provenance:
                provenance = "({}): {}".format(junction_name, self.provenance)
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

        self._warn_invalid_elements(targets)

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
            Dependency(element, Symbol.RUNTIME) for element in target_elements
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
    #   provenance (ProvenanceInformation): The provenance
    #   load_subprojects (bool): Whether to load subprojects on demand
    #
    # Returns:
    #   (Loader): loader for sub-project
    #
    def get_loader(self, name, provenance, *, load_subprojects=True):
        junction_path = name.split(":")
        loader = self

        circular_provenance = self._loader_search_provenances.get(name, None)
        if circular_provenance:

            assert provenance

            detail = None
            if circular_provenance is not provenance:
                detail = "Already searching for '{}' at: {}".format(name, circular_provenance)
            raise LoadError(
                "{}: Circular reference while searching for '{}'".format(provenance, name),
                LoadErrorReason.CIRCULAR_REFERENCE,
                detail=detail,
            )

        self._loader_search_provenances[name] = provenance

        for junction_name in junction_path:
            loader = loader._get_loader(junction_name, provenance, load_subprojects=load_subprojects)

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
    #    provenance (Provenance): The location from where the file was referred to, or None
    #
    # Returns:
    #    (LoadElement): A partially-loaded LoadElement
    #
    def _load_file_no_deps(self, filename, provenance=None):
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

                if provenance:
                    message = "{}: {}".format(provenance, message)

                # If we can't find the file, try to suggest plausible
                # alternatives by stripping the element-path from the given
                # filename, and verifying that it exists.
                detail = None
                elements_dir = os.path.relpath(self._basedir, self.project.directory)
                element_relpath = os.path.relpath(filename, elements_dir)
                if filename.startswith(elements_dir) and os.path.exists(os.path.join(self._basedir, element_relpath)):
                    detail = "Did you mean '{}'?".format(element_relpath)

                raise LoadError(message, LoadErrorReason.MISSING_FILE, detail=detail) from e

            if e.reason == LoadErrorReason.LOADING_DIRECTORY:
                # If a <directory>.bst file exists in the element path,
                # let's suggest this as a plausible alternative.
                message = str(e)
                if provenance:
                    message = "{}: {}".format(provenance, message)
                detail = None
                if os.path.exists(os.path.join(self._basedir, filename + ".bst")):
                    element_name = filename + ".bst"
                    detail = "Did you mean '{}'?\n".format(element_name)
                raise LoadError(message, LoadErrorReason.LOADING_DIRECTORY, detail=detail) from e

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
    #    load_subprojects (bool): Whether to load subprojects
    #    provenance (Provenance): The location from where the file was referred to, or None
    #
    # Returns:
    #    (LoadElement): A loaded LoadElement
    #
    def _load_file(self, filename, provenance, *, load_subprojects=True):

        # Silently ignore already loaded files
        with suppress(KeyError):
            return self._elements[filename]

        top_element = self._load_file_no_deps(filename, provenance)

        # If this element is a link then we need to resolve it
        # and replace the dependency we've processed with this one
        if top_element.link_target is not None:
            _, filename, loader = self._parse_name(
                top_element.link_target, top_element.link_target_provenance, load_subprojects=load_subprojects
            )
            top_element = loader._load_file(
                filename, top_element.link_target_provenance, load_subprojects=load_subprojects
            )

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
                    loader = self.get_loader(dep.junction, dep.provenance)
                    dep_element = loader._load_file(dep.name, dep.provenance)
                else:
                    dep_element = self._elements.get(dep.name)

                    if dep_element is None:
                        # The loader does not have this available so we need to
                        # either recursively cause it to be loaded, or else we
                        # need to push this onto the loader queue in this loader
                        dep_element = self._load_file_no_deps(dep.name, dep.provenance)
                        dep_deps = extract_depends_from_node(dep_element.node)
                        loader_queue.append((dep_element, list(reversed(dep_deps)), []))

                        # Pylint is not very happy about Cython and can't understand 'node' is a 'MappingNode'
                        if dep_element.node.get_str(Symbol.KIND) == "junction":  # pylint: disable=no-member
                            raise LoadError(
                                "{}: Cannot depend on junction".format(dep.provenance), LoadErrorReason.INVALID_DATA
                            )

                # If this dependency is a link then we need to resolve it
                # and replace the dependency we've processed with this one
                if dep_element.link_target:
                    _, filename, loader = self._parse_name(dep_element.link_target, dep_element.link_target_provenance)
                    dep_element = loader._load_file(filename, dep_element.link_target_provenance)

                # We've now resolved the element for this dependency, lets set the resolved
                # LoadElement on the dependency and append the dependency to the owning
                # LoadElement dependency list.
                dep.set_element(dep_element)
                current_element[0].dependencies.append(dep)
            else:
                # We do not have any more dependencies to load for this
                # element on the queue, report any invalid dep names
                self._warn_invalid_elements(loader_queue[-1][2])
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

    # _search_for_override():
    #
    # Search parent projects for an overridden subproject to replace this junction.
    #
    # This function is called once for each direct child while looking up
    # child loaders, after which point the child loader is cached in the `_loaders`
    # table. This function also has the side effect of recording alternative parents
    # of a child loader in the case that the child loader is overridden.
    #
    # Args:
    #    filename (str): Junction name
    #
    def _search_for_override(self, filename):
        loader = self
        override_path = filename

        # Collect any overrides to this junction in the ancestry
        #
        overriding_loaders = []
        while loader._parent:
            junction = loader.project.junction
            override_filename, override_provenance = junction.overrides.get(override_path, (None, None))
            if override_filename:
                overriding_loaders.append((loader._parent, override_filename, override_provenance))

            override_path = junction.name + ":" + override_path
            loader = loader._parent

        # If there are any overriding loaders, use the highest one in
        # the ancestry to lookup the loader for this project.
        #
        if overriding_loaders:
            overriding_loader, override_filename, provenance = overriding_loaders[-1]
            loader = overriding_loader.get_loader(override_filename, provenance)

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
            loader._alternative_parents.extend(l for l, _, _ in overriding_loaders)

            return loader

        # No overrides were found in the ancestry
        #
        return None

    # _get_loader():
    #
    # Return loader for specified junction
    #
    # Args:
    #    filename (str): Junction name
    #    load_subprojects (bool): Whether to load subprojects
    #    provenance (Provenance): The location from where the file was referred to, or None
    #
    # Raises: LoadError
    #
    # Returns: A Loader or None if specified junction does not exist
    #
    def _get_loader(self, filename, provenance, *, load_subprojects=True):
        loader = None
        provenance_str = ""
        if provenance is not None:
            provenance_str = "{}: ".format(provenance)

        # return previously determined result
        if filename in self._loaders:
            return self._loaders[filename]

        #
        # Search the ancestry for an overridden loader to use in place
        # of using the locally defined junction.
        #
        override_loader = self._search_for_override(filename)
        if override_loader:
            self._loaders[filename] = override_loader
            return override_loader

        #
        # Load the junction file
        #
        self._load_file(filename, provenance, load_subprojects=load_subprojects)

        # At this point we've loaded the LoadElement
        load_element = self._elements[filename]

        # If the loaded element is a link, then just follow it
        # immediately and move on to the target.
        #
        if load_element.link_target:
            _, filename, loader = self._parse_name(
                load_element.link_target, load_element.link_target_provenance, load_subprojects=load_subprojects
            )
            return loader.get_loader(filename, load_element.link_target_provenance, load_subprojects=load_subprojects)

        # If we're only performing a lookup, we're done here.
        #
        if not load_subprojects:
            return None

        if load_element.kind != "junction":
            raise LoadError(
                "{}{}: Expected junction but element kind is {}".format(provenance_str, filename, load_element.kind),
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
            p = load_element.dependencies[0].provenance
            raise LoadError(
                "{}: Dependencies are forbidden for 'junction' elements".format(p), LoadErrorReason.INVALID_JUNCTION
            )

        element = Element._new_from_load_element(load_element)
        element._initialize_state()

        # Handle the case where a subproject has no ref
        #
        if not element._has_all_sources_resolved():
            detail = "Try tracking the junction element with `bst source track {}`".format(filename)
            raise LoadError(
                "{}Subproject has no ref for junction: {}".format(provenance_str, filename),
                LoadErrorReason.SUBPROJECT_INCONSISTENT,
                detail=detail,
            )

        # Handle the case where a subproject needs to be fetched
        #
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
                provenance=provenance,
            )
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_PROJECT_CONF:
                message = (
                    provenance_str + "Could not find the project.conf file in the project "
                    "referred to by junction element '{}'.".format(element.name)
                )
                if element.path:
                    message += " Was expecting it at path '{}' in the junction's source.".format(element.path)
                raise LoadError(message=message, reason=LoadErrorReason.INVALID_JUNCTION) from e

            # Otherwise, we don't know the reason, so just raise
            raise

        loader = project.loader
        self._loaders[filename] = loader

        return loader

    # _parse_name():
    #
    # Get junction and base name of element along with loader for the sub-project
    #
    # Args:
    #   name (str): Name of target
    #   provenance (ProvenanceInformation): The provenance
    #   load_subprojects (bool): Whether to load subprojects
    #
    # Returns:
    #   (tuple): - (str): name of the junction element
    #            - (str): name of the element
    #            - (Loader): loader for sub-project
    #
    def _parse_name(self, name, provenance, *, load_subprojects=True):
        # We allow to split only once since deep junctions names are forbidden.
        # Users who want to refer to elements in sub-sub-projects are required
        # to create junctions on the top level project.
        junction_path = name.rsplit(":", 1)
        if len(junction_path) == 1:
            return None, junction_path[-1], self
        else:
            loader = self.get_loader(junction_path[-2], provenance, load_subprojects=load_subprojects)
            return junction_path[-2], junction_path[-1], loader

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

        message = Message(MessageType.WARN, brief)
        self.load_context.context.messenger.message(message)

    # Print warning messages if any of the specified elements have invalid names.
    #
    # Valid filenames should end with ".bst" extension.
    #
    # Args:
    #    elements (list): List of element names
    #
    # Raises:
    #     (:class:`.LoadError`): When warning_token is considered fatal by the project configuration
    #
    def _warn_invalid_elements(self, elements):

        # invalid_elements
        #
        # A dict that maps warning types to the matching elements.
        invalid_elements = {
            CoreWarnings.BAD_ELEMENT_SUFFIX: [],
            CoreWarnings.BAD_CHARACTERS_IN_NAME: [],
        }

        for filename in elements:
            if not filename.endswith(".bst"):
                invalid_elements[CoreWarnings.BAD_ELEMENT_SUFFIX].append(filename)
            if not valid_chars_name(filename):
                invalid_elements[CoreWarnings.BAD_CHARACTERS_IN_NAME].append(filename)

        if invalid_elements[CoreWarnings.BAD_ELEMENT_SUFFIX]:
            self._warn(
                "Target elements '{}' do not have expected file extension `.bst` "
                "Improperly named elements will not be discoverable by commands".format(
                    invalid_elements[CoreWarnings.BAD_ELEMENT_SUFFIX]
                ),
                warning_token=CoreWarnings.BAD_ELEMENT_SUFFIX,
            )
        if invalid_elements[CoreWarnings.BAD_CHARACTERS_IN_NAME]:
            self._warn(
                "Target elements '{}' have invalid characerts in their name.".format(
                    invalid_elements[CoreWarnings.BAD_CHARACTERS_IN_NAME]
                ),
                warning_token=CoreWarnings.BAD_CHARACTERS_IN_NAME,
            )

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
