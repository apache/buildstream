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

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from .. import _yaml
from ..element import Element
from ..node import Node
from .._profile import Topics, PROFILER
from .._includes import Includes

from ._loader import valid_chars_name
from .types import Symbol, extract_depends_from_node
from . import loadelement
from .loadelement import Dependency, LoadElement
from .metaelement import MetaElement
from .metasource import MetaSource
from ..types import CoreWarnings, _KeyStrength
from .._message import Message, MessageType


# This should be used to deliberately disable progress reporting when
# collecting an element
_NO_PROGRESS = object()


# Loader():
#
# The Loader class does the heavy lifting of parsing target
# bst files and ultimately transforming them into a list of MetaElements
# with their own MetaSources, ready for instantiation by the core.
#
# Args:
#    context (Context): The Context object
#    project (Project): The toplevel Project object
#    fetch_subprojects (callable): A function to fetch subprojects
#    parent (Loader): A parent Loader object, in the case this is a junctioned Loader
#
class Loader:
    def __init__(self, context, project, *, fetch_subprojects, parent=None):

        # Ensure we have an absolute path for the base directory
        basedir = project.element_path
        if not os.path.isabs(basedir):
            basedir = os.path.abspath(basedir)

        #
        # Public members
        #
        self.project = project  # The associated Project
        self.loaded = None  # The number of loaded Elements

        #
        # Private members
        #
        self._context = context
        self._options = project.options  # Project options (OptionPool)
        self._basedir = basedir  # Base project directory
        self._first_pass_options = project.first_pass_config.options  # Project options (OptionPool)
        self._parent = parent  # The parent loader
        self._fetch_subprojects = fetch_subprojects

        self._meta_elements = {}  # Dict of resolved meta elements by name
        self._elements = {}  # Dict of elements
        self._loaders = {}  # Dict of junction loaders

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
    #    task (Task): A task object to report progress to
    #
    # Raises: LoadError
    #
    # Returns: The toplevel LoadElement
    def load(self, targets, task, rewritable=False, ticker=None):

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
                _junction, name, loader = self._parse_name(target, rewritable, ticker)
                element = loader._load_file(name, rewritable, ticker)
                target_elements.append(element)

        #
        # Now that we've resolved the dependencies, scan them for circular dependencies
        #

        # Set up a dummy element that depends on all top-level targets
        # to resolve potential circular dependencies between them
        dummy_target = LoadElement(Node.from_dict({}), "", self)
        # Pylint is not very happy with Cython and can't understand 'dependencies' is a list
        dummy_target.dependencies.extend(  # pylint: disable=no-member
            Dependency(element, Symbol.RUNTIME, False) for element in target_elements
        )

        with PROFILER.profile(Topics.CIRCULAR_CHECK, "_".join(targets)):
            self._check_circular_deps(dummy_target)

        ret = []
        #
        # Sort direct dependencies of elements by their dependency ordering
        #

        # Keep a list of all visited elements, to not sort twice the same
        visited_elements = set()

        for element in target_elements:
            loader = element._loader
            with PROFILER.profile(Topics.SORT_DEPENDENCIES, element.name):
                loadelement.sort_dependencies(element, visited_elements)

            # Finally, wrap what we have into LoadElements and return the target
            #
            ret.append(loader._collect_element(element, task))

        self._clean_caches()

        # Cache how many Elements have just been loaded
        if task is not _NO_PROGRESS:
            # Workaround for task potentially being None (because no State object)
            self.loaded = task.current_progress

        return ret

    # get_state_for_child_job_pickling(self)
    #
    # Return data necessary to reconstruct this object in a child job process.
    #
    # This should be implemented the same as __getstate__(). We define this
    # method instead as it is child job specific.
    #
    # Returns:
    #    (dict): This `state` is what we want `self.__dict__` to be restored to
    #    after instantiation in the child process.
    #
    def get_state_for_child_job_pickling(self):
        state = self.__dict__.copy()

        # When pickling a Loader over to the ChildJob, we don't want to bring
        # the whole Stream over with it. The _fetch_subprojects member is a
        # method of the Stream. We also don't want to remove it in the main
        # process. If we remove it in the child process then we will already be
        # too late. The only time that seems just right is here, when preparing
        # the child process' copy of the Loader.
        #
        del state["_fetch_subprojects"]

        # Also there's no gain in pickling over the caches, and they might
        # contain things which are unpleasantly large or unable to pickle.
        del state["_elements"]
        del state["_meta_elements"]

        return state

    # clean_caches()
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
    #    rewritable (bool): Whether we should load in round trippable mode
    #    provenance (Provenance): The location from where the file was referred to, or None
    #
    # Returns:
    #    (LoadElement): A partially-loaded LoadElement
    #
    def _load_file_no_deps(self, filename, rewritable, provenance=None):
        # Load the data and process any conditional statements therein
        fullpath = os.path.join(self._basedir, filename)
        try:
            node = _yaml.load(fullpath, shortname=filename, copy_tree=rewritable, project=self.project)
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
        if kind == "junction":
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
    #    rewritable (bool): Whether we should load in round trippable mode
    #    ticker (callable): A callback to report loaded filenames to the frontend
    #    provenance (Provenance): The location from where the file was referred to, or None
    #
    # Returns:
    #    (LoadElement): A loaded LoadElement
    #
    def _load_file(self, filename, rewritable, ticker, provenance=None):

        # Silently ignore already loaded files
        if filename in self._elements:
            return self._elements[filename]

        # Call the ticker
        if ticker:
            ticker(filename)

        top_element = self._load_file_no_deps(filename, rewritable, provenance)
        dependencies = extract_depends_from_node(top_element.node)
        # The loader queue is a stack of tuples
        # [0] is the LoadElement instance
        # [1] is a stack of dependencies to load
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
                    self._load_file(dep.junction, rewritable, ticker, dep.provenance)
                    loader = self._get_loader(
                        dep.junction, rewritable=rewritable, ticker=ticker, provenance=dep.provenance
                    )
                    dep_element = loader._load_file(dep.name, rewritable, ticker, dep.provenance)
                else:
                    dep_element = self._elements.get(dep.name)

                    if dep_element is None:
                        # The loader does not have this available so we need to
                        # either recursively cause it to be loaded, or else we
                        # need to push this onto the loader queue in this loader
                        dep_element = self._load_file_no_deps(dep.name, rewritable, dep.provenance)
                        dep_deps = extract_depends_from_node(dep_element.node)
                        loader_queue.append((dep_element, list(reversed(dep_deps)), []))

                        # Pylint is not very happy about Cython and can't understand 'node' is a 'MappingNode'
                        if dep_element.node.get_str(Symbol.KIND) == "junction":  # pylint: disable=no-member
                            raise LoadError(
                                "{}: Cannot depend on junction".format(dep.provenance), LoadErrorReason.INVALID_DATA
                            )

                # All is well, push the dependency onto the LoadElement
                # Pylint is not very happy with Cython and can't understand 'dependencies' is a list
                current_element[0].dependencies.append(  # pylint: disable=no-member
                    Dependency(dep_element, dep.dep_type, dep.strict)
                )
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

    # _collect_element_no_deps()
    #
    # Collect a single element, without its dependencies, into a meta_element
    #
    # Args:
    #    element (LoadElement): The element for which to load a MetaElement
    #    task (Task): A task to write progress information to
    #
    # Returns:
    #    (MetaElement): A partially loaded MetaElement
    #
    def _collect_element_no_deps(self, element, task):
        # Return the already built one, if we already built it
        meta_element = self._meta_elements.get(element.name)
        if meta_element:
            return meta_element

        node = element.node
        elt_provenance = node.get_provenance()
        meta_sources = []

        element_kind = node.get_str(Symbol.KIND)

        # if there's a workspace for this element then just append a dummy workspace
        # metasource.
        workspace = self._context.get_workspaces().get_workspace(element.name)
        skip_workspace = True
        if workspace:
            workspace_node = {"kind": "workspace"}
            workspace_node["path"] = workspace.get_absolute_path()
            workspace_node["last_build"] = str(workspace.to_dict().get("last_build", ""))
            node[Symbol.SOURCES] = [workspace_node]
            skip_workspace = False

        sources = node.get_sequence(Symbol.SOURCES, default=[])
        for index, source in enumerate(sources):
            kind = source.get_str(Symbol.KIND)
            # the workspace source plugin cannot be used unless the element is workspaced
            if kind == "workspace" and skip_workspace:
                continue

            del source[Symbol.KIND]

            # Directory is optional
            directory = source.get_str(Symbol.DIRECTORY, default=None)
            if directory:
                del source[Symbol.DIRECTORY]
            meta_source = MetaSource(element.name, index, element_kind, kind, source, directory)
            meta_sources.append(meta_source)

        meta_element = MetaElement(
            self.project,
            element.name,
            element_kind,
            elt_provenance,
            meta_sources,
            node.get_mapping(Symbol.CONFIG, default={}),
            node.get_mapping(Symbol.VARIABLES, default={}),
            node.get_mapping(Symbol.ENVIRONMENT, default={}),
            node.get_str_list(Symbol.ENV_NOCACHE, default=[]),
            node.get_mapping(Symbol.PUBLIC, default={}),
            node.get_mapping(Symbol.SANDBOX, default={}),
            element_kind == "junction",
        )

        # Cache it now, make sure it's already there before recursing
        self._meta_elements[element.name] = meta_element
        if task is not _NO_PROGRESS:
            task.add_current_progress()

        return meta_element

    # _collect_element()
    #
    # Collect the toplevel elements we have
    #
    # Args:
    #    top_element (LoadElement): The element for which to load a MetaElement
    #    task (Task): The task to update with progress changes
    #
    # Returns:
    #    (MetaElement): A fully loaded MetaElement
    #
    def _collect_element(self, top_element, task):
        element_queue = [top_element]
        meta_element_queue = [self._collect_element_no_deps(top_element, task)]

        while element_queue:
            element = element_queue.pop()
            meta_element = meta_element_queue.pop()

            if element.meta_done:
                # This can happen if there are multiple top level targets
                # in which case, we simply skip over this element.
                continue

            for dep in element.dependencies:

                loader = dep.element._loader
                name = dep.element.name

                if name not in loader._meta_elements:
                    meta_dep = loader._collect_element_no_deps(dep.element, task)
                    element_queue.append(dep.element)
                    meta_element_queue.append(meta_dep)
                else:
                    meta_dep = loader._meta_elements[name]

                if dep.dep_type != "runtime":
                    meta_element.build_dependencies.append(meta_dep)
                if dep.dep_type != "build":
                    meta_element.dependencies.append(meta_dep)
                if dep.strict:
                    meta_element.strict_dependencies.append(meta_dep)

            element.meta_done = True

        return self._meta_elements[top_element.name]

    # _get_loader():
    #
    # Return loader for specified junction
    #
    # Args:
    #    filename (str): Junction name
    #
    # Raises: LoadError
    #
    # Returns: A Loader or None if specified junction does not exist
    def _get_loader(self, filename, *, rewritable=False, ticker=None, level=0, provenance=None):

        provenance_str = ""
        if provenance is not None:
            provenance_str = "{}: ".format(provenance)

        # return previously determined result
        if filename in self._loaders:
            loader = self._loaders[filename]

            if loader is None:
                # do not allow junctions with the same name in different
                # subprojects
                raise LoadError(
                    "{}Conflicting junction {} in subprojects, define junction in {}".format(
                        provenance_str, filename, self.project.name
                    ),
                    LoadErrorReason.CONFLICTING_JUNCTION,
                )

            return loader

        if self._parent:
            # junctions in the parent take precedence over junctions defined
            # in subprojects
            loader = self._parent._get_loader(
                filename, rewritable=rewritable, ticker=ticker, level=level + 1, provenance=provenance
            )
            if loader:
                self._loaders[filename] = loader
                return loader

        try:
            self._load_file(filename, rewritable, ticker)
        except LoadError as e:
            if e.reason != LoadErrorReason.MISSING_FILE:
                # other load error
                raise

            if level == 0:
                # junction element not found in this or ancestor projects
                raise

            # mark junction as not available to allow detection of
            # conflicting junctions in subprojects
            self._loaders[filename] = None
            return None

        # meta junction element
        #
        # Note that junction elements are not allowed to have
        # dependencies, so disabling progress reporting here should
        # have no adverse effects - the junction element itself cannot
        # be depended on, so it would be confusing for its load to
        # show up in logs.
        #
        # Any task counting *inside* the junction will be handled by
        # its loader.
        meta_element = self._collect_element_no_deps(self._elements[filename], _NO_PROGRESS)
        if meta_element.kind != "junction":
            raise LoadError(
                "{}{}: Expected junction but element kind is {}".format(provenance_str, filename, meta_element.kind),
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
        if self._elements[filename].dependencies:
            raise LoadError("Dependencies are forbidden for 'junction' elements", LoadErrorReason.INVALID_JUNCTION)

        element = Element._new_from_meta(meta_element)
        element._initialize_state()

        # If this junction element points to a sub-sub-project, we need to
        # find loader for that project.
        if element.target:
            subproject_loader = self._get_loader(
                element.target_junction, rewritable=rewritable, ticker=ticker, level=level, provenance=provenance
            )
            loader = subproject_loader._get_loader(
                element.target_element, rewritable=rewritable, ticker=ticker, level=level, provenance=provenance
            )
            self._loaders[filename] = loader
            return loader

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
        if not element._has_all_sources_in_source_cache():
            if ticker:
                ticker(filename, "Fetching subproject")
            self._fetch_subprojects([element])

        sources = list(element.sources())
        if len(sources) == 1 and sources[0]._get_local_path():
            # Optimization for junctions with a single local source
            basedir = sources[0]._get_local_path()
        else:
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
                self._context,
                junction=element,
                parent_loader=self,
                search_for_project=False,
                fetch_subprojects=self._fetch_subprojects,
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
    #   rewritable (bool): Whether the loaded files should be rewritable
    #                      this is a bit more expensive due to deep copies
    #   ticker (callable): An optional function for tracking load progress
    #
    # Returns:
    #   (tuple): - (str): name of the junction element
    #            - (str): name of the element
    #            - (Loader): loader for sub-project
    #
    def _parse_name(self, name, rewritable, ticker):
        # We allow to split only once since deep junctions names are forbidden.
        # Users who want to refer to elements in sub-sub-projects are required
        # to create junctions on the top level project.
        junction_path = name.rsplit(":", 1)
        if len(junction_path) == 1:
            return None, junction_path[-1], self
        else:
            self._load_file(junction_path[-2], rewritable, ticker)
            loader = self._get_loader(junction_path[-2], rewritable=rewritable, ticker=ticker)
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
        self._context.messenger.message(message)

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
