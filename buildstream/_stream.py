#!/usr/bin/env python3
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
import stat
import shlex
import shutil
import tarfile
from tempfile import TemporaryDirectory

from ._exceptions import StreamError, ImplError, BstError
from ._message import Message, MessageType
from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue
from ._pipeline import Pipeline, PipelineSelection
from ._platform import Platform
from ._profile import Topics, profile_start, profile_end
from . import utils, _yaml, _site
from . import Scope, Consistency


# Stream()
#
# This is the main, toplevel calling interface in BuildStream core.
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    loaded_callback (callable): A callback to invoke when the pipeline is loaded
#
class Stream():

    def __init__(self, context, project, loaded_callback):
        self.session_elements = 0  # Number of elements to process in this session
        self.total_elements = 0    # Number of total potential elements for this pipeline

        self._context = context
        self._project = project
        self._scheduler = None
        self._pipeline = None

        self._loaded_cb = loaded_callback

        # Load selected platform
        Platform.create_instance(context, project)
        self._platform = Platform.get_platform()
        self._artifacts = self._platform.artifactcache

    # cleanup()
    #
    # Cleans up application state
    #
    def cleanup(self):
        if self._pipeline:
            self._pipeline.cleanup()

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
    #    downloadable (bool): Whether the downloadable state of elements should be resolved
    #
    def load_selection(self, targets, *,
                       selection=PipelineSelection.NONE,
                       except_targets=(),
                       downloadable=False):
        self.init_pipeline(targets, except_=except_targets,
                           use_configured_remote_caches=downloadable)
        return self._pipeline.get_selection(selection)

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
                for dep in self._pipeline.dependencies(scope)
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

        rewritable = False
        if track_targets:
            rewritable = True

        self.init_pipeline(targets,
                           except_=track_except,
                           rewritable=rewritable,
                           use_configured_remote_caches=True,
                           track_elements=track_targets,
                           track_cross_junctions=track_cross_junctions)

        if build_all:
            plan = self._pipeline.dependencies(Scope.ALL)
        else:
            plan = self._pipeline._plan(except_=False)

        # We want to start the build queue with any elements that are
        # not being tracked first
        track_elements = set(self._pipeline._track_elements)
        plan = [e for e in plan if e not in track_elements]

        # Assert that we have a consistent pipeline now (elements in
        # track_plan will be made consistent)
        self._pipeline._assert_consistent(plan)

        fetch = FetchQueue(self._scheduler, skip_cached=True)
        build = BuildQueue(self._scheduler)
        track = None
        pull = None
        push = None
        queues = []
        if self._pipeline._track_elements:
            track = TrackQueue(self._scheduler)
            queues.append(track)
        if self._pipeline._artifacts.has_fetch_remotes():
            pull = PullQueue(self._scheduler)
            queues.append(pull)
        queues.append(fetch)
        queues.append(build)
        if self._pipeline._artifacts.has_push_remotes():
            push = PushQueue(self._scheduler)
            queues.append(push)

        # If we're going to track, tracking elements go into the first queue
        # which is the tracking queue, the rest of the plan goes into the next
        # queue (whatever that happens to be)
        if track:
            queues[0].enqueue(self._pipeline._track_elements)
            queues[1].enqueue(plan)
        else:
            queues[0].enqueue(plan)

        self.session_elements = len(self._pipeline._track_elements) + len(plan)

        _, status = self._scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

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

        rewritable = False
        if track_targets:
            rewritable = True

        self.init_pipeline(targets,
                           except_=except_targets,
                           rewritable=rewritable,
                           track_elements=targets if track_targets else None,
                           track_cross_junctions=track_cross_junctions)

        fetch_plan = self._pipeline.get_selection(selection)

        # Delegated to a shared method for now
        self._do_fetch(fetch_plan)

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
              selection=PipelineSelection.NONE,
              except_targets=None,
              track_targets=False,
              cross_junctions=False):

        self.init_pipeline(targets,
                           except_=except_targets,
                           rewritable=True,
                           track_elements=targets,
                           track_cross_junctions=cross_junctions,
                           track_selection=selection)

        track = TrackQueue(self._scheduler)
        track.enqueue(self._pipeline._track_elements)
        self.session_elements = len(self._pipeline._track_elements)

        _, status = self._scheduler.run([track])
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

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

        use_configured_remote_caches = True
        if remote is not None:
            use_configured_remote_caches = False

        self.init_pipeline(targets,
                           use_configured_remote_caches=use_configured_remote_caches,
                           add_remote_cache=remote)
        elements = self._pipeline.get_selection(selection)

        if not self._pipeline._artifacts.has_fetch_remotes():
            raise StreamError("No artifact caches available for pulling artifacts")

        plan = elements
        self._pipeline._assert_consistent(plan)
        self._pipeline.session_elements = len(plan)

        pull = PullQueue(self._scheduler)
        pull.enqueue(plan)
        queues = [pull]

        _, status = self._scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

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

        use_configured_remote_caches = True
        if remote is not None:
            use_configured_remote_caches = False

        self.init_pipeline(targets,
                           use_configured_remote_caches=use_configured_remote_caches,
                           add_remote_cache=remote)
        elements = self._pipeline.get_selection(selection)

        if not self._pipeline._artifacts.has_push_remotes():
            raise StreamError("No artifact caches available for pushing artifacts")

        plan = elements
        self._pipeline._assert_consistent(plan)
        self._pipeline.session_elements = len(plan)

        push = PushQueue(self._scheduler)
        push.enqueue(plan)
        queues = [push]

        _, status = self._scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

    # checkout()
    #
    # Checkout the pipeline target artifact to the specified directory
    #
    # Args:
    #    target (str): Target to checkout
    #    directory (str): The directory to checkout the artifact to
    #    force (bool): Force overwrite files which exist in `directory`
    #    integrate (bool): Whether to run integration commands
    #    hardlinks (bool): Whether checking out files hardlinked to
    #                      their artifacts is acceptable
    #
    def checkout(self, target, *,
                 directory=None,
                 force=False,
                 integrate=True,
                 hardlinks=False):

        self.init_pipeline((target,))

        # We only have one target in a checkout command
        target = self._pipeline.targets[0]

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise StreamError("Failed to create checkout directory: {}".format(e)) from e

        if not os.access(directory, os.W_OK):
            raise StreamError("Directory {} not writable".format(directory))

        if not force and os.listdir(directory):
            raise StreamError("Checkout directory is not empty: {}"
                              .format(directory))

        # Stage deps into a temporary sandbox first
        try:
            with target._prepare_sandbox(Scope.RUN, None, integrate=integrate) as sandbox:

                # Copy or move the sandbox to the target directory
                sandbox_root = sandbox.get_directory()
                with target.timed_activity("Checking out files in {}".format(directory)):
                    try:
                        if hardlinks:
                            self._checkout_hardlinks(sandbox_root, directory)
                        else:
                            utils.copy_files(sandbox_root, directory)
                    except OSError as e:
                        raise StreamError("Failed to checkout files: {}".format(e)) from e
        except BstError as e:
            raise StreamError("Error while staging dependencies into a sandbox: {}".format(e),
                              reason=e.reason) from e

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

        self.init_pipeline((target,),
                           track_elements=[target] if track_first else None,
                           track_selection=PipelineSelection.NONE,
                           rewritable=track_first)

        target = self._pipeline.targets[0]
        workdir = os.path.abspath(directory)

        if not list(target.sources()):
            build_depends = [x.name for x in target.dependencies(Scope.BUILD, recurse=False)]
            if not build_depends:
                raise StreamError("The given element has no sources")
            detail = "Try opening a workspace on one of its dependencies instead:\n"
            detail += "  \n".join(build_depends)
            raise StreamError("The given element has no sources", detail=detail)

        # Check for workspace config
        workspace = self._project.workspaces.get_workspace(target.name)
        if workspace:
            raise StreamError("Workspace '{}' is already defined at: {}"
                              .format(target.name, workspace.path))

        # If we're going to checkout, we need at least a fetch,
        # if we were asked to track first, we're going to fetch anyway.
        #
        # For now, tracking is handled by _do_fetch() automatically
        # by virtue of our screwed up pipeline initialization stuff.
        #
        if not no_checkout or track_first:
            self._do_fetch([target])

        if not no_checkout and target._get_consistency() != Consistency.CACHED:
            raise StreamError("Could not stage uncached source. " +
                              "Use `--track` to track and " +
                              "fetch the latest version of the " +
                              "source.")

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise StreamError("Failed to create workspace directory: {}".format(e)) from e

        self._project.workspaces.create_workspace(target.name, workdir)

        if not no_checkout:
            with target.timed_activity("Staging sources to {}".format(directory)):
                target._open_workspace()

        self._project.workspaces.save_config()
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
        workspace = self._project.workspaces.get_workspace(element_name)

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
        self._project.workspaces.delete_workspace(element_name)
        self._project.workspaces.save_config()
        self._message(MessageType.INFO, "Closed workspace for {}".format(element_name))

    # workspace_reset
    #
    # Reset a workspace to its original state, discarding any user
    # changes.
    #
    # Args:
    #    targets (list of str): The target elements to reset the workspace for
    #    track_first (bool): Whether to also track the sources first
    #
    def workspace_reset(self, targets, *, track_first):

        self.init_pipeline(targets,
                           track_elements=targets if track_first else None,
                           track_selection=PipelineSelection.NONE,
                           rewritable=track_first)

        # Do the tracking first
        if track_first:
            self._do_fetch(self._pipeline.targets)

        for target in self._pipeline.targets:
            workspace = self._project.workspaces.get_workspace(target.name)

            with target.timed_activity("Removing workspace directory {}"
                                       .format(workspace.path)):
                try:
                    shutil.rmtree(workspace.path)
                except OSError as e:
                    raise StreamError("Could not remove  '{}': {}"
                                      .format(workspace.path, e)) from e

            self._project.workspaces.delete_workspace(target.name)
            self._project.workspaces.create_workspace(target.name, workspace.path)

            with target.timed_activity("Staging sources to {}".format(workspace.path)):
                target._open_workspace()

            self._message(MessageType.INFO, "Reset workspace for {} at: {}".format(target.name, workspace.path))

        self._project.workspaces.save_config()

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
        if element_name:
            workspace = self._project.workspaces.get_workspace(element_name)
            if workspace:
                return True
        elif any(self._project.workspaces.list()):
            return True

        return False

    # workspace_list
    #
    # Serializes the workspaces and dumps them in YAML to stdout.
    #
    def workspace_list(self):
        workspaces = []
        for element_name, workspace_ in self._project.workspaces.list():
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
                      compression="gz"):

        self.init_pipeline((target,),
                           track_elements=[target] if track_first else None,
                           track_selection=PipelineSelection.NONE,
                           rewritable=track_first)

        # source-bundle only supports one target
        target = self._pipeline.targets[0]
        dependencies = self._pipeline.get_selection(PipelineSelection.ALL)

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

        plan = list(dependencies)
        self._do_fetch(plan)

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
                raise StreamError("Failed to create directory: {}"
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

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self._context.message(
            Message(None, message_type, message, **args))

    # _do_fetch()
    #
    # Performs the fetch job, the body of this function is here because
    # it is shared between a few internals.
    #
    # Args:
    #    elements (list of Element): Elements to fetch
    #
    def _do_fetch(self, elements):

        fetch_plan = elements

        # Subtract the track elements from the fetch elements, they will be added separately
        if self._pipeline._track_elements:
            track_elements = set(self._pipeline._track_elements)
            fetch_plan = [e for e in fetch_plan if e not in track_elements]

        # Assert consistency for the fetch elements
        self._pipeline._assert_consistent(fetch_plan)

        # Filter out elements with cached sources, only from the fetch plan
        # let the track plan resolve new refs.
        cached = [elt for elt in fetch_plan if elt._get_consistency() == Consistency.CACHED]
        fetch_plan = [elt for elt in fetch_plan if elt not in cached]

        self.session_elements = len(self._pipeline._track_elements) + len(fetch_plan)

        fetch = FetchQueue(self._scheduler)
        fetch.enqueue(fetch_plan)
        if self._pipeline._track_elements:
            track = TrackQueue(self._scheduler)
            track.enqueue(self._pipeline._track_elements)
            queues = [track, fetch]
        else:
            queues = [fetch]

        _, status = self._scheduler.run(queues)
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

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
        with self._pipeline.targets[0].timed_activity("Creating tarball {}".format(tar_name)):
            if compression == "none":
                permissions = "w:"
            else:
                permissions = "w:" + compression

            with tarfile.open(tar_name, permissions) as tar:
                tar.add(directory, arcname=element_name)

    #############################################################
    #                      TEMPORARY CRAP                       #
    #############################################################

    # init_pipeline()
    #
    # Initialize the pipeline for a given activity
    #
    # Args:
    #    elements (list of elements): The elements to load recursively
    #    except_ (list of elements): The elements to except
    #    rewritable (bool): Whether we should load the YAML files for roundtripping
    #    use_configured_remote_caches (bool): Whether we should contact remotes
    #    add_remote_cache (str): The URL for an explicitly mentioned remote cache
    #    track_elements (list of elements): Elements which are to be tracked
    #    track_cross_junctions (bool): Whether tracking is allowed to cross junction boundaries
    #    track_selection (PipelineSelection): The selection algorithm for track elements
    #    fetch_subprojects (bool): Whether we should fetch subprojects as a part of the
    #                              loading process, if they are not yet locally cached
    #
    # Note that the except_ argument may have a subtly different meaning depending
    # on the activity performed on the Pipeline. In normal circumstances the except_
    # argument excludes elements from the `elements` list. In a build session, the
    # except_ elements are excluded from the tracking plan.
    #
    def init_pipeline(self, elements, *,
                      except_=tuple(),
                      rewritable=False,
                      use_configured_remote_caches=False,
                      add_remote_cache=None,
                      track_elements=None,
                      track_cross_junctions=False,
                      track_selection=PipelineSelection.ALL):

        profile_start(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

        self._pipeline = Pipeline(self._context, self._project, self._artifacts,
                                  elements, except_, rewritable=rewritable)

        self._pipeline.initialize(use_configured_remote_caches=use_configured_remote_caches,
                                  add_remote_cache=add_remote_cache,
                                  track_elements=track_elements,
                                  track_cross_junctions=track_cross_junctions,
                                  track_selection=track_selection)

        profile_end(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

        # Get the total
        self.total_elements = len(list(self._pipeline.dependencies(Scope.ALL)))

        if self._loaded_cb is not None:
            self._loaded_cb(self._pipeline)
