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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import sys
import stat
import shlex
import shutil
import tarfile
import tempfile
from contextlib import contextmanager, suppress
from fnmatch import fnmatch
from collections import deque
from typing import List, Tuple

from ._artifactelement import verify_artifact_ref, ArtifactElement
from ._exceptions import StreamError, ImplError, BstError, ArtifactElementError, ArtifactError
from ._message import Message, MessageType
from ._scheduler import (
    Scheduler,
    SchedStatus,
    TrackQueue,
    FetchQueue,
    SourcePushQueue,
    BuildQueue,
    PullQueue,
    ArtifactPushQueue,
)
from .element import Element
from ._pipeline import Pipeline
from ._profile import Topics, PROFILER
from ._state import State
from .types import _KeyStrength, _PipelineSelection, _SchedulerErrorAction
from .plugin import Plugin
from . import utils, _yaml, _site
from . import Scope


# Stream()
#
# This is the main, toplevel calling interface in BuildStream core.
#
# Args:
#    context (Context): The Context object
#    session_start (datetime): The time when the session started
#    session_start_callback (callable): A callback to invoke when the session starts
#    interrupt_callback (callable): A callback to invoke when we get interrupted
#    ticker_callback (callable): Invoked every second while running the scheduler
#
class Stream:
    def __init__(
        self, context, session_start, *, session_start_callback=None, interrupt_callback=None, ticker_callback=None
    ):

        #
        # Public members
        #
        self.targets = []  # Resolved target elements
        self.session_elements = []  # List of elements being processed this session
        self.total_elements = []  # Total list of elements based on targets
        self.queues = []  # Queue objects

        #
        # Private members
        #
        self._context = context
        self._artifacts = None
        self._sourcecache = None
        self._project = None
        self._pipeline = None
        self._state = State(session_start)  # Owned by Stream, used by Core to set state
        self._notification_queue = deque()

        context.messenger.set_state(self._state)

        self._scheduler = Scheduler(context, session_start, self._state, interrupt_callback, ticker_callback)
        self._session_start_callback = session_start_callback
        self._running = False
        self._terminated = False
        self._suspended = False

    # init()
    #
    # Initialization of Stream that has side-effects that require it to be
    # performed after the Stream is created.
    #
    def init(self):
        self._artifacts = self._context.artifactcache
        self._sourcecache = self._context.sourcecache

    # cleanup()
    #
    # Cleans up application state
    #
    def cleanup(self):
        if self._project:
            self._project.cleanup()

    # set_project()
    #
    # Set the top-level project.
    #
    # Args:
    #    project (Project): The Project object
    #
    def set_project(self, project):
        assert self._project is None
        self._project = project
        self._project.load_context.set_fetch_subprojects(self._fetch_subprojects)
        self._pipeline = Pipeline(self._context, project, self._artifacts)

    # load_selection()
    #
    # An all purpose method for loading a selection of elements, this
    # is primarily useful for the frontend to implement `bst show`
    # and `bst shell`.
    #
    # Args:
    #    targets (list of str): Targets to pull
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from fetching
    #    use_artifact_config (bool): If artifact remote configs should be loaded
    #
    # Returns:
    #    (list of Element): The selected elements
    def load_selection(
        self,
        targets,
        *,
        selection=_PipelineSelection.NONE,
        except_targets=(),
        use_artifact_config=False,
        load_refs=False
    ):
        with PROFILER.profile(Topics.LOAD_SELECTION, "_".join(t.replace(os.sep, "-") for t in targets)):
            target_objects = self._load(
                targets,
                selection=selection,
                except_targets=except_targets,
                use_artifact_config=use_artifact_config,
                load_refs=load_refs,
            )

            return target_objects

    # shell()
    #
    # Run a shell
    #
    # Args:
    #    element (Element): An Element object to run the shell for
    #    scope (Scope): The scope for the shell (Scope.BUILD or Scope.RUN)
    #    prompt (str): The prompt to display in the shell
    #    mounts (list of HostMount): Additional directories to mount into the sandbox
    #    isolate (bool): Whether to isolate the environment like we do in builds
    #    command (list): An argv to launch in the sandbox, or None
    #    usebuildtree (str): Whether to use a buildtree as the source, given cli option
    #    pull_dependencies ([Element]|None): Elements to attempt to pull
    #    unique_id: (str): Whether to use a unique_id to load an Element instance
    #
    # Returns:
    #    (int): The exit code of the launched shell
    #
    def shell(
        self,
        element,
        scope,
        prompt,
        *,
        mounts=None,
        isolate=False,
        command=None,
        usebuildtree=None,
        pull_dependencies=None,
        unique_id=None
    ):

        # Load the Element via the unique_id if given
        if unique_id and element is None:
            element = Plugin._lookup(unique_id)

        missing_deps = [dep for dep in self._pipeline.dependencies([element], scope) if not dep._cached()]
        if missing_deps:
            if not pull_dependencies:
                raise StreamError(
                    "Elements need to be built or downloaded before staging a shell environment",
                    detail="\n".join(list(map(lambda x: x._get_full_name(), missing_deps))),
                )
            self._message(MessageType.INFO, "Attempting to fetch missing or incomplete artifacts")
            self._scheduler.clear_queues()
            self._add_queue(PullQueue(self._scheduler))
            plan = self._pipeline.add_elements([element], missing_deps)
            self._enqueue_plan(plan)
            self._run()

        buildtree = False
        # Check if we require a pull queue attempt, with given artifact state and context
        if usebuildtree:
            if not element._cached_buildtree():
                require_buildtree = self._buildtree_pull_required([element])
                # Attempt a pull queue for the given element if remote and context allow it
                if require_buildtree:
                    self._message(MessageType.INFO, "Attempting to fetch missing artifact buildtree")
                    self._scheduler.clear_queues()
                    self._add_queue(PullQueue(self._scheduler))
                    self._enqueue_plan(require_buildtree)
                    self._run()
                    # Now check if the buildtree was successfully fetched
                    if element._cached_buildtree():
                        buildtree = True

                if not buildtree:
                    message = "Buildtree is not cached locally or in available remotes"
                    if usebuildtree == "always":
                        raise StreamError(message)

                    self._message(MessageType.INFO, message + ", shell will be loaded without it")
            else:
                buildtree = True

        # Ensure we have our sources if we are launching a build shell
        if scope == Scope.BUILD and not buildtree:
            self._fetch([element])
            self._pipeline.assert_sources_cached([element])

        return element._shell(
            scope, mounts=mounts, isolate=isolate, prompt=prompt, command=command, usebuildtree=buildtree
        )

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    targets (list of str): Targets to build
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    ignore_junction_targets (bool): Whether junction targets should be filtered out
    #    remote (str): The URL of a specific remote server to push to, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to push artifacts to.
    #
    def build(self, targets, *, selection=_PipelineSelection.PLAN, ignore_junction_targets=False, remote=None):

        use_config = True
        if remote:
            use_config = False

        elements = self._load(
            targets,
            selection=selection,
            ignore_junction_targets=ignore_junction_targets,
            use_artifact_config=use_config,
            artifact_remote_url=remote,
            use_source_config=True,
            dynamic_plan=True,
        )

        # Assert that the elements are consistent
        self._pipeline.assert_consistent(elements)

        if all(project.remote_execution_specs for project in self._context.get_projects()):
            # Remote execution is configured for all projects.
            # Require artifact files only for target elements and their runtime dependencies.
            self._context.set_artifact_files_optional()

            # fetch blobs of targets if options set
            if self._context.pull_artifact_files:
                scope = Scope.ALL if selection == _PipelineSelection.ALL else Scope.RUN
                for element in self.targets:
                    element._set_artifact_files_required(scope=scope)

        # Now construct the queues
        #
        self._scheduler.clear_queues()

        if self._artifacts.has_fetch_remotes():
            self._add_queue(PullQueue(self._scheduler))

        self._add_queue(FetchQueue(self._scheduler, skip_cached=True))

        self._add_queue(BuildQueue(self._scheduler))

        if self._artifacts.has_push_remotes():
            self._add_queue(ArtifactPushQueue(self._scheduler))

        if self._sourcecache.has_push_remotes():
            self._add_queue(SourcePushQueue(self._scheduler))

        # Enqueue elements
        self._enqueue_plan(elements)
        self._run(announce_session=True)

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    targets (list of str): Targets to fetch
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from fetching
    #    remote (str|None): The URL of a specific remote server to pull from.
    #
    def fetch(self, targets, *, selection=_PipelineSelection.PLAN, except_targets=None, remote=None):

        use_source_config = True
        if remote:
            use_source_config = False

        elements = self._load(
            targets,
            selection=selection,
            except_targets=except_targets,
            use_source_config=use_source_config,
            source_remote_url=remote,
        )

        # Delegated to a shared fetch method
        self._fetch(elements, announce_session=True)

    # track()
    #
    # Tracks all the sources of the selected elements.
    #
    # Args:
    #    targets (list of str): Targets to track
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from tracking
    #    cross_junctions (bool): Whether tracking should cross junction boundaries
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, targets, *, selection=_PipelineSelection.REDIRECT, except_targets=None, cross_junctions=False):

        elements = self._load_tracking(
            targets, selection=selection, except_targets=except_targets, cross_junctions=cross_junctions
        )

        # Note: We do not currently need to initialize the state of an
        # element before it is tracked, since tracking can be done
        # irrespective of source/artifact condition. Once an element
        # is tracked, its state must be fully updated in either case,
        # and we anyway don't do anything else with it.

        self._scheduler.clear_queues()
        track_queue = TrackQueue(self._scheduler)
        self._add_queue(track_queue, track=True)
        self._enqueue_plan(elements, queue=track_queue)
        self._run(announce_session=True)

    # source_push()
    #
    # Push sources.
    #
    # Args:
    #    targets (list of str): Targets to push
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    remote (str): The URL of a specific remote server to push to, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to push sources to.
    #
    # If any of the given targets are missing their expected sources,
    # a fetch queue will be created if user context and available remotes allow for
    # attempting to fetch them.
    #
    def source_push(self, targets, *, selection=_PipelineSelection.NONE, remote=None):

        use_source_config = True
        if remote:
            use_source_config = False

        elements = self._load(
            targets,
            selection=selection,
            use_source_config=use_source_config,
            source_remote_url=remote,
            load_refs=True,
        )

        if not self._sourcecache.has_push_remotes():
            raise StreamError("No source caches available for pushing sources")

        self._pipeline.assert_consistent(elements)

        self._add_queue(FetchQueue(self._scheduler, skip_cached=True))

        self._add_queue(SourcePushQueue(self._scheduler))

        self._enqueue_plan(elements)
        self._run(announce_session=True)

    # pull()
    #
    # Pulls artifacts from remote artifact server(s)
    #
    # Args:
    #    targets (list of str): Targets to pull
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    ignore_junction_targets (bool): Whether junction targets should be filtered out
    #    remote (str): The URL of a specific remote server to pull from, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to pull artifacts from.
    #
    def pull(self, targets, *, selection=_PipelineSelection.NONE, ignore_junction_targets=False, remote=None):

        use_config = True
        if remote:
            use_config = False

        elements = self._load(
            targets,
            selection=selection,
            ignore_junction_targets=ignore_junction_targets,
            use_artifact_config=use_config,
            artifact_remote_url=remote,
            load_refs=True,
        )

        if not self._artifacts.has_fetch_remotes():
            raise StreamError("No artifact caches available for pulling artifacts")

        self._pipeline.assert_consistent(elements)
        self._scheduler.clear_queues()
        self._add_queue(PullQueue(self._scheduler))
        self._enqueue_plan(elements)
        self._run(announce_session=True)

    # push()
    #
    # Pulls artifacts to remote artifact server(s)
    #
    # Args:
    #    targets (list of str): Targets to push
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    ignore_junction_targets (bool): Whether junction targets should be filtered out
    #    remote (str): The URL of a specific remote server to push to, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to push artifacts to.
    #
    # If any of the given targets are missing their expected buildtree artifact,
    # a pull queue will be created if user context and available remotes allow for
    # attempting to fetch them.
    #
    def push(self, targets, *, selection=_PipelineSelection.NONE, ignore_junction_targets=False, remote=None):

        use_config = True
        if remote:
            use_config = False

        elements = self._load(
            targets,
            selection=selection,
            ignore_junction_targets=ignore_junction_targets,
            use_artifact_config=use_config,
            artifact_remote_url=remote,
            load_refs=True,
        )

        if not self._artifacts.has_push_remotes():
            raise StreamError("No artifact caches available for pushing artifacts")

        self._pipeline.assert_consistent(elements)

        # Check if we require a pull queue, with given artifact state and context
        require_buildtrees = self._buildtree_pull_required(elements)
        if require_buildtrees:
            self._message(MessageType.INFO, "Attempting to fetch missing artifact buildtrees")
            self._add_queue(PullQueue(self._scheduler))
            self._enqueue_plan(require_buildtrees)

        # Before we try to push the artifacts, ensure they're cached
        cached_elements = []
        uncached_elements = []
        self._message(MessageType.INFO, "Verifying that elements are cached")
        for element in elements:
            if element._cached():
                cached_elements.append(element)
            else:
                msg = "{} is not cached".format(element.name)
                if self._context.sched_error_action != _SchedulerErrorAction.CONTINUE:
                    raise StreamError("Push failed: " + msg)

                self._message(MessageType.WARN, msg)
                uncached_elements.append(element)

        if cached_elements:
            self._scheduler.clear_queues()
            push_queue = ArtifactPushQueue(self._scheduler)
            self._add_queue(push_queue)
            self._enqueue_plan(cached_elements, queue=push_queue)
            self._run(announce_session=True)

        # If the user has selected to continue on error, fail the command
        # and print a summary of artifacts which could not be pushed
        #
        # NOTE: Usually we check the _SchedulerErrorAction when a *job* has failed.
        #       However, we cannot create a PushQueue job unless we intentionally
        #       ready an uncached element in the PushQueue.
        if self._context.sched_error_action == _SchedulerErrorAction.CONTINUE and uncached_elements:
            names = [element.name for element in uncached_elements]
            fail_str = (
                "Error while pushing. The following elements were not pushed as they are "
                "not yet cached:\n\n\t{}\n".format("\n\t".join(names))
            )

            raise StreamError(fail_str)

    # checkout()
    #
    # Checkout target artifact to the specified location
    #
    # Args:
    #    target (str): Target to checkout
    #    location (str): Location to checkout the artifact to
    #    force (bool): Whether files can be overwritten if necessary
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    integrate (bool): Whether to run integration commands
    #    hardlinks (bool): Whether checking out files hardlinked to
    #                      their artifacts is acceptable
    #    tar (bool): If true, a tarball from the artifact contents will
    #                be created, otherwise the file tree of the artifact
    #                will be placed at the given location. If true and
    #                location is '-', the tarball will be dumped on the
    #                standard output.
    #    pull (bool): If true will attempt to pull any missing or incomplete
    #                 artifacts.
    #
    def checkout(
        self,
        target,
        *,
        location=None,
        force=False,
        selection=_PipelineSelection.RUN,
        integrate=True,
        hardlinks=False,
        compression="",
        pull=False,
        tar=False
    ):

        elements = self._load((target,), selection=selection, use_artifact_config=True, load_refs=True)

        # self.targets contains a list of the loaded target objects
        # if we specify --deps build, Stream._load() will return a list
        # of build dependency objects, however, we need to prepare a sandbox
        # with the target (which has had its appropriate dependencies loaded)
        target = self.targets[0]

        self._check_location_writable(location, force=force, tar=tar)

        uncached_elts = [elt for elt in elements if not elt._cached()]
        if uncached_elts and pull:
            self._message(MessageType.INFO, "Attempting to fetch missing or incomplete artifact")
            self._scheduler.clear_queues()
            self._add_queue(PullQueue(self._scheduler))
            self._enqueue_plan(uncached_elts)
            self._run(announce_session=True)

        try:
            scope = {
                _PipelineSelection.RUN: Scope.RUN,
                _PipelineSelection.BUILD: Scope.BUILD,
                _PipelineSelection.NONE: Scope.NONE,
                _PipelineSelection.ALL: Scope.ALL,
            }
            with target._prepare_sandbox(scope=scope[selection], integrate=integrate) as sandbox:
                # Copy or move the sandbox to the target directory
                virdir = sandbox.get_virtual_directory()
                self._export_artifact(tar, location, compression, target, hardlinks, virdir)
        except BstError as e:
            raise StreamError(
                "Error while staging dependencies into a sandbox" ": '{}'".format(e), detail=e.detail, reason=e.reason
            ) from e

    # _export_artifact()
    #
    # Export the files of the artifact/a tarball to a virtual directory
    #
    # Args:
    #    tar (bool): Whether we want to create a tarfile
    #    location (str): The name of the directory/the tarfile we want to export to/create
    #    compression (str): The type of compression for the tarball
    #    target (Element/ArtifactElement): The Element/ArtifactElement we want to checkout
    #    hardlinks (bool): Whether to checkout hardlinks instead of copying
    #    virdir (Directory): The sandbox's root directory as a virtual directory
    #
    def _export_artifact(self, tar, location, compression, target, hardlinks, virdir):
        if not tar:
            with target.timed_activity("Checking out files in '{}'".format(location)):
                try:
                    if hardlinks:
                        self._checkout_hardlinks(virdir, location)
                    else:
                        virdir.export_files(location)
                except OSError as e:
                    raise StreamError("Failed to checkout files: '{}'".format(e)) from e
        else:
            to_stdout = location == "-"
            mode = _handle_compression(compression, to_stream=to_stdout)
            with target.timed_activity("Creating tarball"):
                if to_stdout:
                    # Save the stdout FD to restore later
                    saved_fd = os.dup(sys.stdout.fileno())
                    try:
                        with os.fdopen(sys.stdout.fileno(), "wb") as fo:
                            with tarfile.open(fileobj=fo, mode=mode) as tf:
                                virdir.export_to_tar(tf, ".")
                    finally:
                        # No matter what, restore stdout for further use
                        os.dup2(saved_fd, sys.stdout.fileno())
                        os.close(saved_fd)
                else:
                    with tarfile.open(location, mode=mode) as tf:
                        virdir.export_to_tar(tf, ".")

    # artifact_show()
    #
    # Show cached artifacts
    #
    # Args:
    #    targets (str): Targets to show the cached state of
    #
    def artifact_show(self, targets, *, selection=_PipelineSelection.NONE):
        # Obtain list of Element and/or ArtifactElement objects
        target_objects = self.load_selection(targets, selection=selection, use_artifact_config=True, load_refs=True)

        if self._artifacts.has_fetch_remotes():
            self._pipeline.check_remotes(target_objects)

        # XXX: We need to set the name of an ArtifactElement to its ref in order
        #      to display the expected result in the frontend
        for obj in target_objects:
            if isinstance(obj, ArtifactElement):
                obj.name = obj.get_artifact_name()

        return target_objects

    # artifact_log()
    #
    # Show the full log of an artifact
    #
    # Args:
    #    targets (str): Targets to view the logs of
    #
    # Returns:
    #    logsdir (list): A list of CasBasedDirectory objects containing artifact logs
    #
    def artifact_log(self, targets):
        # Return list of Element and/or ArtifactElement objects
        target_objects = self.load_selection(targets, selection=_PipelineSelection.NONE, load_refs=True)

        artifact_logs = {}
        for obj in target_objects:
            ref = obj.get_artifact_name()
            if not obj._cached():
                self._message(MessageType.WARN, "{} is not cached".format(ref))
                continue
            if not obj._cached_logs():
                self._message(MessageType.WARN, "{} is cached without log files".format(ref))
                continue

            artifact_logs[obj.name] = obj.get_logs()

        return artifact_logs

    # artifact_list_contents()
    #
    # Show a list of content of an artifact
    #
    # Args:
    #    targets (str): Targets to view the contents of
    #
    # Returns:
    #    elements_to_files (list): A list of tuples of the artifact name and it's contents
    #
    def artifact_list_contents(self, targets):
        # Return list of Element and/or ArtifactElement objects
        target_objects = self.load_selection(targets, selection=_PipelineSelection.NONE, load_refs=True)

        elements_to_files = {}
        for obj in target_objects:
            ref = obj.get_artifact_name()
            if not obj._cached():
                self._message(MessageType.WARN, "{} is not cached".format(ref))
                obj.name = {ref: "No artifact cached"}
                continue
            if isinstance(obj, ArtifactElement):
                obj.name = ref
            files = list(obj._walk_artifact_files())
            elements_to_files[obj.name] = files
        return elements_to_files

    # artifact_delete()
    #
    # Remove artifacts from the local cache
    #
    # Args:
    #    targets (str): Targets to remove
    #
    def artifact_delete(self, targets, *, selection=_PipelineSelection.NONE):
        # Return list of Element and/or ArtifactElement objects
        target_objects = self.load_selection(targets, selection=selection, load_refs=True)

        # Some of the targets may refer to the same key, so first obtain a
        # set of the refs to be removed.
        remove_refs = set()
        for obj in target_objects:
            for key_strength in [_KeyStrength.STRONG, _KeyStrength.WEAK]:
                key = obj._get_cache_key(strength=key_strength)
                remove_refs.add(obj.get_artifact_name(key=key))

        ref_removed = False
        for ref in remove_refs:
            try:
                self._artifacts.remove(ref)
            except ArtifactError as e:
                self._message(MessageType.WARN, str(e))
                continue

            self._message(MessageType.INFO, "Removed: {}".format(ref))
            ref_removed = True

        if not ref_removed:
            self._message(MessageType.INFO, "No artifacts were removed")

    # source_checkout()
    #
    # Checkout sources of the target element to the specified location
    #
    # Args:
    #    target (str): The target element whose sources to checkout
    #    location (str): Location to checkout the sources to
    #    force (bool): Whether to overwrite existing directories/tarfiles
    #    deps (str): The dependencies to checkout
    #    except_targets ([str]): List of targets to except from staging
    #    tar (bool): Whether to write a tarfile holding the checkout contents
    #    compression (str): The type of compression for tarball
    #    include_build_scripts (bool): Whether to include build scripts in the checkout
    #
    def source_checkout(
        self,
        target,
        *,
        location=None,
        force=False,
        deps="none",
        except_targets=(),
        tar=False,
        compression=None,
        include_build_scripts=False
    ):

        self._check_location_writable(location, force=force, tar=tar)

        elements = self._load((target,), selection=deps, except_targets=except_targets)

        # Assert all sources are cached in the source dir
        self._fetch(elements)
        self._pipeline.assert_sources_cached(elements)

        # Stage all sources determined by scope
        try:
            self._source_checkout(elements, location, force, deps, tar, compression, include_build_scripts)
        except BstError as e:
            raise StreamError(
                "Error while writing sources" ": '{}'".format(e), detail=e.detail, reason=e.reason
            ) from e

        self._message(MessageType.INFO, "Checked out sources to '{}'".format(location))

    # workspace_open
    #
    # Open a project workspace
    #
    # Args:
    #    targets (list): List of target elements to open workspaces for
    #    no_checkout (bool): Whether to skip checking out the source
    #    force (bool): Whether to ignore contents in an existing directory
    #    custom_dir (str): Custom location to create a workspace or false to use default location.
    #
    def workspace_open(self, targets, *, no_checkout, force, custom_dir):
        # This function is a little funny but it is trying to be as atomic as possible.

        elements = self._load(targets, selection=_PipelineSelection.REDIRECT)

        workspaces = self._context.get_workspaces()

        # If we're going to checkout, we need at least a fetch,
        #
        if not no_checkout:
            self._fetch(elements, fetch_original=True)

        expanded_directories = []
        #  To try to be more atomic, loop through the elements and raise any errors we can early
        for target in elements:

            if not list(target.sources()):
                build_depends = [x.name for x in target.dependencies(Scope.BUILD, recurse=False)]
                if not build_depends:
                    raise StreamError("The element {}  has no sources".format(target.name))
                detail = "Try opening a workspace on one of its dependencies instead:\n"
                detail += "  \n".join(build_depends)
                raise StreamError("The element {} has no sources".format(target.name), detail=detail)

            # Check for workspace config
            workspace = workspaces.get_workspace(target._get_full_name())
            if workspace:
                if not force:
                    raise StreamError(
                        "Element '{}' already has an open workspace defined at: {}".format(
                            target.name, workspace.get_absolute_path()
                        )
                    )
                if not no_checkout:
                    target.warn(
                        "Replacing existing workspace for element '{}' defined at: {}".format(
                            target.name, workspace.get_absolute_path()
                        )
                    )
                self.workspace_close(target._get_full_name(), remove_dir=not no_checkout)

            if not custom_dir:
                directory = os.path.abspath(os.path.join(self._context.workspacedir, target.name))
                if directory[-4:] == ".bst":
                    directory = directory[:-4]
                expanded_directories.append(directory)

        if custom_dir:
            if len(elements) != 1:
                raise StreamError(
                    "Exactly one element can be given if --directory is used",
                    reason="directory-with-multiple-elements",
                )
            directory = os.path.abspath(custom_dir)
            expanded_directories = [
                directory,
            ]
        else:
            # If this fails it is a bug in what ever calls this, usually cli.py and so can not be tested for via the
            # run bst test mechanism.
            assert len(elements) == len(expanded_directories)

        for target, directory in zip(elements, expanded_directories):
            if os.path.exists(directory):
                if not os.path.isdir(directory):
                    raise StreamError(
                        "For element '{}', Directory path is not a directory: {}".format(target.name, directory),
                        reason="bad-directory",
                    )

                if not (no_checkout or force) and os.listdir(directory):
                    raise StreamError(
                        "For element '{}', Directory path is not empty: {}".format(target.name, directory),
                        reason="bad-directory",
                    )
                if os.listdir(directory):
                    if force and not no_checkout:
                        utils._force_rmtree(directory)

        # So far this function has tried to catch as many issues as possible with out making any changes
        # Now it does the bits that can not be made atomic.
        targetGenerator = zip(elements, expanded_directories)
        for target, directory in targetGenerator:
            self._message(MessageType.INFO, "Creating workspace for element {}".format(target.name))

            workspace = workspaces.get_workspace(target._get_full_name())
            if workspace and not no_checkout:
                workspaces.delete_workspace(target._get_full_name())
                workspaces.save_config()
                utils._force_rmtree(directory)
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                todo_elements = " ".join([str(target.name) for target, directory_dict in targetGenerator])
                if todo_elements:
                    # This output should make creating the remaining workspaces as easy as possible.
                    todo_elements = "\nDid not try to create workspaces for " + todo_elements
                raise StreamError("Failed to create workspace directory: {}".format(e) + todo_elements) from e

            workspaces.create_workspace(target, directory, checkout=not no_checkout)
            self._message(MessageType.INFO, "Created a workspace for element: {}".format(target._get_full_name()))

    # workspace_close
    #
    # Close a project workspace
    #
    # Args:
    #    element_name (str): The element name to close the workspace for
    #    remove_dir (bool): Whether to remove the associated directory
    #
    def workspace_close(self, element_name, *, remove_dir):
        workspaces = self._context.get_workspaces()
        workspace = workspaces.get_workspace(element_name)

        # Remove workspace directory if prompted
        if remove_dir:
            with self._context.messenger.timed_activity(
                "Removing workspace directory {}".format(workspace.get_absolute_path())
            ):
                try:
                    shutil.rmtree(workspace.get_absolute_path())
                except OSError as e:
                    raise StreamError("Could not remove  '{}': {}".format(workspace.get_absolute_path(), e)) from e

        # Delete the workspace and save the configuration
        workspaces.delete_workspace(element_name)
        workspaces.save_config()
        self._message(MessageType.INFO, "Closed workspace for {}".format(element_name))

    # workspace_reset
    #
    # Reset a workspace to its original state, discarding any user
    # changes.
    #
    # Args:
    #    targets (list of str): The target elements to reset the workspace for
    #    soft (bool): Only set the workspace state to not prepared
    #
    def workspace_reset(self, targets, *, soft):

        elements = self._load(targets, selection=_PipelineSelection.REDIRECT)

        nonexisting = []
        for element in elements:
            if not self.workspace_exists(element.name):
                nonexisting.append(element.name)
        if nonexisting:
            raise StreamError("Workspace does not exist", detail="\n".join(nonexisting))

        workspaces = self._context.get_workspaces()
        for element in elements:
            workspace = workspaces.get_workspace(element._get_full_name())
            workspace_path = workspace.get_absolute_path()

            if soft:
                workspace.last_build = None
                self._message(
                    MessageType.INFO, "Reset workspace state for {} at: {}".format(element.name, workspace_path)
                )
                continue

            self.workspace_close(element._get_full_name(), remove_dir=True)
            workspaces.save_config()
            self.workspace_open([element._get_full_name()], no_checkout=False, force=True, custom_dir=workspace_path)

    # workspace_exists
    #
    # Check if a workspace exists
    #
    # Args:
    #    element_name (str): The element name to close the workspace for, or None
    #
    # Returns:
    #    (bool): True if the workspace exists
    #
    # If None is specified for `element_name`, then this will return
    # True if there are any existing workspaces.
    #
    def workspace_exists(self, element_name=None):
        workspaces = self._context.get_workspaces()
        if element_name:
            workspace = workspaces.get_workspace(element_name)
            if workspace:
                return True
        elif any(workspaces.list()):
            return True

        return False

    # workspace_list
    #
    # Serializes the workspaces and dumps them in YAML to stdout.
    #
    def workspace_list(self):
        workspaces = []
        for element_name, workspace_ in self._context.get_workspaces().list():
            workspace_detail = {
                "element": element_name,
                "directory": workspace_.get_absolute_path(),
            }
            workspaces.append(workspace_detail)

        _yaml.roundtrip_dump({"workspaces": workspaces})

    # redirect_element_names()
    #
    # Takes a list of element names and returns a list where elements have been
    # redirected to their source elements if the element file exists, and just
    # the name, if not.
    #
    # Args:
    #    elements (list of str): The element names to redirect
    #
    # Returns:
    #    (list of str): The element names after redirecting
    #
    def redirect_element_names(self, elements):
        element_dir = self._project.element_path
        load_elements = []
        output_elements = set()

        for e in elements:
            element_path = os.path.join(element_dir, e)
            if os.path.exists(element_path):
                load_elements.append(e)
            else:
                output_elements.add(e)
        if load_elements:
            loaded_elements = self._load(load_elements, selection=_PipelineSelection.REDIRECT)

            for e in loaded_elements:
                output_elements.add(e.name)

        return list(output_elements)

    # get_state()
    #
    # Get the State object owned by Stream
    #
    # Returns:
    #    State: The State object
    def get_state(self):
        return self._state

    #############################################################
    #                 Scheduler API forwarding                  #
    #############################################################

    # running
    #
    # Whether the scheduler is running
    #
    @property
    def running(self):
        return self._running

    # suspended
    #
    # Whether the scheduler is currently suspended
    #
    @property
    def suspended(self):
        return self._suspended

    # terminated
    #
    # Whether the scheduler is currently terminated
    #
    @property
    def terminated(self):
        return self._terminated

    # terminate()
    #
    # Terminate jobs
    #
    def terminate(self):
        self._scheduler.terminate()
        self._terminated = True

    # quit()
    #
    # Quit the session, this will continue with any ongoing
    # jobs, use Stream.terminate() instead for cancellation
    # of ongoing jobs
    #
    def quit(self):
        self._scheduler.stop()

    # suspend()
    #
    # Context manager to suspend ongoing jobs
    #
    @contextmanager
    def suspend(self):
        self._scheduler.suspend()
        self._suspended = True
        yield
        self._suspended = False
        self._scheduler.resume()

    #############################################################
    #                    Private Methods                        #
    #############################################################

    # _fetch_subprojects()
    #
    # Fetch subprojects as part of the project and element loading process.
    #
    # Args:
    #    junctions (list of Element): The junctions to fetch
    #
    def _fetch_subprojects(self, junctions):
        self._scheduler.clear_queues()
        queue = FetchQueue(self._scheduler)
        queue.enqueue(junctions)
        self.queues = [queue]
        self._run()

    # _load_elements_from_targets
    #
    # Given the usual set of target element names/artifact refs, load
    # the `Element` objects required to describe the selection.
    #
    # The result is returned as a truple - firstly the loaded normal
    # elements, secondly the loaded "excepting" elements and lastly
    # the loaded artifact elements.
    #
    # Args:
    #     targets - The target element names/artifact refs
    #     except_targets - The names of elements to except
    #     rewritable - Whether to load the elements in re-writable mode
    #
    # Returns:
    #     ([elements], [except_elements], [artifact_elements])
    #
    def _load_elements_from_targets(
        self, targets: List[str], except_targets: List[str], *, rewritable: bool = False
    ) -> Tuple[List[Element], List[Element], List[Element]]:
        names, refs = self._classify_artifacts(targets)
        loadable = [names, except_targets]

        self._project.load_context.set_rewritable(rewritable)

        # Load and filter elements
        if loadable:
            elements, except_elements = self._pipeline.load(loadable)
        else:
            elements, except_elements = [], []

        # Load artifacts
        if refs:
            artifacts = self._pipeline.load_artifacts(refs)
        else:
            artifacts = []

        return elements, except_elements, artifacts

    # _connect_remotes()
    #
    # Connect to the source and artifact remotes.
    #
    # Args:
    #     artifact_url - The url of the artifact server to connect to.
    #     source_url - The url of the source server to connect to.
    #     use_artifact_config - Whether to use the artifact config.
    #     use_source_config - Whether to use the source config.
    #
    def _connect_remotes(self, artifact_url: str, source_url: str, use_artifact_config: bool, use_source_config: bool):
        # ArtifactCache.setup_remotes expects all projects to be fully loaded
        for project in self._context.get_projects():
            project.ensure_fully_loaded()

        # Connect to remote caches, this needs to be done before resolving element state
        self._artifacts.setup_remotes(use_config=use_artifact_config, remote_url=artifact_url)
        self._sourcecache.setup_remotes(use_config=use_source_config, remote_url=source_url)

    # _load_tracking()
    #
    # A variant of _load() to be used when the elements should be used
    # for tracking
    #
    # If `targets` is not empty used project configuration will be
    # fully loaded.
    #
    # Args:
    #    targets (list of str): Targets to load
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except
    #    cross_junctions (bool): Whether tracking should cross junction boundaries
    #
    # Returns:
    #    (list of Element): The tracking element selection
    #
    def _load_tracking(self, targets, *, selection=_PipelineSelection.NONE, except_targets=(), cross_junctions=False):
        # We never want to use a PLAN selection when tracking elements
        assert selection != _PipelineSelection.PLAN

        elements, except_elements, artifacts = self._load_elements_from_targets(
            targets, except_targets, rewritable=True
        )

        # We can't track artifact refs, since they have no underlying
        # elements or sources to interact with. Abort if the user asks
        # us to do that.
        if artifacts:
            detail = "\n".join(artifact.get_artifact_name() for artifact in artifacts)
            raise ArtifactElementError("Cannot perform this operation with artifact refs:", detail=detail)

        # Hold on to the targets
        self.targets = elements

        track_projects = {}
        for element in elements:
            project = element._get_project()
            if project not in track_projects:
                track_projects[project] = [element]
            else:
                track_projects[project].append(element)

        track_selected = []

        for project, project_elements in track_projects.items():
            selected = self._pipeline.get_selection(project_elements, selection)
            selected = self._pipeline.track_cross_junction_filter(project, selected, cross_junctions)
            track_selected.extend(selected)

        return self._pipeline.except_elements(elements, track_selected, except_elements)

    # _load()
    #
    # A convenience method for loading element lists
    #
    # If `targets` is not empty used project configuration will be
    # fully loaded.
    #
    # Args:
    #    targets (list of str): Main targets to load
    #    selection (_PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from fetching
    #    ignore_junction_targets (bool): Whether junction targets should be filtered out
    #    use_artifact_config (bool): Whether to initialize artifacts with the config
    #    use_source_config (bool): Whether to initialize remote source caches with the config
    #    artifact_remote_url (str): A remote url for initializing the artifacts
    #    source_remote_url (str): A remote url for initializing source caches
    #
    # Returns:
    #    (list of Element): The primary element selection
    #
    def _load(
        self,
        targets,
        *,
        selection=_PipelineSelection.NONE,
        except_targets=(),
        ignore_junction_targets=False,
        use_artifact_config=False,
        use_source_config=False,
        artifact_remote_url=None,
        source_remote_url=None,
        dynamic_plan=False,
        load_refs=False
    ):
        elements, except_elements, artifacts = self._load_elements_from_targets(
            targets, except_targets, rewritable=False
        )

        if artifacts:
            if not load_refs:
                detail = "\n".join(artifact.get_artifact_name() for artifact in artifacts)
                raise ArtifactElementError("Cannot perform this operation with artifact refs:", detail=detail)
            if selection in (_PipelineSelection.ALL, _PipelineSelection.RUN):
                raise StreamError("Error: '--deps {}' is not supported for artifact refs".format(selection.value))

        if ignore_junction_targets:
            elements = [e for e in elements if e.get_kind() != "junction"]

        # Hold on to the targets
        self.targets = elements + artifacts

        # Connect to remote caches, this needs to be done before resolving element state
        self._connect_remotes(artifact_remote_url, source_remote_url, use_artifact_config, use_source_config)

        # Now move on to loading primary selection.
        #
        self._pipeline.resolve_elements(self.targets)
        selected = self._pipeline.get_selection(self.targets, selection, silent=False)
        selected = self._pipeline.except_elements(self.targets, selected, except_elements)

        if selection == _PipelineSelection.PLAN and dynamic_plan:
            # We use a dynamic build plan, only request artifacts of top-level targets,
            # others are requested dynamically as needed.
            # This avoids pulling, fetching, or building unneeded build-only dependencies.
            for element in elements:
                element._set_required()
        else:
            for element in selected:
                element._set_required()

        return selected

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self._context.messenger.message(Message(message_type, message, **args))

    # _add_queue()
    #
    # Adds a queue to the stream
    #
    # Args:
    #    queue (Queue): Queue to add to the pipeline
    #
    def _add_queue(self, queue, *, track=False):
        if not track and not self.queues:
            # First non-track queue
            queue.set_required_element_check()

        self.queues.append(queue)

    # _enqueue_plan()
    #
    # Enqueues planned elements to the specified queue.
    #
    # Args:
    #    plan (list of Element): The list of elements to be enqueued
    #    queue (Queue): The target queue, defaults to the first queue
    #
    def _enqueue_plan(self, plan, *, queue=None):
        queue = queue or self.queues[0]
        queue.enqueue(plan)
        self.session_elements += plan

    # _failure_retry()
    #
    # Enqueues given element via unique_id to the specified queue
    # matched against provided action_name & removes the related
    # failed task from the tasks group.
    #
    # Args:
    #    action_name: The name of the action being performed
    #    unique_id: A unique_id to load an Element instance
    #
    def _failure_retry(self, action_name: str, unique_id: str) -> None:
        self._state.retry_task(action_name, unique_id)

    # _run()
    #
    # Common function for running the scheduler
    #
    # Args:
    #    announce_session (bool): Whether to announce the session in the frontend.
    #
    def _run(self, *, announce_session: bool = False):

        # Inform the frontend of the full list of elements
        # and the list of elements which will be processed in this run
        #
        self.total_elements = list(self._pipeline.dependencies(self.targets, Scope.ALL))

        if announce_session and self._session_start_callback is not None:
            self._session_start_callback()

        self._running = True
        status = self._scheduler.run(self.queues, self._context.get_cascache().get_casd_process_manager())
        self._running = False

        if status == SchedStatus.ERROR:
            raise StreamError()
        if status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

    # _fetch()
    #
    # Performs the fetch job, the body of this function is here because
    # it is shared between a few internals.
    #
    # Args:
    #    elements (list of Element): Elements to fetch
    #    fetch_original (bool): Whether to fetch original unstaged
    #    announce_session (bool): Whether to announce the session in the frontend
    #
    def _fetch(self, elements: List[Element], *, fetch_original: bool = False, announce_session: bool = False):

        # Assert consistency for the fetch elements
        self._pipeline.assert_consistent(elements)

        # Construct queues, enqueue and run
        #
        self._scheduler.clear_queues()
        self._add_queue(FetchQueue(self._scheduler, fetch_original=fetch_original))
        self._enqueue_plan(elements)
        self._run(announce_session=announce_session)

    # _check_location_writable()
    #
    # Check if given location is writable.
    #
    # Args:
    #    location (str): Destination path
    #    force (bool): Allow files to be overwritten
    #    tar (bool): Whether destination is a tarball
    #
    # Raises:
    #    (StreamError): If the destination is not writable
    #
    def _check_location_writable(self, location, force=False, tar=False):
        if not tar:
            try:
                os.makedirs(location, exist_ok=True)
            except OSError as e:
                raise StreamError("Failed to create destination directory: '{}'".format(e)) from e
            if not os.access(location, os.W_OK):
                raise StreamError("Destination directory '{}' not writable".format(location))
            if not force and os.listdir(location):
                raise StreamError("Destination directory '{}' not empty".format(location))
        elif os.path.exists(location) and location != "-":
            if not os.access(location, os.W_OK):
                raise StreamError("Output file '{}' not writable".format(location))
            if not force and os.path.exists(location):
                raise StreamError("Output file '{}' already exists".format(location))

    # Helper function for checkout()
    #
    def _checkout_hardlinks(self, sandbox_vroot, directory):
        try:
            utils.safe_remove(directory)
        except OSError as e:
            raise StreamError("Failed to remove checkout directory: {}".format(e)) from e

        sandbox_vroot.export_files(directory, can_link=True, can_destroy=True)

    # Helper function for source_checkout()
    def _source_checkout(
        self,
        elements,
        location=None,
        force=False,
        deps="none",
        tar=False,
        compression=None,
        include_build_scripts=False,
    ):
        location = os.path.abspath(location)

        # Stage all our sources in a temporary directory. The this
        # directory can be used to either construct a tarball or moved
        # to the final desired location.
        temp_source_dir = tempfile.TemporaryDirectory(dir=self._context.tmpdir)
        try:
            self._write_element_sources(temp_source_dir.name, elements)
            if include_build_scripts:
                self._write_build_scripts(temp_source_dir.name, elements)
            if tar:
                self._create_tarball(temp_source_dir.name, location, compression)
            else:
                self._move_directory(temp_source_dir.name, location, force)
        except OSError as e:
            raise StreamError("Failed to checkout sources to {}: {}".format(location, e)) from e
        finally:
            with suppress(FileNotFoundError):
                temp_source_dir.cleanup()

    # Move a directory src to dest. This will work across devices and
    # may optionaly overwrite existing files.
    def _move_directory(self, src, dest, force=False):
        def is_empty_dir(path):
            return os.path.isdir(dest) and not os.listdir(dest)

        try:
            os.rename(src, dest)
            return
        except OSError:
            pass

        if force or is_empty_dir(dest):
            try:
                utils.link_files(src, dest)
            except utils.UtilError as e:
                raise StreamError("Failed to move directory: {}".format(e)) from e

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
            element_source_dir = self._get_element_dirname(directory, element)
            if list(element.sources()):
                os.makedirs(element_source_dir)
                element._stage_sources_at(element_source_dir)

    # Create a tarball from the content of directory
    def _create_tarball(self, directory, tar_name, compression):
        if compression is None:
            compression = ""
        mode = _handle_compression(compression)
        try:
            with utils.save_file_atomic(tar_name, mode="wb") as f:
                tarball = tarfile.open(fileobj=f, mode=mode)
                for item in os.listdir(str(directory)):
                    file_to_add = os.path.join(directory, item)
                    tarball.add(file_to_add, arcname=item)
                tarball.close()
        except OSError as e:
            raise StreamError("Failed to create tar archive: {}".format(e)) from e

    # Write all the build_scripts for elements in the directory location
    def _write_build_scripts(self, location, elements):
        for element in elements:
            self._write_element_script(location, element)
        self._write_master_build_script(location, elements)

    # Write a master build script to the sandbox
    def _write_master_build_script(self, directory, elements):

        module_string = ""
        for element in elements:
            module_string += shlex.quote(element.normal_name) + " "

        script_path = os.path.join(directory, "build.sh")

        with open(_site.build_all_template, "r") as f:
            script_template = f.read()

        with utils.save_file_atomic(script_path, "w") as script:
            script.write(script_template.format(modules=module_string))

        os.chmod(script_path, stat.S_IEXEC | stat.S_IREAD)

    # _get_element_dirname()
    #
    # Get path to directory for an element based on its normal name.
    #
    # For cross-junction elements, the path will be prefixed with the name
    # of the junction element.
    #
    # Args:
    #    directory (str): path to base directory
    #    element (Element): the element
    #
    # Returns:
    #    (str): Path to directory for this element
    #
    def _get_element_dirname(self, directory, element):
        parts = [element.normal_name]
        while element._get_project() != self._project:
            element = element._get_project().junction
            parts.append(element.normal_name)

        return os.path.join(directory, *reversed(parts))

    # _buildtree_pull_required()
    #
    # Check if current task, given config, requires element buildtree artifact
    #
    # Args:
    #    elements (list): elements to check if buildtrees are required
    #
    # Returns:
    #    (list): elements requiring buildtrees
    #
    def _buildtree_pull_required(self, elements):
        required_list = []

        # If context is set to not pull buildtrees, or no fetch remotes, return empty list
        if not self._context.pull_buildtrees or not self._artifacts.has_fetch_remotes():
            return required_list

        for element in elements:
            # Check if element is partially cached without its buildtree, as the element
            # artifact may not be cached at all
            if element._cached() and not element._cached_buildtree() and element._buildtree_exists():
                required_list.append(element)

        return required_list

    # _classify_artifacts()
    #
    # Split up a list of targets into element names and artifact refs
    #
    # Args:
    #    targets (list): A list of targets
    #
    # Returns:
    #    (list): element names present in the targets
    #    (list): artifact refs present in the targets
    #
    def _classify_artifacts(self, targets):
        element_targets = []
        artifact_refs = []
        element_globs = []
        artifact_globs = []

        for target in targets:
            if target.endswith(".bst"):
                if any(c in "*?[" for c in target):
                    element_globs.append(target)
                else:
                    element_targets.append(target)
            else:
                if any(c in "*?[" for c in target):
                    artifact_globs.append(target)
                else:
                    try:
                        verify_artifact_ref(target)
                    except ArtifactElementError:
                        element_targets.append(target)
                        continue
                    artifact_refs.append(target)

        if element_globs:
            for dirpath, _, filenames in os.walk(self._project.element_path):
                for filename in filenames:
                    element_path = os.path.join(dirpath, filename)
                    length = len(self._project.element_path) + 1
                    element_path = element_path[length:]  # Strip out the element_path

                    if any(fnmatch(element_path, glob) for glob in element_globs):
                        element_targets.append(element_path)

        if artifact_globs:
            for glob in artifact_globs:
                artifact_refs.extend(self._artifacts.list_artifacts(glob=glob))
            if not artifact_refs:
                self._message(MessageType.WARN, "No artifacts found for globs: {}".format(", ".join(artifact_globs)))

        return element_targets, artifact_refs


# _handle_compression()
#
# Return the tarfile mode str to be used when creating a tarball
#
# Args:
#    compression (str): The type of compression (either 'gz', 'xz' or 'bz2')
#    to_stdout (bool): Whether we want to open a stream for writing
#
# Returns:
#    (str): The tarfile mode string
#
def _handle_compression(compression, *, to_stream=False):
    mode_prefix = "w|" if to_stream else "w:"
    return mode_prefix + compression
