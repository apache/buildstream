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

# System imports
import os
from collections import deque
from enum import Enum
import traceback

# Local imports
from ..jobs import ElementJob
from ..resources import ResourceType

# BuildStream toplevel imports
from ..._exceptions import BstError, set_last_task_error
from ..._message import Message, MessageType


# Queue status for a given element
#
#
class QueueStatus(Enum):
    # The element is waiting for dependencies.
    WAIT = 1

    # The element can skip this queue.
    SKIP = 2

    # The element is ready for processing in this queue.
    READY = 3


# Queue()
#
# Args:
#    scheduler (Scheduler): The Scheduler
#
class Queue():

    # These should be overridden on class data of of concrete Queue implementations
    action_name = None
    complete_name = None
    resources = []                     # Resources this queues' jobs want

    def __init__(self, scheduler):

        #
        # Public members
        #
        self.failed_elements = []      # List of failed elements, for the frontend
        self.processed_elements = []   # List of processed elements, for the frontend
        self.skipped_elements = []     # List of skipped elements, for the frontend

        #
        # Private members
        #
        self._scheduler = scheduler
        self._wait_queue = deque()
        self._done_queue = deque()
        self._max_retries = 0

        # Assert the subclass has setup class data
        assert self.action_name is not None
        assert self.complete_name is not None

        if ResourceType.UPLOAD in self.resources or ResourceType.DOWNLOAD in self.resources:
            self._max_retries = scheduler.context.sched_network_retries

    #####################################################
    #     Abstract Methods for Queue implementations    #
    #####################################################

    # process()
    #
    # Abstract method for processing an element
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (any): An optional something to be returned
    #           for every element successfully processed
    #
    #
    def process(self, element):
        pass

    # status()
    #
    # Abstract method for reporting the status of an element.
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (QueueStatus): The element status
    #
    def status(self, element):
        return QueueStatus.READY

    # prepare()
    #
    # Abstract method for handling job preparation in the main process.
    #
    # Args:
    #    element (Element): The element which is scheduled
    #
    def prepare(self, element):
        pass

    # done()
    #
    # Abstract method for handling a successful job completion.
    #
    # Args:
    #    job (Job): The job which completed processing
    #    element (Element): The element which completed processing
    #    result (any): The return value of the process() implementation
    #    success (bool): True if the process() implementation did not
    #                    raise any exception
    #
    def done(self, job, element, result, success):
        pass

    #####################################################
    #          Scheduler / Pipeline facing APIs         #
    #####################################################

    # enqueue()
    #
    # Enqueues some elements
    #
    # Args:
    #    elts (list): A list of Elements
    #
    def enqueue(self, elts):
        if not elts:
            return

        # Note: The internal lists work with jobs. This is not
        #       reflected in any external methods (except
        #       pop/peek_ready_jobs).
        def create_job(element):
            logfile = self._element_log_path(element)
            return ElementJob(self._scheduler, self.action_name,
                              logfile, element=element, queue=self,
                              resources=self.resources,
                              action_cb=self.process,
                              complete_cb=self._job_done,
                              max_retries=self._max_retries)

        # Place skipped elements directly on the done queue
        jobs = [create_job(elt) for elt in elts]
        skip = [job for job in jobs if self.status(job.element) == QueueStatus.SKIP]
        wait = [job for job in jobs if job not in skip]

        self._wait_queue.extend(wait)
        self._done_queue.extend(skip)
        self.skipped_elements.extend(skip)

    # dequeue()
    #
    # A generator which dequeues the elements which
    # are ready to exit the queue.
    #
    # Yields:
    #    (Element): Elements being dequeued
    #
    def dequeue(self):
        while self._done_queue:
            yield self._done_queue.popleft().element

    # dequeue_ready()
    #
    # Reports whether there are any elements to dequeue
    #
    # Returns:
    #    (bool): Whether there are elements to dequeue
    #
    def dequeue_ready(self):
        return any(self._done_queue)

    # pop_ready_jobs()
    #
    # Returns:
    #     ([Job]): A list of jobs to run
    #
    # Process elements in the queue, moving elements which were enqueued
    # into the dequeue pool, and processing them if necessary.
    #
    # This will have different results for elements depending
    # on the Queue.status() implementation.
    #
    #   o Elements which are QueueStatus.WAIT will not be effected
    #
    #   o Elements which are QueueStatus.SKIP will move directly
    #     to the dequeue pool
    #
    #   o For Elements which are QueueStatus.READY a Job will be
    #     created and returned to the caller, given that the scheduler
    #     allows the Queue enough resources for the given job
    #
    def pop_ready_jobs(self):
        unready = []
        ready = []

        while self._wait_queue:
            job = self._wait_queue.popleft()
            element = job.element

            status = self.status(element)
            if status == QueueStatus.WAIT:
                unready.append(job)
                continue
            elif status == QueueStatus.SKIP:
                self._done_queue.append(job)
                self.skipped_elements.append(element)
                continue

            self.prepare(element)
            ready.append(job)

        # These were not ready but were in the beginning, give em
        # first priority again next time around
        self._wait_queue.extendleft(unready)

        return ready

    def peek_ready_jobs(self):
        def ready(job):
            return self.status(job.element) == QueueStatus.READY

        yield from (job for job in self._wait_queue if ready(job))

    #####################################################
    #                 Private Methods                   #
    #####################################################

    # _update_workspaces()
    #
    # Updates and possibly saves the workspaces in the
    # main data model in the main process after a job completes.
    #
    # Args:
    #    element (Element): The element which completed
    #    job (Job): The job which completed
    #
    def _update_workspaces(self, element, job):
        workspace_dict = None
        if job.child_data:
            workspace_dict = job.child_data.get('workspace', None)

        # Handle any workspace modifications now
        #
        if workspace_dict:
            context = element._get_context()
            workspaces = context.get_workspaces()
            if workspaces.update_workspace(element._get_full_name(), workspace_dict):
                try:
                    workspaces.save_config()
                except BstError as e:
                    self._message(element, MessageType.ERROR, "Error saving workspaces", detail=str(e))
                except Exception as e:   # pylint: disable=broad-except
                    self._message(element, MessageType.BUG,
                                  "Unhandled exception while saving workspaces",
                                  detail=traceback.format_exc())

    # _job_done()
    #
    # A callback reported by the Job() when a job completes
    #
    # This will call the Queue implementation specific Queue.done()
    # implementation and trigger the scheduler to reschedule.
    #
    # See the Job object for an explanation of the call signature
    #
    def _job_done(self, job, element, success, result):

        # Update values that need to be synchronized in the main task
        # before calling any queue implementation
        self._update_workspaces(element, job)

        # Give the result of the job to the Queue implementor,
        # and determine if it should be considered as processed
        # or skipped.
        try:
            self.done(job, element, result, success)
        except BstError as e:

            # Report error and mark as failed
            #
            self._message(element, MessageType.ERROR, "Post processing error", detail=str(e))
            self.failed_elements.append(element)

            # Treat this as a task error as it's related to a task
            # even though it did not occur in the task context
            #
            # This just allows us stronger testing capability
            #
            set_last_task_error(e.domain, e.reason)

        except Exception as e:   # pylint: disable=broad-except

            # Report unhandled exceptions and mark as failed
            #
            self._message(element, MessageType.BUG,
                          "Unhandled exception in post processing",
                          detail=traceback.format_exc())
            self.failed_elements.append(element)
        else:

            # No exception occured, handle the success/failure state in the normal way
            #
            if success:
                self._done_queue.append(job)
                if not job.skipped:
                    self.processed_elements.append(element)
                else:
                    self.skipped_elements.append(element)
            else:
                self.failed_elements.append(element)

    # Convenience wrapper for Queue implementations to send
    # a message for the element they are processing
    def _message(self, element, message_type, brief, **kwargs):
        context = element._get_context()
        message = Message(element._get_unique_id(), message_type, brief, **kwargs)
        context.message(message)

    def _element_log_path(self, element):
        project = element._get_project()
        key = element._get_display_key()[1]
        action = self.action_name.lower()
        logfile = "{key}-{action}".format(key=key, action=action)

        return os.path.join(project.name, element.normal_name, logfile)
