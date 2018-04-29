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
import tarfile
from tempfile import TemporaryDirectory

from ._exceptions import StreamError, ImplError, BstError
from . import _site
from . import utils
from . import Scope, Consistency
from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue, PullQueue, PushQueue


# Stream()
#
# This is the main, toplevel calling interface in BuildStream core.
#
# Args:
#    context (Context): The Context object
#
class Stream():

    def __init__(self, context, scheduler, pipeline):
        self.session_elements = 0  # Number of elements to process in this session
        self.total_elements = 0    # Number of total potential elements for this pipeline

        self._context = context
        self._scheduler = scheduler
        self._pipeline = pipeline

        self.total_elements = len(list(self._pipeline.dependencies(Scope.ALL)))

    # track()
    #
    # Trackes all the sources of all the elements in the pipeline,
    # i.e. all of the elements which the target somehow depends on.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, scheduler):
        track = TrackQueue(self._scheduler)
        track.enqueue(self._pipeline._track_elements)
        self.session_elements = len(self._pipeline._track_elements)

        _, status = self._scheduler.run([track])
        if status == SchedStatus.ERROR:
            raise StreamError()
        elif status == SchedStatus.TERMINATED:
            raise StreamError(terminated=True)

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    dependencies (list): List of elements to fetch
    #
    def fetch(self, scheduler, dependencies):
        fetch_plan = dependencies

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

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    build_all (bool): Whether to build all elements, or only those
    #                      which are required to build the target.
    #
    def build(self, scheduler, *, build_all=False):

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
                            self.checkout_hardlinks(sandbox_root, directory)
                        else:
                            utils.copy_files(sandbox_root, directory)
                    except OSError as e:
                        raise StreamError("Failed to checkout files: {}".format(e)) from e
        except BstError as e:
            raise StreamError("Error while staging dependencies into a sandbox: {}".format(e),
                              reason=e.reason) from e

    # Helper function for checkout()
    #
    def checkout_hardlinks(self, sandbox_root, directory):
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

    # pull()
    #
    # Pulls elements from the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to pull
    #
    def pull(self, scheduler, elements):

        if not self._pipeline._artifacts.has_fetch_remotes():
            raise StreamError("Not artifact caches available for pulling artifacts")

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
    # Pushes elements in the pipeline
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    elements (list): List of elements to push
    #
    def push(self, scheduler, elements):

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
        target = self._pipeline.targets[0]

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
        self.fetch(self._scheduler, plan)

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
