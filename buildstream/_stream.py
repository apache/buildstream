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
from contextlib import contextmanager
from tempfile import TemporaryDirectory

from ._exceptions import StreamError, ImplError, BstError, set_last_task_error
from ._message import Message, MessageType
from ._scheduler import Scheduler, SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue
from ._pipeline import Pipeline, PipelineSelection
from ._platform import Platform
from . import utils, _yaml, _site
from . import Scope, Consistency


# Stream()
#
# This is the main, toplevel calling interface in BuildStream core.
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    session_start (datetime): The time when the session started
#    session_start_callback (callable): A callback to invoke when the session starts
#    interrupt_callback (callable): A callback to invoke when we get interrupted
#    ticker_callback (callable): Invoked every second while running the scheduler
#    job_start_callback (callable): Called when a job starts
#    job_complete_callback (callable): Called when a job completes
#
class Stream():

    def __init__(self, context, project, session_start, *,
                 session_start_callback=None,
                 interrupt_callback=None,
                 ticker_callback=None,
                 job_start_callback=None,
                 job_complete_callback=None):

        #
        # Public members
        #
        self.targets = []            # Resolved target elements
        self.session_elements = []   # List of elements being processed this session
        self.total_elements = []     # Total list of elements based on targets
        self.queues = []             # Queue objects

        #
        # Private members
        #
        self._platform = Platform.get_platform()
        self._artifacts = self._platform.artifactcache
        self._context = context
        self._project = project
        self._pipeline = Pipeline(context, project, self._artifacts)
        self._scheduler = Scheduler(context, session_start,
                                    interrupt_callback=interrupt_callback,
                                    ticker_callback=ticker_callback,
                                    job_start_callback=job_start_callback,
                                    job_complete_callback=job_complete_callback)
        self._first_non_track_queue = None
        self._session_start_callback = session_start_callback

    # cleanup()
    #
    # Cleans up application state
    #
    def cleanup(self):
        if self._project:
            self._project.cleanup()

    # load_selection()
    #
    # An all purpose method for loading a selection of elements, this
    # is primarily useful for the frontend to implement `bst show`
    # and `bst shell`.
    #
    # Args:
    #    targets (list of str): Targets to pull
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from fetching
    #
    # Returns:
    #    (list of Element): The selected elements
    def load_selection(self, targets, *,
                       selection=PipelineSelection.NONE,
                       except_targets=()):
        elements, _ = self._load(targets, (),
                                 selection=selection,
                                 except_targets=except_targets,
                                 fetch_subprojects=False)
        return elements

    # shell()
    #
    # Run a shell
    #
    # Args:
    #    element (Element): An Element object to run the shell for
    #    scope (Scope): The scope for the shell (Scope.BUILD or Scope.RUN)
    #    prompt (str): The prompt to display in the shell
    #    directory (str): A directory where an existing prestaged sysroot is expected, or None
    #    mounts (list of HostMount): Additional directories to mount into the sandbox
    #    isolate (bool): Whether to isolate the environment like we do in builds
    #    command (list): An argv to launch in the sandbox, or None
    #
    # Returns:
    #    (int): The exit code of the launched shell
    #
    def shell(self, element, scope, prompt, *,
              directory=None,
              mounts=None,
              isolate=False,
              command=None):

        # Assert we have everything we need built, unless the directory is specified
        # in which case we just blindly trust the directory, using the element
        # definitions to control the execution environment only.
        if directory is None:
            missing_deps = [
                dep._get_full_name()
                for dep in self._pipeline.dependencies([element], scope)
                if not dep._cached()
            ]
            if missing_deps:
                raise StreamError("Elements need to be built or downloaded before staging a shell environment",
                                  detail="\n".join(missing_deps))

        return element._shell(scope, directory, mounts=mounts, isolate=isolate, prompt=prompt, command=command)

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    targets (list of str): Targets to build
    #    track_targets (list of str): Specified targets for tracking
    #    track_except (list of str): Specified targets to except from tracking
    #    track_cross_junctions (bool): Whether tracking should cross junction boundaries
    #    build_all (bool): Whether to build all elements, or only those
    #                      which are required to build the target.
    #
    def build(self, targets, *,
              track_targets=None,
              track_except=None,
              track_cross_junctions=False,
              build_all=False):

        if build_all:
            selection = PipelineSelection.ALL
        else:
            selection = PipelineSelection.PLAN

        elements, track_elements = \
            self._load(targets, track_targets,
                       selection=selection, track_selection=PipelineSelection.ALL,
                       track_except_targets=track_except,
                       track_cross_junctions=track_cross_junctions,
                       use_artifact_config=True,
                       fetch_subprojects=True,
                       dynamic_plan=True)

        # Remove the tracking elements from the main targets
        elements = self._pipeline.subtract_elements(elements, track_elements)

        # Assert that the elements we're not going to track are consistent
        self._pipeline.assert_consistent(elements)

        # Now construct the queues
        #
        track_queue = None
        if track_elements:
            track_queue = TrackQueue(self._scheduler)
            self._add_queue(track_queue, track=True)

        if self._artifacts.has_fetch_remotes():
            self._add_queue(PullQueue(self._scheduler))

        self._add_queue(FetchQueue(self._scheduler, skip_cached=True))
        self._add_queue(BuildQueue(self._scheduler))

        if self._artifacts.has_push_remotes():
            self._add_queue(PushQueue(self._scheduler))

        # Enqueue elements
        #
        if track_elements:
            self._enqueue_plan(track_elements, queue=track_queue)
        self._enqueue_plan(elements)
        self._run()

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    targets (list of str): Targets to fetch
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from fetching
    #    track_targets (bool): Whether to track selected targets in addition to fetching
    #    track_cross_junctions (bool): Whether tracking should cross junction boundaries
    #
    def fetch(self, targets, *,
              selection=PipelineSelection.PLAN,
              except_targets=None,
              track_targets=False,
              track_cross_junctions=False):

        if track_targets:
            track_targets = targets
            track_selection = selection
            track_except_targets = except_targets
        else:
            track_targets = ()
            track_selection = PipelineSelection.NONE
            track_except_targets = ()

        elements, track_elements = \
            self._load(targets, track_targets,
                       selection=selection, track_selection=track_selection,
                       except_targets=except_targets,
                       track_except_targets=track_except_targets,
                       track_cross_junctions=track_cross_junctions,
                       fetch_subprojects=True)

        # Delegated to a shared fetch method
        self._fetch(elements, track_elements=track_elements)

    # track()
    #
    # Tracks all the sources of the selected elements.
    #
    # Args:
    #    targets (list of str): Targets to track
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    except_targets (list of str): Specified targets to except from tracking
    #    cross_junctions (bool): Whether tracking should cross junction boundaries
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, targets, *,
              selection=PipelineSelection.REDIRECT,
              except_targets=None,
              cross_junctions=False):

        # We pass no target to build. Only to track. Passing build targets
        # would fully load project configuration which might not be
        # possible before tracking is done.
        _, elements = \
            self._load([], targets,
                       selection=selection, track_selection=selection,
                       except_targets=except_targets,
                       track_except_targets=except_targets,
                       track_cross_junctions=cross_junctions,
                       fetch_subprojects=True)

        track_queue = TrackQueue(self._scheduler)
        self._add_queue(track_queue, track=True)
        self._enqueue_plan(elements, queue=track_queue)
        self._run()

    # pull()
    #
    # Pulls artifacts from remote artifact server(s)
    #
    # Args:
    #    targets (list of str): Targets to pull
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    remote (str): The URL of a specific remote server to pull from, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to pull artifacts from.
    #
    def pull(self, targets, *,
             selection=PipelineSelection.NONE,
             remote=None):

        use_config = True
        if remote:
            use_config = False

        elements, _ = self._load(targets, (),
                                 selection=selection,
                                 use_artifact_config=use_config,
                                 artifact_remote_url=remote,
                                 fetch_subprojects=True)

        if not self._artifacts.has_fetch_remotes():
            raise StreamError("No artifact caches available for pulling artifacts")

        self._pipeline.assert_consistent(elements)
        self._add_queue(PullQueue(self._scheduler))
        self._enqueue_plan(elements)
        self._run()

    # push()
    #
    # Pulls artifacts to remote artifact server(s)
    #
    # Args:
    #    targets (list of str): Targets to push
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    remote (str): The URL of a specific remote server to push to, or None
    #
    # If `remote` specified as None, then regular configuration will be used
    # to determine where to push artifacts to.
    #
    def push(self, targets, *,
             selection=PipelineSelection.NONE,
             remote=None):

        use_config = True
        if remote:
            use_config = False

        elements, _ = self._load(targets, (),
                                 selection=selection,
                                 use_artifact_config=use_config,
                                 artifact_remote_url=remote,
                                 fetch_subprojects=True)

        if not self._artifacts.has_push_remotes():
            raise StreamError("No artifact caches available for pushing artifacts")

        self._pipeline.assert_consistent(elements)
        self._add_queue(PushQueue(self._scheduler))
        self._enqueue_plan(elements)
        self._run()

    # checkout()
    #
    # Checkout target artifact to the specified location
    #
    # Args:
    #    target (str): Target to checkout
    #    location (str): Location to checkout the artifact to
    #    force (bool): Whether files can be overwritten if necessary
    #    deps (str): The dependencies to checkout
    #    integrate (bool): Whether to run integration commands
    #    hardlinks (bool): Whether checking out files hardlinked to
    #                      their artifacts is acceptable
    #    tar (bool): If true, a tarball from the artifact contents will
    #                be created, otherwise the file tree of the artifact
    #                will be placed at the given location. If true and
    #                location is '-', the tarball will be dumped on the
    #                standard output.
    #
    def checkout(self, target, *,
                 location=None,
                 force=False,
                 deps='run',
                 integrate=True,
                 hardlinks=False,
                 tar=False):

        # We only have one target in a checkout command
        elements, _ = self._load((target,), (), fetch_subprojects=True)
        target = elements[0]

        if not tar:
            try:
                os.makedirs(location, exist_ok=True)
            except OSError as e:
                raise StreamError("Failed to create checkout directory: '{}'"
                                  .format(e)) from e

        if not tar:
            if not os.access(location, os.W_OK):
                raise StreamError("Checkout directory '{}' not writable"
                                  .format(location))
            if not force and os.listdir(location):
                raise StreamError("Checkout directory '{}' not empty"
                                  .format(location))
        elif os.path.exists(location) and location != '-':
            if not os.access(location, os.W_OK):
                raise StreamError("Output file '{}' not writable"
                                  .format(location))
            if not force and os.path.exists(location):
                raise StreamError("Output file '{}' already exists"
                                  .format(location))

        # Stage deps into a temporary sandbox first
        try:
            with target._prepare_sandbox(Scope.RUN, None, deps=deps,
                                         integrate=integrate) as sandbox:

                # Copy or move the sandbox to the target directory
                sandbox_root = sandbox.get_directory()
                if not tar:
                    with target.timed_activity("Checking out files in '{}'"
                                               .format(location)):
                        try:
                            if hardlinks:
                                self._checkout_hardlinks(sandbox_root, location)
                            else:
                                utils.copy_files(sandbox_root, location)
                        except OSError as e:
                            raise StreamError("Failed to checkout files: '{}'"
                                              .format(e)) from e
                else:
                    if location == '-':
                        with target.timed_activity("Creating tarball"):
                            with os.fdopen(sys.stdout.fileno(), 'wb') as fo:
                                with tarfile.open(fileobj=fo, mode="w|") as tf:
                                    Stream._add_directory_to_tarfile(
                                        tf, sandbox_root, '.')
                    else:
                        with target.timed_activity("Creating tarball '{}'"
                                                   .format(location)):
                            with tarfile.open(location, "w:") as tf:
                                Stream._add_directory_to_tarfile(
                                    tf, sandbox_root, '.')

        except BstError as e:
            raise StreamError("Error while staging dependencies into a sandbox"
                              ": '{}'".format(e), detail=e.detail, reason=e.reason) from e

    # workspace_open
    #
    # Open a project workspace
    #
    # Args:
    #    target (str): The target element to open the workspace for
    #    directory (str): The directory to stage the source in
    #    no_checkout (bool): Whether to skip checking out the source
    #    track_first (bool): Whether to track and fetch first
    #    force (bool): Whether to ignore contents in an existing directory
    #
    def workspace_open(self, target, directory, *,
                       no_checkout,
                       track_first,
                       force):

        if track_first:
            track_targets = (target,)
        else:
            track_targets = ()

        elements, track_elements = self._load((target,), track_targets,
                                              selection=PipelineSelection.REDIRECT,
                                              track_selection=PipelineSelection.REDIRECT)
        target = elements[0]
        workdir = os.path.abspath(directory)

        if not list(target.sources()):
            build_depends = [x.name for x in target.dependencies(Scope.BUILD, recurse=False)]
            if not build_depends:
                raise StreamError("The given element has no sources")
            detail = "Try opening a workspace on one of its dependencies instead:\n"
            detail += "  \n".join(build_depends)
            raise StreamError("The given element has no sources", detail=detail)

        workspaces = self._context.get_workspaces()

        # Check for workspace config
        workspace = workspaces.get_workspace(target._get_full_name())
        if workspace and not force:
            raise StreamError("Workspace '{}' is already defined at: {}"
                              .format(target.name, workspace.path))

        # If we're going to checkout, we need at least a fetch,
        # if we were asked to track first, we're going to fetch anyway.
        #
        if not no_checkout or track_first:
            track_elements = []
            if track_first:
                track_elements = elements
            self._fetch(elements, track_elements=track_elements)

        if not no_checkout and target._get_consistency() != Consistency.CACHED:
            raise StreamError("Could not stage uncached source. " +
                              "Use `--track` to track and " +
                              "fetch the latest version of the " +
                              "source.")

        if workspace:
            workspaces.delete_workspace(target._get_full_name())
            workspaces.save_config()
            shutil.rmtree(directory)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise StreamError("Failed to create workspace directory: {}".format(e)) from e

        workspaces.create_workspace(target._get_full_name(), workdir)

        if not no_checkout:
            with target.timed_activity("Staging sources to {}".format(directory)):
                target._open_workspace()

        workspaces.save_config()
        self._message(MessageType.INFO, "Saved workspace configuration")

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
            with self._context.timed_activity("Removing workspace directory {}"
                                              .format(workspace.path)):
                try:
                    shutil.rmtree(workspace.path)
                except OSError as e:
                    raise StreamError("Could not remove  '{}': {}"
                                      .format(workspace.path, e)) from e

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
    #    soft (bool): Only reset workspace state
    #    track_first (bool): Whether to also track the sources first
    #
    def workspace_reset(self, targets, *, soft, track_first):

        if track_first:
            track_targets = targets
        else:
            track_targets = ()

        elements, track_elements = self._load(targets, track_targets,
                                              selection=PipelineSelection.REDIRECT,
                                              track_selection=PipelineSelection.REDIRECT)

        nonexisting = []
        for element in elements:
            if not self.workspace_exists(element.name):
                nonexisting.append(element.name)
        if nonexisting:
            raise StreamError("Workspace does not exist", detail="\n".join(nonexisting))

        # Do the tracking first
        if track_first:
            self._fetch(elements, track_elements=track_elements)

        workspaces = self._context.get_workspaces()

        for element in elements:
            workspace = workspaces.get_workspace(element._get_full_name())

            if soft:
                workspace.prepared = False
                self._message(MessageType.INFO, "Reset workspace state for {} at: {}"
                              .format(element.name, workspace.path))
                continue

            with element.timed_activity("Removing workspace directory {}"
                                        .format(workspace.path)):
                try:
                    shutil.rmtree(workspace.path)
                except OSError as e:
                    raise StreamError("Could not remove  '{}': {}"
                                      .format(workspace.path, e)) from e

            workspaces.delete_workspace(element._get_full_name())
            workspaces.create_workspace(element._get_full_name(), workspace.path)

            with element.timed_activity("Staging sources to {}".format(workspace.path)):
                element._open_workspace()

            self._message(MessageType.INFO, "Reset workspace for {} at: {}".format(element.name, workspace.path))

        workspaces.save_config()

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
                'element': element_name,
                'directory': workspace_.path,
            }
            workspaces.append(workspace_detail)

        _yaml.dump({
            'workspaces': workspaces
        })

    # source_bundle()
    #
    # Create a host buildable tarball bundle for the given target.
    #
    # Args:
    #    target (str): The target element to bundle
    #    directory (str): The directory to output the tarball
    #    track_first (bool): Track new source references before bundling
    #    compression (str): The compression type to use
    #    force (bool): Overwrite an existing tarball
    #
    def source_bundle(self, target, directory, *,
                      track_first=False,
                      force=False,
                      compression="gz",
                      except_targets=()):

        if track_first:
            track_targets = (target,)
        else:
            track_targets = ()

        elements, track_elements = self._load((target,), track_targets,
                                              selection=PipelineSelection.ALL,
                                              except_targets=except_targets,
                                              track_selection=PipelineSelection.ALL,
                                              fetch_subprojects=True)

        # source-bundle only supports one target
        target = self.targets[0]

        self._message(MessageType.INFO, "Bundling sources for target {}".format(target.name))

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
            raise StreamError("Cannot write to {0}: {1}"
                              .format(tar_location, e)) from e

        # Fetch and possibly track first
        #
        self._fetch(elements, track_elements=track_elements)

        # We don't use the scheduler for this as it is almost entirely IO
        # bound.

        # Create a temporary directory to build the source tree in
        builddir = self._context.builddir
        prefix = "{}-".format(target.normal_name)

        with TemporaryDirectory(prefix=prefix, dir=builddir) as tempdir:
            source_directory = os.path.join(tempdir, 'source')
            try:
                os.makedirs(source_directory)
            except OSError as e:
                raise StreamError("Failed to create directory: {}"
                                  .format(e)) from e

            # Any elements that don't implement _write_script
            # should not be included in the later stages.
            elements = [
                element for element in elements
                if self._write_element_script(source_directory, element)
            ]

            self._write_element_sources(tempdir, elements)
            self._write_build_script(tempdir, elements)
            self._collect_sources(tempdir, tar_location,
                                  target.normal_name, compression)

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
            loaded_elements, _ = self._load(load_elements, (),
                                            selection=PipelineSelection.REDIRECT,
                                            track_selection=PipelineSelection.REDIRECT)

            for e in loaded_elements:
                output_elements.add(e.name)

        return list(output_elements)

    #############################################################
    #                 Scheduler API forwarding                  #
    #############################################################

    # running
    #
    # Whether the scheduler is running
    #
    @property
    def running(self):
        return self._scheduler.loop is not None

    # suspended
    #
    # Whether the scheduler is currently suspended
    #
    @property
    def suspended(self):
        return self._scheduler.suspended

    # terminated
    #
    # Whether the scheduler is currently terminated
    #
    @property
    def terminated(self):
        return self._scheduler.terminated

    # elapsed_time
    #
    # Elapsed time since the session start
    #
    @property
    def elapsed_time(self):
        return self._scheduler.elapsed_time()

    # terminate()
    #
    # Terminate jobs
    #
    def terminate(self):
        self._scheduler.terminate_jobs()

    # quit()
    #
    # Quit the session, this will continue with any ongoing
    # jobs, use Stream.terminate() instead for cancellation
    # of ongoing jobs
    #
    def quit(self):
        self._scheduler.stop_queueing()

    # suspend()
    #
    # Context manager to suspend ongoing jobs
    #
    @contextmanager
    def suspend(self):
        with self._scheduler.jobs_suspended():
            yield

    #############################################################
    #                    Private Methods                        #
    #############################################################

    # _load()
    #
    # A convenience method for loading element lists
    #
    # If `targets` is not empty used project configuration will be
    # fully loaded. If `targets` is empty, tracking will still be
    # resolved for elements in `track_targets`, but no build pipeline
    # will be resolved. This is behavior is import for track() to
    # not trigger full loading of project configuration.
    #
    # Args:
    #    targets (list of str): Main targets to load
    #    track_targets (list of str): Tracking targets
    #    selection (PipelineSelection): The selection mode for the specified targets
    #    track_selection (PipelineSelection): The selection mode for the specified tracking targets
    #    except_targets (list of str): Specified targets to except from fetching
    #    track_except_targets (list of str): Specified targets to except from fetching
    #    track_cross_junctions (bool): Whether tracking should cross junction boundaries
    #    use_artifact_config (bool): Whether to initialize artifacts with the config
    #    artifact_remote_url (bool): A remote url for initializing the artifacts
    #    fetch_subprojects (bool): Whether to fetch subprojects while loading
    #
    # Returns:
    #    (list of Element): The primary element selection
    #    (list of Element): The tracking element selection
    #
    def _load(self, targets, track_targets, *,
              selection=PipelineSelection.NONE,
              track_selection=PipelineSelection.NONE,
              except_targets=(),
              track_except_targets=(),
              track_cross_junctions=False,
              use_artifact_config=False,
              artifact_remote_url=None,
              fetch_subprojects=False,
              dynamic_plan=False):

        # Load rewritable if we have any tracking selection to make
        rewritable = False
        if track_targets:
            rewritable = True

        # Load all targets
        elements, except_elements, track_elements, track_except_elements = \
            self._pipeline.load([targets, except_targets, track_targets, track_except_targets],
                                rewritable=rewritable,
                                fetch_subprojects=fetch_subprojects)

        # Hold on to the targets
        self.targets = elements

        # Here we should raise an error if the track_elements targets
        # are not dependencies of the primary targets, this is not
        # supported.
        #
        # This can happen with `bst build --track`
        #
        if targets and not self._pipeline.targets_include(elements, track_elements):
            raise StreamError("Specified tracking targets that are not "
                              "within the scope of primary targets")

        # First take care of marking tracking elements, this must be
        # done before resolving element states.
        #
        assert track_selection != PipelineSelection.PLAN

        # Tracked elements are split by owner projects in order to
        # filter cross junctions tracking dependencies on their
        # respective project.
        track_projects = {}
        for element in track_elements:
            project = element._get_project()
            if project not in track_projects:
                track_projects[project] = [element]
            else:
                track_projects[project].append(element)

        track_selected = []

        for project, project_elements in track_projects.items():
            selected = self._pipeline.get_selection(project_elements, track_selection)
            selected = self._pipeline.track_cross_junction_filter(project,
                                                                  selected,
                                                                  track_cross_junctions)
            track_selected.extend(selected)

        track_selected = self._pipeline.except_elements(track_elements,
                                                        track_selected,
                                                        track_except_elements)

        for element in track_selected:
            element._schedule_tracking()

        if not targets:
            self._pipeline.resolve_elements(track_selected)
            return [], track_selected

        # ArtifactCache.setup_remotes expects all projects to be fully loaded
        for project in self._context.get_projects():
            project.ensure_fully_loaded()

        # Connect to remote caches, this needs to be done before resolving element state
        self._artifacts.setup_remotes(use_config=use_artifact_config, remote_url=artifact_remote_url)

        # Now move on to loading primary selection.
        #
        self._pipeline.resolve_elements(elements)
        selected = self._pipeline.get_selection(elements, selection, silent=False)
        selected = self._pipeline.except_elements(elements,
                                                  selected,
                                                  except_elements)

        # Set the "required" artifacts that should not be removed
        # while this pipeline is active
        #
        # It must include all the artifacts which are required by the
        # final product. Note that this is a superset of the build plan.
        #
        self._artifacts.mark_required_elements(self._pipeline.dependencies(elements, Scope.ALL))

        if selection == PipelineSelection.PLAN and dynamic_plan:
            # We use a dynamic build plan, only request artifacts of top-level targets,
            # others are requested dynamically as needed.
            # This avoids pulling, fetching, or building unneeded build-only dependencies.
            for element in elements:
                element._set_required()
        else:
            for element in selected:
                element._set_required()

        return selected, track_selected

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self._context.message(
            Message(None, message_type, message, **args))

    # _add_queue()
    #
    # Adds a queue to the stream
    #
    # Args:
    #    queue (Queue): Queue to add to the pipeline
    #    track (bool): Whether this is the tracking queue
    #
    def _add_queue(self, queue, *, track=False):
        self.queues.append(queue)

        if not (track or self._first_non_track_queue):
            self._first_non_track_queue = queue

    # _enqueue_plan()
    #
    # Enqueues planned elements to the specified queue.
    #
    # Args:
    #    plan (list of Element): The list of elements to be enqueued
    #    queue (Queue): The target queue, defaults to the first non-track queue
    #
    def _enqueue_plan(self, plan, *, queue=None):
        queue = queue or self._first_non_track_queue

        queue.enqueue(plan)
        self.session_elements += plan

    # _run()
    #
    # Common function for running the scheduler
    #
    def _run(self):

        # Inform the frontend of the full list of elements
        # and the list of elements which will be processed in this run
        #
        self.total_elements = list(self._pipeline.dependencies(self.targets, Scope.ALL))

        if self._session_start_callback is not None:
            self._session_start_callback()

        _, status = self._scheduler.run(self.queues)

        # Force update element states after a run, such that the summary
        # is more coherent
        try:
            for element in self.total_elements:
                element._update_state()
        except BstError as e:
            self._message(MessageType.ERROR, "Error resolving final state", detail=str(e))
            set_last_task_error(e.domain, e.reason)
        except Exception as e:   # pylint: disable=broad-except
            self._message(MessageType.BUG, "Unhandled exception while resolving final state", detail=str(e))

        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

    # _fetch()
    #
    # Performs the fetch job, the body of this function is here because
    # it is shared between a few internals.
    #
    # Args:
    #    elements (list of Element): Elements to fetch
    #    track_elements (list of Element): Elements to track
    #
    def _fetch(self, elements, *, track_elements=None):

        if track_elements is None:
            track_elements = []

        # Subtract the track elements from the fetch elements, they will be added separately
        fetch_plan = self._pipeline.subtract_elements(elements, track_elements)

        # Assert consistency for the fetch elements
        self._pipeline.assert_consistent(fetch_plan)

        # Filter out elements with cached sources, only from the fetch plan
        # let the track plan resolve new refs.
        cached = [elt for elt in fetch_plan if elt._get_consistency() == Consistency.CACHED]
        fetch_plan = self._pipeline.subtract_elements(fetch_plan, cached)

        # Construct queues, enqueue and run
        #
        track_queue = None
        if track_elements:
            track_queue = TrackQueue(self._scheduler)
            self._add_queue(track_queue, track=True)
        self._add_queue(FetchQueue(self._scheduler))

        if track_elements:
            self._enqueue_plan(track_elements, queue=track_queue)
        self._enqueue_plan(fetch_plan)
        self._run()

    # Helper function for checkout()
    #
    def _checkout_hardlinks(self, sandbox_root, directory):
        try:
            removed = utils.safe_remove(directory)
        except OSError as e:
            raise StreamError("Failed to remove checkout directory: {}".format(e)) from e

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

    # Add a directory entry deterministically to a tar file
    #
    # This function takes extra steps to ensure the output is deterministic.
    # First, it sorts the results of os.listdir() to ensure the ordering of
    # the files in the archive is the same.  Second, it sets a fixed
    # timestamp for each entry. See also https://bugs.python.org/issue24465.
    @staticmethod
    def _add_directory_to_tarfile(tf, dir_name, dir_arcname, mtime=0):
        for filename in sorted(os.listdir(dir_name)):
            name = os.path.join(dir_name, filename)
            arcname = os.path.join(dir_arcname, filename)

            tarinfo = tf.gettarinfo(name, arcname)
            tarinfo.mtime = mtime

            if tarinfo.isreg():
                with open(name, "rb") as f:
                    tf.addfile(tarinfo, f)
            elif tarinfo.isdir():
                tf.addfile(tarinfo)
                Stream._add_directory_to_tarfile(tf, name, arcname, mtime)
            else:
                tf.addfile(tarinfo)

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
        with self._context.timed_activity("Creating tarball {}".format(tar_name)):
            if compression == "none":
                permissions = "w:"
            else:
                permissions = "w:" + compression

            with tarfile.open(tar_name, permissions) as tar:
                tar.add(directory, arcname=element_name)
