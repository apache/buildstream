#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Author:
#        Tristan Daniël Maat <tristan.maat@codethink.co.uk>
#

from .job import Job, ChildJob


# ElementJob()
#
# A job to run an element's commands. When this job is started
# `action_cb` will be called, and when it completes `complete_cb` will
# be called.
#
# Args:
#    scheduler (Scheduler): The scheduler
#    action_name (str): The queue action name
#    max_retries (int): The maximum number of retries
#    action_cb (callable): The function to execute on the child
#    complete_cb (callable): The function to execute when the job completes
#    element (Element): The element to work on
#    kwargs: Remaining Job() constructor arguments
#
# Here is the calling signature of the action_cb:
#
#     action_cb():
#
#     This function will be called in the child task
#
#     Args:
#        element (Element): The element passed to the Job() constructor
#
#     Returns:
#        (object): Any abstract simple python object, including a string, int,
#                  bool, list or dict, this must be a simple serializable object.
#
# Here is the calling signature of the complete_cb:
#
#     complete_cb():
#
#     This function will be called when the child task completes
#
#     Args:
#        job (Job): The job object which completed
#        element (Element): The element passed to the Job() constructor
#        status (JobStatus): The status of whether the workload raised an exception
#        result (object): The deserialized object returned by the `action_cb`, or None
#                         if `success` is False
#
class ElementJob(Job):
    def __init__(self, *args, element, queue, action_cb, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_name(element._get_full_name())
        self.queue = queue
        self._element = element  # Set the Element pertaining to the job
        self._action_cb = action_cb  # The action callable function
        self._complete_cb = complete_cb  # The complete callable function

        # Set the plugin element name & key for logging purposes
        self.set_message_element_name(self.name)
        self.set_message_element_key(self._element._get_display_key())

    def parent_complete(self, status, result):
        self._complete_cb(self, self._element, status, self._result)

    def create_child_job(self, *args, **kwargs):
        return ChildElementJob(*args, element=self._element, action_cb=self._action_cb, **kwargs)


class ChildElementJob(ChildJob):
    def __init__(self, *args, element, action_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self._element = element
        self._action_cb = action_cb

    def child_process(self):

        # Run the action
        return self._action_cb(self._element)
