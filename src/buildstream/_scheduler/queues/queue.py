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
import heapq
import traceback

# Local imports
from ..jobs import ElementJob, JobStatus
from ..resources import ResourceType

# BuildStream toplevel imports
from ..._exceptions import BstError, ImplError, set_last_task_error
from ..._message import Message, MessageType


# Queue status for a given element
#
#
class QueueStatus(Enum):
    # The element is not yet ready to be processed in the queue.
    PENDING = 1

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
        self._resources = scheduler.resources  # Shared resource pool
        self._ready_queue = []                 # Ready elements
        self._done_queue = deque()             # Processed / Skipped elements
        self._max_retries = 0

        self._required_element_check = False   # Whether we should check that elements are required before enqueuing

        # Assert the subclass has setup class data
        assert self.action_name is not None
        assert self.complete_name is not None

        if ResourceType.UPLOAD in self.resources or ResourceType.DOWNLOAD in self.resources:
            self._max_retries = scheduler.context.sched_network_retries

    #####################################################
    #     Abstract Methods for Queue implementations    #
    #####################################################

    # get_process_func()
    #
    # Abstract method, returns a callable for processing an element.
    #
    # The callable should fit the signature `process(element: Element) -> any`.
    #
    # Note that the callable may be executed in a child process, so the return
    # value should be a simple object (must be pickle-able, i.e. strings,
    # lists, dicts, numbers, but not Element instances). This is sent to back
    # to the main process.
    #
    # This method is the only way for a queue to affect elements, and so is
    # not optional to implement.
    #
    # Returns:
    #    (Callable[[Element], Any]): The callable for processing elements.
    #
    def get_process_func(self):
        raise NotImplementedError()

    # status()
    #
    # Abstract method for reporting the immediate status of an element. The status
    # determines whether an element can/cannot be pushed into the queue, or even
    # skip the queue entirely, when called.
    #
    # Args:
    #    element (Element): An element to process
    #
    # Returns:
    #    (QueueStatus): The element status
    #
    def status(self, element):
        return QueueStatus.READY

    # done()
    #
    # Abstract method for handling a successful job completion.
    #
    # Args:
    #    job (Job): The job which completed processing
    #    element (Element): The element which completed processing
    #    result (any): The return value of the process() implementation
    #    status (JobStatus): The return status of the Job
    #
    def done(self, job, element, result, status):
        pass

    #####################################################
    #      Virtual Methods for Queue implementations    #
    #####################################################

    # register_pending_element()
    #
    # Virtual method for registering a queue specific callback
    # to an Element which is not immediately ready to advance
    # to the next queue
    #
    # Args:
    #    element (Element): The element waiting to be pushed into the queue
    #
    def register_pending_element(self, element):
        raise ImplError("Queue type: {} does not implement register_pending_element()"
                        .format(self.action_name))

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

        # Obtain immediate element status
        for elt in elts:
            if self._required_element_check and not elt._is_required():
                elt._set_required_callback(self._enqueue_element)
            else:
                self._enqueue_element(elt)

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
            yield self._done_queue.popleft()

    # dequeue_ready()
    #
    # Reports whether any elements can be promoted to other queues
    #
    # Returns:
    #    (bool): Whether there are elements ready
    #
    def dequeue_ready(self):
        return any(self._done_queue)

    # harvest_jobs()
    #
    # Spawn as many jobs from the ready queue for which resources
    # can be reserved.
    #
    # Returns:
    #     ([Job]): A list of jobs which can be run now
    #
    def harvest_jobs(self):
        ready = []
        while self._ready_queue:
            # Now reserve them
            reserved = self._resources.reserve(self.resources)
            if not reserved:
                break

            _, element = heapq.heappop(self._ready_queue)
            ready.append(element)

        return [
            ElementJob(self._scheduler, self.action_name,
                       self._element_log_path(element),
                       element=element, queue=self,
                       action_cb=self.get_process_func(),
                       complete_cb=self._job_done,
                       max_retries=self._max_retries)
            for element in ready
        ]

    # set_required_element_check()
    #
    # This ensures that, for the first non-track queue, we must check
    # whether elements are required before enqueuing them
    def set_required_element_check(self):
        self._required_element_check = True

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
                except Exception:   # pylint: disable=broad-except
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
    def _job_done(self, job, element, status, result):

        # Now release the resources we reserved
        #
        self._resources.release(self.resources)

        # Update values that need to be synchronized in the main task
        # before calling any queue implementation
        self._update_workspaces(element, job)

        # Give the result of the job to the Queue implementor,
        # and determine if it should be considered as processed
        # or skipped.
        try:
            self.done(job, element, result, status)
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

        except Exception:   # pylint: disable=broad-except

            # Report unhandled exceptions and mark as failed
            #
            self._message(element, MessageType.BUG,
                          "Unhandled exception in post processing",
                          detail=traceback.format_exc())
            self.failed_elements.append(element)
        else:
            # All elements get placed on the done queue for later processing.
            self._done_queue.append(element)

            # These lists are for bookkeeping purposes for the UI and logging.
            if status is JobStatus.SKIPPED or job.get_terminated():
                self.skipped_elements.append(element)
            elif status is JobStatus.OK:
                self.processed_elements.append(element)
            else:
                self.failed_elements.append(element)

    # Convenience wrapper for Queue implementations to send
    # a message for the element they are processing
    def _message(self, element, message_type, brief, **kwargs):
        context = element._get_context()
        message = Message(element._unique_id, message_type, brief, **kwargs)
        context.messenger.message(message)

    def _element_log_path(self, element):
        project = element._get_project()
        key = element._get_display_key()[1]
        action = self.action_name.lower()
        logfile = "{key}-{action}".format(key=key, action=action)

        return os.path.join(project.name, element.normal_name, logfile)

    # _enqueue_element()
    #
    # Enqueue an Element upon a callback to a specific queue
    # Here we check whether an element is either immediately ready to be processed
    # in the current queue or whether it can skip the queue. Element's which are
    # not yet ready to be processed or cannot skip will have the appropriate
    # callback registered
    #
    # Args:
    #    element (Element): The Element to enqueue
    #
    def _enqueue_element(self, element):
        status = self.status(element)
        if status == QueueStatus.SKIP:
            # Place skipped elements into the done queue immediately
            self.skipped_elements.append(element)       # Public record of skipped elements
            self._done_queue.append(element)            # Elements to proceed to the next queue
        elif status == QueueStatus.READY:
            # Push elements which are ready to be processed immediately into the queue
            heapq.heappush(self._ready_queue, (element._depth, element))
        else:
            # Register a queue specific callback for pending elements
            self.register_pending_element(element)
