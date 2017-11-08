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
import itertools
from operator import itemgetter
from tempfile import TemporaryDirectory
from pluginbase import PluginBase

from ._exceptions import PipelineError, ArtifactError, ImplError
from ._message import Message, MessageType
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from . import Consistency
from . import Scope
from . import _site
from . import _yaml, utils
from ._platform import Platform
from .element import Element

from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue


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

    def plan(self, roots):
        for root in roots:
            self.plan_element(root, 0)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)
        return [item[0] for item in depth_sorted if not item[0]._cached()]


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

    def __init__(self, context, project, targets, except_,
                 inconsistent=False,
                 rewritable=False,
                 use_remote_cache=False,
                 load_ticker=None,
                 resolve_ticker=None,
                 remote_ticker=None,
                 cache_ticker=None):
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
        meta_elements = loader.load(rewritable, load_ticker)
        if load_ticker:
            load_ticker(None)

        # Create the factories after resolving the project
        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase, project._plugin_element_paths)
        self.source_factory = SourceFactory(pluginbase, project._plugin_source_paths)

        # Resolve the real elements now that we've resolved the project
        resolved_elements = [self.resolve(meta_element, ticker=resolve_ticker)
                             for meta_element in meta_elements]

        self.targets = resolved_elements[:len(targets)]
        self.exceptions = resolved_elements[len(targets):]

        if resolve_ticker:
            resolve_ticker(None)

        # Preflight directly after resolving elements, before ever interrogating
        # caches or anything.
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            plugin.preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        for element_name, source, workspace in project._list_workspaces():
            for target in self.targets:
                element = target.search(Scope.ALL, element_name)

                if element is None:
                    self.unused_workspaces.append((element_name, source, workspace))
                    continue

                self.project._set_workspace(element, source, workspace)

        if use_remote_cache and self.artifacts.can_fetch():
            try:
                if remote_ticker:
                    remote_ticker(self.artifacts.url)
                self.artifacts.initialize_remote()
                self.artifacts.fetch_remote_refs()
            except ArtifactError:
                self.message(MessageType.WARN, "Failed to fetch remote refs")
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
            self.message(MessageType.ERROR, "Inconsistent pipeline", detail=detail)
            raise PipelineError()

    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def plan(self):
        build_plan = Planner().plan(self.targets)
        self.remove_elements(build_plan)

        for element in build_plan:
            yield element

    # Local message propagator
    #
    def message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context._message(
            Message(None, message_type, message, **args))

    # Internal: Instantiates plugin-provided Element and Source instances
    # from MetaElement and MetaSource objects
    #
    def resolve(self, meta_element, ticker=None):
        if meta_element in self._resolved_elements:
            return self._resolved_elements[meta_element]

        if ticker:
            ticker(meta_element.name)

        element = self.element_factory.create(meta_element.kind,
                                              self.context,
                                              self.project,
                                              self.artifacts,
                                              meta_element)

        self._resolved_elements[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self.resolve(dep, ticker=ticker), Scope.RUN)
        for dep in meta_element.build_dependencies:
            element._add_dependency(self.resolve(dep, ticker=ticker), Scope.BUILD)

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
        track = TrackQueue()
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
            self.message(MessageType.WARN, "Unused workspaces",
                         detail="\n".join([el + "-" + str(src) for el, src, _
                                           in self.unused_workspaces]))

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

        self.message(MessageType.START, "Starting build")
        elapsed, status = scheduler.run(queues)
        built = len(build.processed_elements)

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
    #
    def checkout(self, directory, force, integrate):
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

            # Make copies from the sandbox into to the desired directory
            sandbox_root = sandbox.get_directory()
            with target.timed_activity("Copying files to {}".format(directory)):
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

        if not self.artifacts.can_fetch():
            raise PipelineError("Not configured for pulling artifacts")

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

        if not self.artifacts.can_push():
            raise PipelineError("Not configured for pushing artifacts")

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
    def deps_elements(self, mode, except_=None):

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
            except e:
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

        with open(script_path, "w") as script:
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
