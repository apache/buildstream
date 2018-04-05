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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import os
import stat
import shlex
import tarfile
import itertools
from operator import itemgetter
from tempfile import TemporaryDirectory

from ._exceptions import PipelineError, ImplError, BstError
from ._message import Message, MessageType
from ._loader import Loader
from . import Consistency
from . import Scope
from . import _site
from . import utils
from ._platform import Platform
from ._project import ProjectRefStorage
from ._artifactcache.artifactcache import ArtifactCacheSpec, configured_remote_artifact_cache_specs

from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    inconsistent (bool): Whether to load the pipeline in a forcefully inconsistent state,
#                         this is appropriate when source tracking will run and the
#                         current source refs will not be the effective refs.
#    rewritable (bool): Whether the loaded files should be rewritable
#                       this is a bit more expensive due to deep copies
#    use_configured_remote_caches (bool): Whether to connect to configured artifact remotes.
#    add_remote_cache (str): Adds an additional artifact remote URL, which is
#                            prepended to the list of remotes (and thus given highest priority).
#
# The ticker methods will be called with an element name for each tick, a final
# tick with None as the argument is passed to signal that processing of this
# stage has terminated.
#
# Raises:
#    LoadError
#    PluginError
#    SourceError
#    ElementError
#    ProgramNotFoundError
#
class Pipeline():

    def __init__(self, context, project, targets, except_, rewritable=False):

        self.context = context     # The Context
        self.project = project     # The toplevel project
        self.session_elements = 0  # Number of elements to process in this session
        self.total_elements = 0    # Number of total potential elements for this pipeline
        self.targets = []          # List of toplevel target Element objects

        #
        # Private members
        #
        self._unused_workspaces = []
        self._resolved_elements = {}
        self._redundant_refs = []
        self._artifacts = None
        self._loader = None
        self._exceptions = None

        #
        # Early initialization
        #

        # Load selected platform
        Platform.create_instance(context, project)
        platform = Platform.get_platform()
        self._artifacts = platform.artifactcache
        self._loader = Loader(self.context, self.project, targets + except_)

        with self.context.timed_activity("Loading pipeline", silent_nested=True):
            meta_elements = self._loader.load(rewritable, None)

        # Resolve the real elements now that we've resolved the project
        with self.context.timed_activity("Resolving pipeline"):
            resolved_elements = [self._resolve(meta_element)
                                 for meta_element in meta_elements]

        # Now warn about any redundant source references which may have
        # been discovered in the resolve() phase.
        if self._redundant_refs:
            detail = "The following inline specified source references will be ignored:\n\n"
            lines = [
                "{}:{}".format(source._get_provenance(), ref)
                for source, ref in self._redundant_refs
            ]
            detail += "\n".join(lines)
            self._message(MessageType.WARN, "Ignoring redundant source references", detail=detail)

        self.targets = resolved_elements[:len(targets)]
        self._exceptions = resolved_elements[len(targets):]

    # initialize()
    #
    # Initialize the pipeline
    #
    # Args:
    #    use_configured_remote_caches (bool): Whether to contact configured remote artifact caches
    #    add_remote_cache (str): The URL for an additional remote artifact cache
    #    track_element (list of Elements): List of elements specified by the frontend for tracking
    #
    def initialize(self, use_configured_remote_caches=False,
                   add_remote_cache=None, track_elements=None):

        # Preflight directly, before ever interrogating caches or anything.
        self._preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        self._initialize_workspaces()

        # Initialize remote artifact caches. We allow the commandline to override
        # the user config in some cases (for example `bst push --remote=...`).
        has_remote_caches = False
        if add_remote_cache:
            self._artifacts.set_remotes([ArtifactCacheSpec(add_remote_cache, push=True)])
            has_remote_caches = True
        if use_configured_remote_caches:
            for project in self.context.get_projects():
                artifact_caches = configured_remote_artifact_cache_specs(self.context, project)
                if artifact_caches:  # artifact_caches is a list of ArtifactCacheSpec instances
                    self._artifacts.set_remotes(artifact_caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self._initialize_remote_caches()

        self._resolve_cache_keys(track_elements)

    # cleanup()
    #
    # Cleans up resources used by the Pipeline.
    #
    def cleanup(self):
        if self._loader:
            self._loader.cleanup()

    # deps_elements()
    #
    # Args:
    #    mode (str): A specific mode of resolving deps
    #
    # Various commands define a --deps option to specify what elements to
    # use in the result, this function reports a list that is appropriate for
    # the selected option.
    #
    def deps_elements(self, mode):

        elements = None
        if mode == 'none':
            elements = self.targets
        elif mode == 'plan':
            elements = list(self._plan())
        else:
            if mode == 'all':
                scope = Scope.ALL
            elif mode == 'build':
                scope = Scope.BUILD
            elif mode == 'run':
                scope = Scope.RUN

            elements = list(self.dependencies(scope))

        return self.remove_elements(elements)

    # dependencies()
    #
    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    # Args:
    #    scope (Scope): The scope to iterate over
    #    recurse (bool): Whether to recurse into dependencies
    #    include_sources (bool): Whether to include element sources in iteration
    #
    def dependencies(self, scope, *, recurse=True, include_sources=False):
        # Keep track of 'visited' in this scope, so that all targets
        # share the same context.
        visited = {}

        for target in self.targets:
            for element in target.dependencies(scope, recurse=recurse, visited=visited):
                if include_sources:
                    for source in element.sources():
                        yield source
                yield element

    #############################################################
    #                         Commands                          #
    #############################################################

    # track()
    #
    # Trackes all the sources of all the elements in the pipeline,
    # i.e. all of the elements which the target somehow depends on.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    dependencies (list): List of elements to track
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, scheduler, dependencies):

        dependencies = list(dependencies)
        track = TrackQueue()
        track.enqueue(dependencies)
        self.session_elements = len(dependencies)

        self._assert_junction_tracking(dependencies, build=False)

        _, status = scheduler.run([track])
        if status == SchedStatus.ERROR:
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            raise PipelineError(terminated=True)

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    dependencies (list): List of elements to fetch
    #    track_first (bool): Track new source references before fetching
    #
    def fetch(self, scheduler, dependencies, track_first):

        plan = dependencies

        # Assert that we have a consistent pipeline, or that
        # the track option will make it consistent
        if not track_first:
            self._assert_consistent(plan)

        # Filter out elements with cached sources, we already have them.
        cached = [elt for elt in plan if elt._consistency() == Consistency.CACHED]
        plan = [elt for elt in plan if elt not in cached]

        self.session_elements = len(plan)

        fetch = FetchQueue()
        if track_first:
            track = TrackQueue()
            track.enqueue(plan)
            queues = [track, fetch]
        else:
            track = None
            fetch.enqueue(plan)
            queues = [fetch]

        _, status = scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            raise PipelineError(terminated=True)

    def get_elements_to_track(self, track_targets):
        planner = _Planner()

        target_elements = [e for e in self.dependencies(Scope.ALL)
                           if e.name in track_targets]
        track_elements = planner.plan(target_elements, ignore_cache=True)

        return self.remove_elements(track_elements)

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    build_all (bool): Whether to build all elements, or only those
    #                      which are required to build the target.
    #    track_first (list): Elements whose sources to track prior to
    #                        building
    #
    def build(self, scheduler, build_all, track_first):
        if self._unused_workspaces:
            self._message(MessageType.WARN, "Unused workspaces",
                          detail="\n".join([el for el, _
                                            in self._unused_workspaces]))

        # We set up two plans; one to track elements, the other to
        # build them once tracking has finished. The first plan
        # contains elements from track_first, the second contains the
        # target elements.
        #
        # The reason we can't use one plan is that the tracking
        # elements may consist of entirely different elements.
        track_plan = []
        if track_first:
            track_plan = self.get_elements_to_track(track_first)

        self._assert_junction_tracking(track_plan, build=True)

        if build_all:
            plan = self.dependencies(Scope.ALL)
        else:
            plan = self._plan(except_=False)

        # We want to start the build queue with any elements that are
        # not being tracked first
        track_elements = set(track_plan)
        plan = [e for e in plan if e not in track_elements]

        # Assert that we have a consistent pipeline now (elements in
        # track_plan will be made consistent)
        self._assert_consistent(plan)

        fetch = FetchQueue(skip_cached=True)
        build = BuildQueue()
        track = None
        pull = None
        push = None
        queues = []
        if track_plan:
            track = TrackQueue()
            queues.append(track)
        if self._artifacts.has_fetch_remotes():
            pull = PullQueue()
            queues.append(pull)
        queues.append(fetch)
        queues.append(build)
        if self._artifacts.has_push_remotes():
            push = PushQueue()
            queues.append(push)

        if track:
            queues[0].enqueue(track_plan)
            queues[1].enqueue(plan)
        else:
            queues[0].enqueue(plan)

        self.session_elements = len(track_plan) + len(plan)

        _, status = scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            raise PipelineError(terminated=True)

    # checkout()
    #
    # Checkout the pipeline target artifact to the specified directory
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #    force (bool): Force overwrite files which exist in `directory`
    #    integrate (bool): Whether to run integration commands
    #    hardlinks (bool): Whether checking out files hardlinked to
    #                      their artifacts is acceptable
    #
    def checkout(self, directory, force, integrate, hardlinks):
        # We only have one target in a checkout command
        target = self.targets[0]

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise PipelineError("Failed to create checkout directory: {}".format(e)) from e

        if not os.access(directory, os.W_OK):
            raise PipelineError("Directory {} not writable".format(directory))

        if not force and os.listdir(directory):
            raise PipelineError("Checkout directory is not empty: {}"
                                .format(directory))

        # Stage deps into a temporary sandbox first
        try:
            with target._prepare_sandbox(Scope.RUN, None, integrate=integrate) as sandbox:

                # Copy or move the sandbox to the target directory
                sandbox_root = sandbox.get_directory()
                with target.timed_activity("Checking out files in {}".format(directory)):
                    try:
                        if hardlinks:
                            self.checkout_hardlinks(sandbox_root, directory)
                        else:
                            utils.copy_files(sandbox_root, directory)
                    except OSError as e:
                        raise PipelineError("Failed to checkout files: {}".format(e)) from e
        except BstError as e:
            raise PipelineError("Error while staging dependencies into a sandbox: {}".format(e),
                                reason=e.reason) from e

    # Helper function for checkout()
    #
    def checkout_hardlinks(self, sandbox_root, directory):
        try:
            removed = utils.safe_remove(directory)
        except OSError as e:
            raise PipelineError("Failed to remove checkout directory: {}".format(e)) from e

        if removed:
            # Try a simple rename of the sandbox root; if that
            # doesnt cut it, then do the regular link files code path
            try:
                os.rename(sandbox_root, directory)
            except OSError:
                os.makedirs(directory, exist_ok=True)
                utils.link_files(sandbox_root, directory)
        else:
            utils.link_files(sandbox_root, directory)

    # pull()
    #
    # Pulls elements from the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to pull
    #
    def pull(self, scheduler, elements):

        if not self._artifacts.has_fetch_remotes():
            raise PipelineError("Not artifact caches available for pulling artifacts")

        plan = elements
        self._assert_consistent(plan)
        self.session_elements = len(plan)

        pull = PullQueue()
        pull.enqueue(plan)
        queues = [pull]

        _, status = scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            raise PipelineError(terminated=True)

    # push()
    #
    # Pushes elements in the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to push
    #
    def push(self, scheduler, elements):

        if not self._artifacts.has_push_remotes():
            raise PipelineError("No artifact caches available for pushing artifacts")

        plan = elements
        self._assert_consistent(plan)
        self.session_elements = len(plan)

        push = PushQueue()
        push.enqueue(plan)
        queues = [push]

        _, status = scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            raise PipelineError(terminated=True)

    # remove_elements():
    #
    # Internal function
    #
    # Return what we are left with after the intersection between
    # excepted and target elements and their unique dependencies is
    # gone.
    #
    # Args:
    #    elements (list of elements): The list to remove elements from.
    def remove_elements(self, elements):
        targeted = list(self.dependencies(Scope.ALL))

        visited = []

        def find_intersection(element):
            if element in visited:
                return
            visited.append(element)

            # Intersection elements are those that are also in
            # 'targeted', as long as we don't recurse into them.
            if element in targeted:
                yield element
            else:
                for dep in element.dependencies(Scope.ALL, recurse=False):
                    yield from find_intersection(dep)

        # Build a list of 'intersection' elements, i.e. the set of
        # elements that lie on the border closest to excepted elements
        # between excepted and target elements.
        intersection = list(itertools.chain.from_iterable(
            find_intersection(element) for element in self._exceptions
        ))

        # Now use this set of elements to traverse the targeted
        # elements, except 'intersection' elements and their unique
        # dependencies.
        queue = []
        visited = []

        queue.extend(self.targets)
        while queue:
            element = queue.pop()
            if element in visited or element in intersection:
                continue
            visited.append(element)

            queue.extend(element.dependencies(Scope.ALL, recurse=False))

        # That looks like a lot, but overall we only traverse (part
        # of) the graph twice. This could be reduced to once if we
        # kept track of parent elements, but is probably not
        # significant.

        # Ensure that we return elements in the same order they were
        # in before.
        return [element for element in elements if element in visited]

    # source_bundle()
    #
    # Create a build bundle for the given artifact.
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #
    def source_bundle(self, scheduler, dependencies, force,
                      track_first, compression, directory):

        # source-bundle only supports one target
        target = self.targets[0]

        # Find the correct filename for the compression algorithm
        tar_location = os.path.join(directory, target.normal_name + ".tar")
        if compression != "none":
            tar_location += "." + compression

        # Attempt writing a file to generate a good error message
        # early
        #
        # FIXME: A bit hackish
        try:
            open(tar_location, mode="x")
            os.remove(tar_location)
        except IOError as e:
            raise PipelineError("Cannot write to {0}: {1}"
                                .format(tar_location, e)) from e

        plan = list(dependencies)
        self.fetch(scheduler, plan, track_first)

        # We don't use the scheduler for this as it is almost entirely IO
        # bound.

        # Create a temporary directory to build the source tree in
        builddir = target._get_context().builddir
        prefix = "{}-".format(target.normal_name)

        with TemporaryDirectory(prefix=prefix, dir=builddir) as tempdir:
            source_directory = os.path.join(tempdir, 'source')
            try:
                os.makedirs(source_directory)
            except OSError as e:
                raise PipelineError("Failed to create directory: {}"
                                    .format(e)) from e

            # Any elements that don't implement _write_script
            # should not be included in the later stages.
            plan = [element for element in plan
                    if self._write_element_script(source_directory, element)]

            self._write_element_sources(tempdir, plan)
            self._write_build_script(tempdir, plan)
            self._collect_sources(tempdir, tar_location,
                                  target.normal_name, compression)

    #############################################################
    #                     Private Methods                       #
    #############################################################

    # _resolve()
    #
    # Instantiates plugin-provided Element and Source instances
    # from MetaElement and MetaSource objects
    #
    # This has a side effect of populating `self._redundant_refs` so
    # we can later print a warning
    #
    def _resolve(self, meta_element):
        if meta_element in self._resolved_elements:
            return self._resolved_elements[meta_element]

        element = meta_element.project.create_element(meta_element.kind,
                                                      self._artifacts,
                                                      meta_element)

        self._resolved_elements[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self._resolve(dep), Scope.RUN)
        for dep in meta_element.build_dependencies:
            element._add_dependency(self._resolve(dep), Scope.BUILD)

        # resolve sources
        for meta_source in meta_element.sources:
            source = meta_element.project.create_source(meta_source.kind, meta_source)
            redundant_ref = source._load_ref()
            element._add_source(source)

            # Collect redundant refs for a warning message
            if redundant_ref is not None:
                self._redundant_refs.append((source, redundant_ref))

        return element

    # _prefilght()
    #
    # Preflights all the plugins in the pipeline
    #
    def _preflight(self):
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            try:
                plugin._preflight()
            except BstError as e:
                # Prepend the plugin identifier string to the error raised by
                # the plugin so that users can more quickly identify the issue
                # that a given plugin is encountering.
                #
                # Propagate the original error reason for test case purposes
                #
                raise PipelineError("{}: {}".format(plugin, e), reason=e.reason) from e

    # _initialize_workspaces()
    #
    # Initialize active workspaces, and collect a list
    # of any workspaces which are unused by the pipeline
    #
    def _initialize_workspaces(self):
        for element_name, workspace in self.project.workspaces.list():
            for target in self.targets:
                element = target.search(Scope.ALL, element_name)

                if element is None:
                    self._unused_workspaces.append((element_name, workspace))
                else:
                    workspace.init(element)

    # _initialize_remote_caches()
    #
    # Initialize remote artifact caches, checking what
    # artifacts are contained by the artifact cache remotes
    #
    def _initialize_remote_caches(self):
        def remote_failed(url, error):
            self._message(MessageType.WARN, "Failed to fetch remote refs from {}: {}".format(url, error))

        with self.context.timed_activity("Initializing remote caches", silent_nested=True):
            self._artifacts.initialize_remotes(on_failure=remote_failed)

    # _resolve_cache_keys()
    #
    # Initially resolve the cache keys
    #
    def _resolve_cache_keys(self, track_elements):
        if track_elements:
            track_elements = self.get_elements_to_track(track_elements)

        with self.context.timed_activity("Resolving cached state", silent_nested=True):
            for element in self.dependencies(Scope.ALL):
                if track_elements and element in track_elements:
                    # Load the pipeline in an explicitly inconsistent state, use
                    # this for pipelines with tracking queues enabled.
                    element._schedule_tracking()

                # Determine initial element state. This may resolve cache keys
                # and interrogate the artifact cache.
                element._update_state()

    # _assert_consistent()
    #
    # Asserts that the pipeline is in a consistent state, that
    # is to say that all sources are consistent and can at least
    # be fetched.
    #
    # Consequently it also means that cache keys can be resolved.
    #
    def _assert_consistent(self, toplevel):
        inconsistent = []
        with self.context.timed_activity("Checking sources"):
            for element in toplevel:
                if element._consistency() == Consistency.INCONSISTENT:
                    inconsistent.append(element)

        if inconsistent:
            detail = "Exact versions are missing for the following elements\n" + \
                     "Try tracking these elements first with `bst track`\n\n"
            for element in inconsistent:
                detail += "  " + element.name + "\n"
            raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline")

    # _assert_junction_tracking()
    #
    # Raises an error if tracking is attempted on junctioned elements and
    # a project.refs file is not enabled for the toplevel project.
    #
    # Args:
    #    elements (list of Element): The list of elements to be tracked
    #    build (bool): Whether this is being called for `bst build`, otherwise `bst track`
    #
    # The `build` argument is only useful for suggesting an appropriate
    # alternative to the user
    #
    def _assert_junction_tracking(self, elements, *, build):

        # We can track anything if the toplevel project uses project.refs
        #
        if self.project.ref_storage == ProjectRefStorage.PROJECT_REFS:
            return

        # Ideally, we would want to report every cross junction element but not
        # their dependencies, unless those cross junction elements dependencies
        # were also explicitly requested on the command line.
        #
        # But this is too hard, lets shoot for a simple error.
        for element in elements:
            element_project = element._get_project()
            if element_project is not self.project:
                suggestion = '--except'
                if build:
                    suggestion = '--track-except'

                detail = "Requested to track sources across junction boundaries\n" + \
                         "in a project which does not use separate source references.\n\n" + \
                         "Try using `{}` arguments to limit the scope of tracking.".format(suggestion)

                raise PipelineError("Untrackable sources", detail=detail, reason="untrackable-sources")

    # _plan()
    #
    # Args:
    #    except_ (bool): Whether to filter out the except elements from the plan
    #
    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def _plan(self, except_=True):
        build_plan = _Planner().plan(self.targets)

        if except_:
            build_plan = self.remove_elements(build_plan)

        for element in build_plan:
            yield element

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context.message(
            Message(None, message_type, message, **args))

    # Write the element build script to the given directory
    def _write_element_script(self, directory, element):
        try:
            element._write_script(directory)
        except ImplError:
            return False
        return True

    # Write all source elements to the given directory
    def _write_element_sources(self, directory, elements):
        for element in elements:
            source_dir = os.path.join(directory, "source")
            element_source_dir = os.path.join(source_dir, element.normal_name)

            element._stage_sources_at(element_source_dir)

    # Write a master build script to the sandbox
    def _write_build_script(self, directory, elements):

        module_string = ""
        for element in elements:
            module_string += shlex.quote(element.normal_name) + " "

        script_path = os.path.join(directory, "build.sh")

        with open(_site.build_all_template, "r") as f:
            script_template = f.read()

        with utils.save_file_atomic(script_path, "w") as script:
            script.write(script_template.format(modules=module_string))

        os.chmod(script_path, stat.S_IEXEC | stat.S_IREAD)

    # Collect the sources in the given sandbox into a tarfile
    def _collect_sources(self, directory, tar_name, element_name, compression):
        with self.targets[0].timed_activity("Creating tarball {}".format(tar_name)):
            if compression == "none":
                permissions = "w:"
            else:
                permissions = "w:" + compression

            with tarfile.open(tar_name, permissions) as tar:
                tar.add(directory, arcname=element_name)


# _Planner()
#
# An internal object used for constructing build plan
# from a given resolved toplevel element, while considering what
# parts need to be built depending on build only dependencies
# being cached, and depth sorting for more efficient processing.
#
class _Planner():
    def __init__(self):
        self.depth_map = {}
        self.visiting_elements = set()

    # Here we want to traverse the same element more than once when
    # it is reachable from multiple places, with the interest of finding
    # the deepest occurance of every element
    def plan_element(self, element, depth, ignore_cache):
        if element in self.visiting_elements:
            # circular dependency, already being processed
            return

        prev_depth = self.depth_map.get(element)
        if prev_depth is not None and prev_depth >= depth:
            # element and dependencies already processed at equal or greater depth
            return

        self.visiting_elements.add(element)
        for dep in element.dependencies(Scope.RUN, recurse=False):
            self.plan_element(dep, depth, ignore_cache)

        # Dont try to plan builds of elements that are cached already
        if ignore_cache or (not element._cached() and not element._remotely_cached()):
            for dep in element.dependencies(Scope.BUILD, recurse=False):
                self.plan_element(dep, depth + 1, ignore_cache)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, roots, ignore_cache=False):
        for root in roots:
            self.plan_element(root, 0, ignore_cache)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)
        return [item[0] for item in depth_sorted if ignore_cache or not item[0]._cached()]
