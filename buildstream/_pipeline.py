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
import shutil
import tarfile
import itertools
from contextlib import contextmanager
from operator import itemgetter
from tempfile import TemporaryDirectory

from ._exceptions import PipelineError, ArtifactError, ImplError, BstError
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
        self.context = context
        self.project = project
        self.session_elements = 0
        self.total_elements = 0
        self.unused_workspaces = []
        self._resolved_elements = {}
        self._redundant_refs = []

        # Load selected platform
        Platform._create_instance(context, project)
        self.platform = Platform.get_platform()
        self.artifacts = self.platform.artifactcache

        self.loader = Loader(self.project, targets + except_)

        with self.timed_activity("Loading pipeline", silent_nested=True):
            meta_elements = self.loader.load(rewritable, None)

        # Resolve the real elements now that we've resolved the project
        with self.timed_activity("Resolving pipeline"):
            resolved_elements = [self.resolve(meta_element)
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
            self.message(MessageType.WARN, "Ignoring redundant source references", detail=detail)

        self.targets = resolved_elements[:len(targets)]
        self.exceptions = resolved_elements[len(targets):]

    def initialize(self, use_configured_remote_caches=False,
                   add_remote_cache=None, track_elements=None):
        # Preflight directly, before ever interrogating caches or
        # anything.
        self.preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        self.initialize_workspaces()

        # Initialize remote artifact caches. We allow the commandline to override
        # the user config in some cases (for example `bst push --remote=...`).
        has_remote_caches = False
        if add_remote_cache:
            self.artifacts.set_remotes([ArtifactCacheSpec(add_remote_cache, push=True)])
            has_remote_caches = True
        if use_configured_remote_caches:
            for project in self.context._get_projects():
                artifact_caches = configured_remote_artifact_cache_specs(self.context, project)
                if artifact_caches:  # artifact_caches is a list of ArtifactCacheSpec instances
                    self.artifacts.set_remotes(artifact_caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self.initialize_remote_caches()

        self.resolve_cache_keys(track_elements)

    def preflight(self):
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

    def initialize_workspaces(self):
        for element_name, workspace in self.project._list_workspaces():
            for target in self.targets:
                element = target.search(Scope.ALL, element_name)

                if element is None:
                    self.unused_workspaces.append((element_name, workspace))
                    continue

                self.project._set_workspace(element, workspace)

    def initialize_remote_caches(self):
        def remote_failed(url, error):
            self.message(MessageType.WARN, "Failed to fetch remote refs from {}: {}".format(url, error))

        with self.timed_activity("Initializing remote caches", silent_nested=True):
            self.artifacts.initialize_remotes(on_failure=remote_failed)

    def resolve_cache_keys(self, track_elements):
        if track_elements:
            track_elements = self.get_elements_to_track(track_elements)

        with self.timed_activity("Resolving cached state", silent_nested=True):
            for element in self.dependencies(Scope.ALL):
                if track_elements and element in track_elements:
                    # Load the pipeline in an explicitly inconsistent state, use
                    # this for pipelines with tracking queues enabled.
                    element._schedule_tracking()

                # Determine initial element state. This may resolve cache keys
                # and interrogate the artifact cache.
                element._update_state()

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
        with self.timed_activity("Checking sources"):
            for element in toplevel:
                if element._consistency() == Consistency.INCONSISTENT:
                    inconsistent.append(element)

        if inconsistent:
            detail = "Exact versions are missing for the following elements\n" + \
                     "Try tracking these elements first with `bst track`\n\n"
            for element in inconsistent:
                detail += "  " + element.name + "\n"
            raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline")

    # assert_junction_tracking()
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
    def assert_junction_tracking(self, elements, *, build):

        # We can track anything if the toplevel project uses project.refs
        #
        if self.project._ref_storage == ProjectRefStorage.PROJECT_REFS:
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
    # This has a side effect of populating `self._redundant_refs` so
    # we can later print a warning
    #
    def resolve(self, meta_element):
        if meta_element in self._resolved_elements:
            return self._resolved_elements[meta_element]

        element = meta_element.project._create_element(meta_element.kind,
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
            source = meta_element.project._create_source(meta_source.kind, meta_source)
            redundant_ref = source._load_ref()
            element._add_source(source)

            # Collect redundant refs for a warning message
            if redundant_ref is not None:
                self._redundant_refs.append((source, redundant_ref))

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
        track = TrackQueue()
        track.enqueue(dependencies)
        self.session_elements = len(dependencies)

        self.assert_junction_tracking(dependencies, build=False)

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
    #
    def build(self, scheduler, build_all, track_first):
        if self.unused_workspaces:
            self.message(MessageType.WARN, "Unused workspaces",
                         detail="\n".join([el for el, _
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

        self.assert_junction_tracking(track_plan, build=True)

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
            track = TrackQueue()
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

    # open_workspace
    #
    # Open a project workspace.
    #
    # Args:
    #    directory (str): The directory to stage the source in
    #    no_checkout (bool): Whether to skip checking out the source
    #    track_first (bool): Whether to track and fetch first
    #    force (bool): Whether to ignore contents in an existing directory
    #
    def open_workspace(self, scheduler, directory, no_checkout, track_first, force):
        # When working on workspaces we only have one target
        target = self.targets[0]
        workdir = os.path.abspath(directory)

        if not list(target.sources()):
            build_depends = [x.name for x in target.dependencies(Scope.BUILD, recurse=False)]
            if not build_depends:
                raise PipelineError("The given element has no sources or build-dependencies")
            detail = "Try opening a workspace on one of its dependencies instead:\n"
            detail += "  \n".join(build_depends)
            raise PipelineError("The given element has no sources", detail=detail)

        # Check for workspace config
        if self.project._get_workspace(target.name):
            raise PipelineError("Workspace '{}' is already defined."
                                .format(target.name))

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

        if queues:
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

        if not no_checkout and target._consistency() != Consistency.CACHED:
            raise PipelineError("Could not stage uncached source. " +
                                "Use `--track` to track and " +
                                "fetch the latest version of the " +
                                "source.")

        # Check directory
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise PipelineError("Failed to create workspace directory: {}".format(e)) from e

        if not no_checkout:
            if not force and os.listdir(directory):
                raise PipelineError("Checkout directory is not empty: {}".format(directory))

            with target.timed_activity("Staging sources to {}".format(directory)):
                for source in target.sources():
                    source._init_workspace(directory)

        self.project._set_workspace(target, workdir)

        with target.timed_activity("Saving workspace configuration"):
            self.project._save_workspace_config()

    # close_workspace
    #
    # Close a project workspace
    #
    # Args:
    #    remove_dir (bool) - Whether to remove the associated directory
    #
    def close_workspace(self, remove_dir):
        # When working on workspaces we only have one target
        target = self.targets[0]

        # Remove workspace directory if prompted
        if remove_dir:
            path = self.project._get_workspace(target.name)
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
                self.project._delete_workspace(target.name)
            except KeyError:
                raise PipelineError("Workspace '{}' is currently not defined"
                                    .format(target.name))

        # Update workspace config
        self.project._save_workspace_config()

        # Reset source to avoid checking out the (now empty) workspace
        for source in target.sources():
            source._del_workspace()

    # reset_workspace
    #
    # Reset a workspace to its original state, discarding any user
    # changes.
    #
    # Args:
    #    scheduler: The app scheduler
    #    track (bool): Whether to also track the source
    #    no_checkout (bool): Whether to check out the source (at all)
    #
    def reset_workspace(self, scheduler, track, no_checkout):
        # When working on workspaces we only have one target
        target = self.targets[0]
        workspace_dir = self.project._get_workspace(target.name)

        if workspace_dir is None:
            raise PipelineError("Workspace '{}' is currently not defined"
                                .format(target.name))

        self.close_workspace(True)

        self.open_workspace(scheduler, workspace_dir, no_checkout, track, False)

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

    def cleanup(self):
        if self.loader:
            self.loader.cleanup()
