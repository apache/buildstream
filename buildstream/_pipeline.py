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

import datetime
import os
import stat
import shlex
import shutil
import tarfile
from operator import itemgetter
from tempfile import TemporaryDirectory
from pluginbase import PluginBase

from .exceptions import _BstError, _ArtifactError
from ._message import Message, MessageType
from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from . import Consistency, ImplError, LoadError
from . import Scope
from . import _site
from . import _yaml, utils

from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue


# Internal exception raised when a pipeline fails
#
class PipelineError(_BstError):

    def __init__(self, message=None):

        # The empty string should never appear to a user,
        # this only allows us to treat this internal error as
        # a _BstError from the frontend.
        if message is None:
            message = ""
        super(PipelineError, self).__init__(message)


class Planner():
    def __init__(self):
        self.depth_map = {}
        self.visiting_elements = set()

    # Here we want to traverse the same element more than once when
    # it is reachable from multiple places, with the interest of finding
    # the deepest occurance of every element
    def plan_element(self, element, depth):
        if element in self.visiting_elements:
            # circular dependency, already being processed
            return

        prev_depth = self.depth_map.get(element)
        if prev_depth is not None and prev_depth >= depth:
            # element and dependencies already processed at equal or greater depth
            return

        self.visiting_elements.add(element)
        for dep in element.dependencies(Scope.RUN, recurse=False):
            self.plan_element(dep, depth)

        # Dont try to plan builds of elements that are cached already
        if not element._cached() and not element._remotely_cached():
            for dep in element.dependencies(Scope.BUILD, recurse=False):
                self.plan_element(dep, depth + 1)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, root):
        self.plan_element(root, 0)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)
        return [item[0] for item in depth_sorted if not item[0]._cached()]


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    target_variant (str): The selected variant of 'target', or None for the default
#    inconsistent (bool): Whether to load the pipeline in a forcefully inconsistent state,
#                         this is appropriate when source tracking will run and the
#                         current source refs will not be the effective refs.
#    rewritable (bool): Whether the loaded files should be rewritable
#                       this is a bit more expensive due to deep copies
#    load_ticker (callable): A function which will be called for each loaded element
#    resolve_ticker (callable): A function which will be called for each resolved element
#    cache_ticker (callable): A function which will be called for each element
#                             while interrogating caches
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

    def __init__(self, context, project, target, target_variant,
                 inconsistent=False,
                 rewritable=False,
                 load_ticker=None,
                 resolve_ticker=None,
                 cache_ticker=None):
        self.context = context
        self.project = project
        self.artifacts = ArtifactCache(self.context)
        self.session_elements = 0
        self.total_elements = 0
        self.unused_workspaces = []

        loader = Loader(self.project.element_path, target, target_variant,
                        context.host_arch, context.target_arch,
                        list(project._list_variants()))
        meta_element = loader.load(rewritable, load_ticker)
        if load_ticker:
            load_ticker(None)

        # Resolve project variant now that we've decided on one
        project._resolve(loader.project_variant)

        # Create the factories after resolving the project
        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase, project._plugin_element_paths)
        self.source_factory = SourceFactory(pluginbase, project._plugin_source_paths)

        # Resolve the real elements now that we've resolved the project
        self.target = self.resolve(meta_element, ticker=resolve_ticker)
        if resolve_ticker:
            resolve_ticker(None)

        # Preflight directly after resolving elements, before ever interrogating
        # caches or anything.
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            plugin.preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        for element_name, source, workspace in project._workspaces():
            element = self.target.search(Scope.ALL, element_name)

            if element is None:
                self.unused_workspaces.append((element_name, source, workspace))
                continue

            self.project._set_workspace(element, source, workspace)

        if self.artifacts.can_fetch():
            try:
                self.artifacts.fetch_remote_refs()
            except _ArtifactError:
                self.message(self.target, MessageType.WARN, "Failed to fetch remote refs")
                self.artifacts.set_offline()

        for element in self.dependencies(Scope.ALL):
            if cache_ticker:
                cache_ticker(element.name)

            if inconsistent:
                # Load the pipeline in an explicitly inconsistent state, use
                # this for pipelines with tracking queues enabled.
                element._force_inconsistent()
            else:
                # Resolve cache keys and interrogate the artifact cache
                # for the first time.
                element._cached()

        if cache_ticker:
            cache_ticker(None)

    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    def dependencies(self, scope, include_sources=False):
        for element in self.target.dependencies(scope):
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
            self.message(self.target, MessageType.ERROR, "Inconsistent pipeline", detail=detail)
            raise PipelineError()

    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def plan(self):
        build_plan = Planner().plan(self.target)
        for element in build_plan:
            yield element

    # Local message propagator
    #
    def message(self, plugin, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    **args))

    # Internal: Instantiates plugin-provided Element and Source instances
    # from MetaElement and MetaSource objects
    #
    def resolve(self, meta_element, resolved=None, ticker=None):
        if resolved is None:
            resolved = {}

        if meta_element in resolved:
            return resolved[meta_element]

        if ticker:
            ticker(meta_element.name)

        element = self.element_factory.create(meta_element.kind,
                                              self.context,
                                              self.project,
                                              self.artifacts,
                                              meta_element)

        resolved[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self.resolve(dep, resolved=resolved, ticker=ticker), Scope.RUN)
        for dep in meta_element.build_dependencies:
            element._add_dependency(self.resolve(dep, resolved=resolved, ticker=ticker), Scope.BUILD)

        # resolve sources
        for meta_source in meta_element.sources:
            element._add_source(
                self.source_factory.create(meta_source.kind,
                                           self.context,
                                           self.project,
                                           meta_source)
            )

        return element

    # Internal: If a remote artifact cache is configured for pushing, check that it
    # actually works.
    def assert_remote_artifact_cache(self):
        if self.artifacts.can_push():
            starttime = datetime.datetime.now()
            self.message(self.target, MessageType.START, "Checking connectivity to remote artifact cache")
            try:
                self.artifacts.preflight()
            except _ArtifactError as e:
                self.message(self.target, MessageType.FAIL, str(e),
                             elapsed=datetime.datetime.now() - starttime)
                raise PipelineError()
            self.message(self.target, MessageType.SUCCESS, "Connectivity OK",
                         elapsed=datetime.datetime.now() - starttime)

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
    #    except_ (list): List of elements to except from tracking
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, scheduler, dependencies):

        dependencies = list(dependencies)
        track = TrackQueue()
        track.enqueue(dependencies)
        self.session_elements = len(dependencies)

        self.message(self.target, MessageType.START, "Starting track")
        elapsed, status = scheduler.run([track])
        changed = len(track.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Track failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after updating {} source references".format(changed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
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
    #    except_ (list): List of elements to except from fetching
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

        self.message(self.target, MessageType.START, "Fetching {} elements".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        fetched = len(fetch.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Fetch failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after fetching {} elements".format(fetched),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
                         "Fetched {} elements".format(fetched),
                         elapsed=elapsed)

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    build_all (bool): Whether to build all elements, or only those
    #                      which are required to build the target.
    #    track_first (bool): Track sources before fetching and building (implies build_all)
    #
    def build(self, scheduler, build_all, track_first):
        if len(self.unused_workspaces) > 0:
            self.message(self.target, MessageType.WARN, "Unused workspaces",
                         detail="\n".join([el + "-" + str(src) for el, src, _
                                           in self.unused_workspaces]))

        self.assert_remote_artifact_cache()

        if build_all or track_first:
            plan = list(self.dependencies(Scope.ALL))
        else:
            plan = list(self.plan())

        # Assert that we have a consistent pipeline, or that
        # the track option will make it consistent
        if not track_first:
            self.assert_consistent(plan)

        fetch = FetchQueue(skip_cached=True)
        build = BuildQueue()
        track = None
        pull = None
        push = None
        queues = []
        if track_first:
            track = TrackQueue()
            queues.append(track)
        if self.artifacts.can_fetch():
            pull = PullQueue()
            queues.append(pull)
        queues.append(fetch)
        queues.append(build)
        if self.artifacts.can_push():
            push = PushQueue()
            queues.append(push)
        queues[0].enqueue(plan)

        self.session_elements = len(plan)

        self.message(self.target, MessageType.START, "Starting build")
        elapsed, status = scheduler.run(queues)
        built = len(build.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Build failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN, "Terminated", elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS, "Build Complete", elapsed=elapsed)

    # checkout()
    #
    # Checkout the pipeline target artifact to the specified directory
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #    force (bool): Force overwrite files which exist in `directory`
    #
    def checkout(self, directory, force):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise PipelineError("Failed to create checkout directory: {}".format(e)) from e

        if not os.access(directory, os.W_OK):
            raise PipelineError("Directory {} not writable".format(directory))

        if not force and os.listdir(directory):
            raise PipelineError("Checkout directory is not empty: {}"
                                .format(directory))

        # BuildStream will one day be able to run host-incompatible binaries
        # by using a QEMU sandbox, but for now we need to disable integration
        # commands for cross-build artifacts.
        can_integrate = (self.context.host_arch == self.context.target_arch)
        if not can_integrate:
            self.message(self.target, MessageType.WARN,
                         "Host-incompatible checkout -- no integration commands can be run")

        # Stage deps into a temporary sandbox first
        with self.target._prepare_sandbox(Scope.RUN, None, integrate=can_integrate) as sandbox:

            # Make copies from the sandbox into to the desired directory
            sandbox_root = sandbox.get_directory()
            with self.target.timed_activity("Copying files to {}".format(directory)):
                try:
                    utils.copy_files(sandbox_root, directory)
                except OSError as e:
                    raise PipelineError("Failed to copy files: {}".format(e)) from e

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
        workdir = os.path.abspath(directory)
        sources = list(self.target.sources())
        source_index = self.validate_workspace_index(source_index)

        # Check directory
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise PipelineError("Failed to create workspace directory: {}".format(e)) from e

        if not force and os.listdir(directory):
            raise PipelineError("Checkout directory is not empty: {}".format(directory))

        # Check for workspace config
        if self.project._get_workspace(self.target.name, source_index):
            raise PipelineError("Workspace '{}' is already defined."
                                .format(self.target.name + " - " + str(source_index)))

        plan = [self.target]

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
                self.message(self.target, MessageType.FAIL, "Tracking failed", elapsed=elapsed)
                raise PipelineError()
            elif status == SchedStatus.TERMINATED:
                self.message(self.target, MessageType.WARN,
                             "Terminated after fetching {} elements".format(fetched),
                             elapsed=elapsed)
                raise PipelineError()
            else:
                self.message(self.target, MessageType.SUCCESS,
                             "Fetched {} elements".format(fetched), elapsed=elapsed)

        if not no_checkout:
            source = sources[source_index]
            with self.target.timed_activity("Staging source to {}".format(directory)):
                if source.get_consistency() != Consistency.CACHED:
                    raise PipelineError("Could not stage uncached source. " +
                                        "Use `--track` to track and " +
                                        "fetch the latest version of the " +
                                        "source.")
                source._stage(directory)

        self.project._set_workspace(self.target, source_index, workdir)

        with self.target.timed_activity("Saving workspace configuration"):
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
        source_index = self.validate_workspace_index(source_index)

        # Remove workspace directory if prompted
        if remove_dir:
            path = self.project._get_workspace(self.target.name, source_index)
            if path is not None:
                with self.target.timed_activity("Removing workspace directory {}"
                                                .format(path)):
                    try:
                        shutil.rmtree(path)
                    except OSError as e:
                        raise PipelineError("Could not remove  '{}': {}"
                                            .format(path, e)) from e

        # Delete the workspace config entry
        with self.target.timed_activity("Removing workspace"):
            try:
                self.project._delete_workspace(self.target.name, source_index)
            except KeyError:
                raise PipelineError("Workspace '{}' is currently not defined"
                                    .format(self.target.name + " - " + str(source_index)))

        # Update workspace config
        self.project._save_workspace_config()

        # Reset source to avoid checking out the (now empty) workspace
        source = list(self.target.sources())[source_index]
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
        source_index = self.validate_workspace_index(source_index)
        workspace_dir = self.project._get_workspace(self.target.name, source_index)

        if workspace_dir is None:
            raise PipelineError("Workspace '{}' is currently not defined"
                                .format(self.target.name + " - " + str(source_index)))

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

        if not self.artifacts.can_fetch():
            self.message(self.target, MessageType.FAIL, "Not configured for pulling artifacts")

        plan = elements
        self.assert_consistent(plan)
        self.session_elements = len(plan)

        pull = PullQueue()
        pull.enqueue(plan)
        queues = [pull]

        self.message(self.target, MessageType.START, "Pulling {} artifacts".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        pulled = len(pull.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Pull failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after pulling {} elements".format(pulled),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
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

        if not self.artifacts.can_push():
            self.message(self.target, MessageType.FAIL, "Not configured for pushing artifacts")

        plan = elements
        self.assert_consistent(plan)
        self.session_elements = len(plan)

        push = PushQueue()
        push.enqueue(plan)
        queues = [push]

        self.message(self.target, MessageType.START, "Pushing {} artifacts".format(len(plan)))
        elapsed, status = scheduler.run(queues)
        pushed = len(push.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Push failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after pushing {} elements".format(pushed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
                         "Pushed {} complete".format(pushed),
                         elapsed=elapsed)

    # remove_elements():
    #
    # Internal function
    #
    # Returns all elements to be removed from the given list of
    # elements when the given removed elements and their unique
    # dependencies are removed.
    #
    # Args:
    #    elements (list of elements): The graph to sever elements from.
    #    removed (list of strings): Names of the elements to remove.
    def remove_elements(self, tree, removed):

        if removed is None:
            removed = []

        to_remove = set()
        tree = list(tree)

        # Find all elements that might need to be removed.
        def search_tree(element_name):
            for element in tree:
                if element.name == element_name:
                    return element
            return None

        for element_name in removed:
            element = search_tree(element_name)
            if element is None:
                raise PipelineError("No element named {}".format(element_name))

            to_remove.update(element.dependencies(Scope.ALL))

        old_to_remove = set()
        while old_to_remove != to_remove:
            old_to_remove = to_remove

            # Of these, find all elements that are not a dependency of
            # elements still in use.
            for element in tree:
                if element.name not in removed and element not in to_remove:
                    to_remove = to_remove.difference(element.dependencies(Scope.ALL, recurse=False))

            to_remove = to_remove.union([e for e in tree if e.name in removed])

        return [element for element in tree if element not in to_remove]

    def validate_workspace_index(self, source_index):
        sources = list(self.target.sources())

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
    def deps_elements(self, mode, except_=None):

        elements = None
        if mode == 'none':
            elements = [self.target]
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

        return self.remove_elements(elements, except_)

    # source_bundle()
    #
    # Create a build bundle for the given artifact.
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #
    def source_bundle(self, scheduler, dependencies, force,
                      track_first, compression, except_, directory):

        # Find the correct filename for the compression algorithm
        tar_location = os.path.join(directory, self.target.normal_name + ".tar")
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
        builddir = self.target.get_context().builddir
        prefix = "{}-".format(self.target.normal_name)

        with TemporaryDirectory(prefix=prefix, dir=builddir) as tempdir:
            source_directory = os.path.join(tempdir, 'source')
            try:
                os.makedirs(source_directory)
            except e:
                raise PipelineError("Failed to create directory: {}"
                                    .format(e)) from e

            for element in plan:
                try:
                    element._write_script(source_directory)
                except ImplError:
                    # Any elements that don't implement _write_script
                    # should not be included in the later stages.
                    plan.remove(element)

            self._write_element_sources(tempdir, plan)
            self._write_build_script(tempdir, plan)
            self._collect_sources(tempdir, tar_location,
                                  self.target.normal_name, compression)

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

        with open(script_path, "w") as script:
            script.write(script_template.format(modules=module_string))

        os.chmod(script_path, stat.S_IEXEC | stat.S_IREAD)

    # Collect the sources in the given sandbox into a tarfile
    def _collect_sources(self, directory, tar_name, element_name, compression):
        with self.target.timed_activity("Creating tarball {}".format(tar_name)):
            if compression == "none":
                permissions = "w:"
            else:
                permissions = "w:" + compression

            with tarfile.open(tar_name, permissions) as tar:
                tar.add(directory, arcname=element_name)
