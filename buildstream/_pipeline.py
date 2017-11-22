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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import os
import stat
import shlex
import shutil
import tarfile
import itertools
from contextlib import contextmanager
from operator import itemgetter
from pluginbase import PluginBase
from tempfile import TemporaryDirectory

from ._exceptions import PipelineError, ArtifactError, ImplError, BstError
from ._message import Message, MessageType
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from . import Consistency
from . import Scope
from . import _site
from . import utils
from ._platform import Platform
from ._artifactcache import configured_artifact_cache_urls

from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue


class Planner():
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
#    use_remote_cache (bool): Whether to connect with remote artifact cache
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
        self.context = context
        self.project = project
        self.session_elements = 0
        self.total_elements = 0
        self.unused_workspaces = []
        self._resolved_elements = {}

        # Load selected platform
        Platform._create_instance(context, project)
        self.platform = Platform.get_platform()
        self.artifacts = self.platform.artifactcache

        loader = Loader(self.project.element_path, targets + except_,
                        self.project._options)

        with self.timed_activity("Loading pipeline", silent_nested=True):
            meta_elements = loader.load(rewritable, None)

        # Create the factories after resolving the project
        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase, project._plugin_element_origins)
        self.source_factory = SourceFactory(pluginbase, project._plugin_source_origins)

        # Resolve the real elements now that we've resolved the project
        with self.timed_activity("Resolving pipeline"):
            resolved_elements = [self.resolve(meta_element)
                                 for meta_element in meta_elements]

        self.targets = resolved_elements[:len(targets)]
        self.exceptions = resolved_elements[len(targets):]

    def initialize(self, use_remote_cache=False, inconsistent=None):
        # Preflight directly, before ever interrogating caches or
        # anything.
        self.preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        self.initialize_workspaces()

        if use_remote_cache:
            self.initialize_remote_caches()

        self.resolve_cache_keys(inconsistent)

    def preflight(self):
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            try:
                plugin.preflight()
            except BstError as e:
                # Prepend the plugin identifier string to the error raised by
                # the plugin so that users can more quickly identify the issue
                # that a given plugin is encountering.
                #
                # Propagate the original error reason for test case purposes
                #
                raise PipelineError("{}: {}".format(plugin, e), reason=e.reason) from e

    def initialize_workspaces(self):
        for element_name, source, workspace in self.project._list_workspaces():
            for target in self.targets:
                element = target.search(Scope.ALL, element_name)

                if element is None:
                    self.unused_workspaces.append((element_name, source, workspace))
                    continue

                self.project._set_workspace(element, source, workspace)

    def initialize_remote_caches(self):
        def remote_failed(url, error):
            self.message(MessageType.WARN, "Failed to fetch remote refs from {}: {}\n".format(url, error))

        with self.timed_activity("Initializing remote caches", silent_nested=True):
            artifact_urls = configured_artifact_cache_urls(self.context, self.project)
            self.artifacts.set_remotes(artifact_urls, on_failure=remote_failed)

    def resolve_cache_keys(self, inconsistent):
        if inconsistent:
            inconsistent = self.get_elements_to_track(inconsistent)

        with self.timed_activity("Resolving cached state", silent_nested=True):
            for element in self.dependencies(Scope.ALL):
                if inconsistent and element in inconsistent:
                    # Load the pipeline in an explicitly inconsistent state, use
                    # this for pipelines with tracking queues enabled.
                    element._force_inconsistent()
                else:
                    # Resolve cache keys and interrogate the artifact cache
                    # for the first time.
                    element._cached()

    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    def dependencies(self, scope, include_sources=False):
        # Keep track of 'visited' in this scope, so that all targets
        # share the same context.
        visited = {}

        for target in self.targets:
            for element in target.dependencies(scope, visited=visited):
                if include_sources:
                    for source in element.sources():
                        yield source
                yield element

    # Asserts that the pipeline is in a consistent state, that
    # is to say that all sources are consistent and can at least
    # be fetched.
    #
    # Consequently it also means that cache keys can be resolved.
    #
    def assert_consistent(self, toplevel):
        inconsistent = []
        for element in toplevel:
            if element._consistency() == Consistency.INCONSISTENT:
                inconsistent.append(element)

        if inconsistent:
            detail = "Exact versions are missing for the following elements\n" + \
                     "Try tracking these elements first with `bst track`\n\n"
            for element in inconsistent:
                detail += "  " + element.name + "\n"
            raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline")

    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def plan(self, except_=True):
        build_plan = Planner().plan(self.targets)

        if except_:
            build_plan = self.remove_elements(build_plan)

        for element in build_plan:
            yield element

    # Local message propagator
    #
    def message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context._message(
            Message(None, message_type, message, **args))

    # Local timed activities, announces the jobs as well
    #
    @contextmanager
    def timed_activity(self, activity_name, *, detail=None, silent_nested=False):
        with self.context._timed_activity(activity_name,
                                          detail=detail,
                                          silent_nested=silent_nested):
            yield

    # Internal: Instantiates plugin-provided Element and Source instances
    # from MetaElement and MetaSource objects
    #
    def resolve(self, meta_element):
        if meta_element in self._resolved_elements:
            return self._resolved_elements[meta_element]

        element = self.element_factory.create(meta_element.kind,
                                              self.context,
                                              self.project,
                                              self.artifacts,
                                              meta_element)

        self._resolved_elements[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self.resolve(dep), Scope.RUN)
        for dep in meta_element.build_dependencies:
            element._add_dependency(self.resolve(dep), Scope.BUILD)

        # resolve sources
        for meta_source in meta_element.sources:
            element._add_source(
                self.source_factory.create(meta_source.kind,
                                           self.context,
                                           self.project,
                                           meta_source)
            )

        return element

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
        track = TrackQueue(save=True)
        track.enqueue(dependencies)
        self.session_elements = len(dependencies)

        self.message(MessageType.START, "Starting track")
        elapsed, status = scheduler.run([track])
        changed = len(track.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(MessageType.FAIL, "Track failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(MessageType.WARN,
                         "Terminated after updating {} source references".format(changed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(MessageType.SUCCESS,
                         "Updated {} source references".format(changed),
                         elapsed=elapsed)

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
            self.assert_consistent(plan)

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

        self.message(MessageType.START, "Fetching {} elements".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        fetched = len(fetch.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(MessageType.FAIL, "Fetch failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(MessageType.WARN,
                         "Terminated after fetching {} elements".format(fetched),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(MessageType.SUCCESS,
                         "Fetched {} elements".format(fetched),
                         elapsed=elapsed)

    def get_elements_to_track(self, track_targets):
        planner = Planner()

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
    #    save (bool): Whether to save the tracking results in the
    #                 elements
    #
    def build(self, scheduler, build_all, track_first, save):
        if len(self.unused_workspaces) > 0:
            self.message(MessageType.WARN, "Unused workspaces",
                         detail="\n".join([el + "-" + str(src) for el, src, _
                                           in self.unused_workspaces]))

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

        if build_all:
            plan = self.dependencies(Scope.ALL)
        else:
            plan = self.plan(except_=False)

        # We want to start the build queue with any elements that are
        # not being tracked first
        track_elements = set(track_plan)
        plan = [e for e in plan if e not in track_elements]

        # Assert that we have a consistent pipeline now (elements in
        # track_plan will be made consistent)
        self.assert_consistent(plan)

        fetch = FetchQueue(skip_cached=True)
        build = BuildQueue()
        track = None
        pull = None
        push = None
        queues = []
        if track_plan:
            track = TrackQueue(save=save)
            queues.append(track)
        if self.artifacts.has_fetch_remotes():
            pull = PullQueue()
            queues.append(pull)
        queues.append(fetch)
        queues.append(build)
        if self.artifacts.has_push_remotes():
            push = PushQueue()
            queues.append(push)

        if track:
            queues[0].enqueue(track_plan)
            queues[1].enqueue(plan)
        else:
            queues[0].enqueue(plan)

        self.session_elements = len(track_plan) + len(plan)

        self.message(MessageType.START, "Starting build")
        elapsed, status = scheduler.run(queues)

        if status == SchedStatus.ERROR:
            self.message(MessageType.FAIL, "Build failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(MessageType.WARN, "Terminated", elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(MessageType.SUCCESS, "Build Complete", elapsed=elapsed)

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

    # open_workspace
    #
    # Open a project workspace.
    #
    # Args:
    #    directory (str): The directory to stage the source in
    #    source_index (int): The index of the source to stage
    #    no_checkout (bool): Whether to skip checking out the source
    #    track_first (bool): Whether to track and fetch first
    #    force (bool): Whether to ignore contents in an existing directory
    #
    def open_workspace(self, scheduler, directory, source_index, no_checkout, track_first, force):
        # When working on workspaces we only have one target
        target = self.targets[0]
        workdir = os.path.abspath(directory)
        sources = list(target.sources())
        source_index = self.validate_workspace_index(source_index)

        # Check directory
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise PipelineError("Failed to create workspace directory: {}".format(e)) from e

        if not no_checkout and not force and os.listdir(directory):
            raise PipelineError("Checkout directory is not empty: {}".format(directory))

        # Check for workspace config
        if self.project._get_workspace(target.name, source_index):
            raise PipelineError("Workspace '{}' is already defined."
                                .format(target.name + " - " + str(source_index)))

        plan = [target]

        # Track/fetch if required
        queues = []
        track = None

        if track_first:
            track = TrackQueue()
            queues.append(track)
        if not no_checkout or track_first:
            fetch = FetchQueue(skip_cached=True)
            queues.append(fetch)

        if len(queues) > 0:
            queues[0].enqueue(plan)

            elapsed, status = scheduler.run(queues)
            fetched = len(fetch.processed_elements)

            if status == SchedStatus.ERROR:
                self.message(MessageType.FAIL, "Tracking failed", elapsed=elapsed)
                raise PipelineError()
            elif status == SchedStatus.TERMINATED:
                self.message(MessageType.WARN,
                             "Terminated after fetching {} elements".format(fetched),
                             elapsed=elapsed)
                raise PipelineError()
            else:
                self.message(MessageType.SUCCESS,
                             "Fetched {} elements".format(fetched), elapsed=elapsed)

        if not no_checkout:
            source = sources[source_index]
            with target.timed_activity("Staging source to {}".format(directory)):
                if source.get_consistency() != Consistency.CACHED:
                    raise PipelineError("Could not stage uncached source. " +
                                        "Use `--track` to track and " +
                                        "fetch the latest version of the " +
                                        "source.")
                source._init_workspace(directory)

        self.project._set_workspace(target, source_index, workdir)

        with target.timed_activity("Saving workspace configuration"):
            self.project._save_workspace_config()

    # close_workspace
    #
    # Close a project workspace
    #
    # Args:
    #    source_index (int) - The index of the source
    #    remove_dir (bool) - Whether to remove the associated directory
    #
    def close_workspace(self, source_index, remove_dir):
        # When working on workspaces we only have one target
        target = self.targets[0]
        source_index = self.validate_workspace_index(source_index)

        # Remove workspace directory if prompted
        if remove_dir:
            path = self.project._get_workspace(target.name, source_index)
            if path is not None:
                with target.timed_activity("Removing workspace directory {}"
                                           .format(path)):
                    try:
                        shutil.rmtree(path)
                    except OSError as e:
                        raise PipelineError("Could not remove  '{}': {}"
                                            .format(path, e)) from e

        # Delete the workspace config entry
        with target.timed_activity("Removing workspace"):
            try:
                self.project._delete_workspace(target.name, source_index)
            except KeyError:
                raise PipelineError("Workspace '{}' is currently not defined"
                                    .format(target.name + " - " + str(source_index)))

        # Update workspace config
        self.project._save_workspace_config()

        # Reset source to avoid checking out the (now empty) workspace
        source = list(target.sources())[source_index]
        source._del_workspace()

    # reset_workspace
    #
    # Reset a workspace to its original state, discarding any user
    # changes.
    #
    # Args:
    #    scheduler: The app scheduler
    #    source_index (int): The index of the source to reset
    #    track (bool): Whether to also track the source
    #    no_checkout (bool): Whether to check out the source (at all)
    #
    def reset_workspace(self, scheduler, source_index, track, no_checkout):
        # When working on workspaces we only have one target
        target = self.targets[0]
        source_index = self.validate_workspace_index(source_index)
        workspace_dir = self.project._get_workspace(target.name, source_index)

        if workspace_dir is None:
            raise PipelineError("Workspace '{}' is currently not defined"
                                .format(target.name + " - " + str(source_index)))

        self.close_workspace(source_index, True)

        self.open_workspace(scheduler, workspace_dir, source_index, no_checkout,
                            track, False)

    # pull()
    #
    # Pulls elements from the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to pull
    #
    def pull(self, scheduler, elements):

        if not self.artifacts.has_fetch_remotes():
            raise PipelineError("Not artifact caches available for pulling artifacts")

        plan = elements
        self.assert_consistent(plan)
        self.session_elements = len(plan)

        pull = PullQueue()
        pull.enqueue(plan)
        queues = [pull]

        self.message(MessageType.START, "Pulling {} artifacts".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        pulled = len(pull.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(MessageType.FAIL, "Pull failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(MessageType.WARN,
                         "Terminated after pulling {} elements".format(pulled),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(MessageType.SUCCESS,
                         "Pulled {} complete".format(pulled),
                         elapsed=elapsed)

    # push()
    #
    # Pushes elements in the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to push
    #
    def push(self, scheduler, elements):

        if not self.artifacts.has_push_remotes():
            raise PipelineError("No artifact caches available for pushing artifacts")

        plan = elements
        self.assert_consistent(plan)
        self.session_elements = len(plan)

        push = PushQueue()
        push.enqueue(plan)
        queues = [push]

        self.message(MessageType.START, "Pushing {} artifacts".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        pushed = len(push.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(MessageType.FAIL, "Push failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(MessageType.WARN,
                         "Terminated after pushing {} elements".format(pushed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(MessageType.SUCCESS,
                         "Pushed {} complete".format(pushed),
                         elapsed=elapsed)

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
            find_intersection(element) for element in self.exceptions
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

    def validate_workspace_index(self, source_index):
        sources = list(self.targets[0].sources())

        # Validate source_index
        if len(sources) < 1:
            raise PipelineError("The given element has no sources")
        if len(sources) == 1 and source_index is None:
            source_index = 0
        if source_index is None:
            raise PipelineError("An index needs to be specified for elements with more than one source")

        return source_index

    # Various commands define a --deps option to specify what elements to
    # use in the result, this function reports a list that is appropriate for
    # the selected option.
    #
    def deps_elements(self, mode):

        elements = None
        if mode == 'none':
            elements = self.targets
        elif mode == 'plan':
            elements = list(self.plan())
        else:
            if mode == 'all':
                scope = Scope.ALL
            elif mode == 'build':
                scope = Scope.BUILD
            elif mode == 'run':
                scope = Scope.RUN

            elements = list(self.dependencies(scope))

        return self.remove_elements(elements)

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
