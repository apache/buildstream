#
#  Copyright (C) 2019 Bloomberg Finance LP
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

import datetime
from collections import OrderedDict


# TaskGroup
#
# The state data stored for a group of tasks (usually scheduler queues)
#
# Args:
#    name (str): The name of the Task Group, e.g. 'build'
#    state (State): The state object
#    complete_name (str): Optional name for frontend status rendering, e.g. 'built'
#
class TaskGroup:
    def __init__(self, name, state, complete_name=None):
        self.name = name
        self.complete_name = complete_name
        self.processed_tasks = 0
        self.skipped_tasks = 0
        # NOTE: failed_tasks is a list of strings instead of an integer count
        #       because the frontend requires the full list of failed tasks to
        #       know whether to print failure messages for a given element.
        self.failed_tasks = []

        self._state = state
        self._update_task_group_cbs = []

    ###########################################
    # Core-facing APIs to drive notifications #
    ###########################################

    # add_processed_task()
    #
    # Update the TaskGroup's count of processed tasks and notify of changes
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_processed_task(self):
        self.processed_tasks += 1
        for cb in self._state._task_groups_changed_cbs:
            cb()

    # add_skipped_task()
    #
    # Update the TaskGroup's count of skipped tasks and notify of changes
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_skipped_task(self):
        self.skipped_tasks += 1

        for cb in self._state._task_groups_changed_cbs:
            cb()

    # add_failed_task()
    #
    # Update the TaskGroup's list of failed tasks and notify of changes
    #
    # Args:
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_failed_task(self, full_name):
        self.failed_tasks.append(full_name)

        for cb in self._state._task_groups_changed_cbs:
            cb()


# State
#
# The state data that is stored for the purpose of sharing with the frontend.
#
# BuildStream's Core is responsible for making changes to this data.
# BuildStream's Frontend may register callbacks with State to be notified
# when parts of State change, and read State to know what has changed.
#
# Args:
#    session_start (datetime): The time the session started
#
class State:
    def __init__(self, session_start):
        self._session_start = session_start

        self.task_groups = OrderedDict()  # key is TaskGroup name

        # Note: A Task's full_name is technically unique, but only accidentally.
        self.tasks = OrderedDict()  # key is a tuple of action_name and full_name

        self._task_added_cbs = []
        self._task_removed_cbs = []
        self._task_changed_cbs = []
        self._task_groups_changed_cbs = []
        self._task_failed_cbs = []
        self._task_retry_cbs = []

    #####################################
    # Frontend-facing notification APIs #
    #####################################

    # register_task_added_callback()
    #
    # Registers a callback to be notified when a task is added
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #
    def register_task_added_callback(self, callback):
        self._task_added_cbs.append(callback)

    # unregister_task_added_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_added_callback()
    #
    # Args:
    #    callback (function): The callback to be removed
    #
    def unregister_task_added_callback(self, callback):
        self._task_added_cbs.remove(callback)

    # register_task_removed_callback()
    #
    # Registers a callback to be notified when a task is removed
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #
    def register_task_removed_callback(self, callback):
        self._task_removed_cbs.append(callback)

    # unregister_task_removed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_removed_callback()
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    def unregister_task_removed_callback(self, callback):
        self._task_removed_cbs.remove(callback)

    # register_task_changed_callback()
    #
    # Register a callback to be notified when a task has changed
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #
    def register_task_changed_callback(self, callback):
        self._task_changed_cbs.append(callback)

    # unregister_task_changed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_changed_callback()
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    def unregister_task_changed_callback(self, callback):
        self._task_changed_cbs.remove(callback)

    # register_task_failed_callback()
    #
    # Registers a callback to be notified when a task has failed
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #    element_job (bool): (optionally) If an element job failed.
    #
    def register_task_failed_callback(self, callback):
        self._task_failed_cbs.append(callback)

    # unregister_task_failed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_failed_callback()
    #
    # Args:
    #    callback (function): The callback to be removed
    #
    def unregister_task_failed_callback(self, callback):
        self._task_failed_cbs.remove(callback)

    # register_task_retry_callback()
    #
    # Registers a callback to be notified when a task is to be retried
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #    element_job (bool): (optionally) If an element job failed.
    #
    def register_task_retry_callback(self, callback):
        self._task_retry_cbs.append(callback)

    ##############################################
    # Core-facing APIs for driving notifications #
    ##############################################

    # add_task_group()
    #
    # Notification that a new task group has been added
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    name (str): The name of the task group, e.g. 'build'
    #    complete_name (str): Optional name to be used for frontend status rendering, e.g. 'built'
    #
    # Returns:
    #    TaskGroup: The task group created
    #
    def add_task_group(self, name, complete_name=None):
        assert name not in self.task_groups, "Trying to add task group '{}' to '{}'".format(name, self.task_groups)
        group = TaskGroup(name, self, complete_name)
        self.task_groups[name] = group

        return group

    # remove_task_group()
    #
    # Notification that a task group has been removed
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    name (str): The name of the task group, e.g. 'build'
    #
    def remove_task_group(self, name):
        # Rely on 'del' to raise an error when removing nonexistent task groups
        del self.task_groups[name]

    # add_task()
    #
    # Add a task and send appropriate notifications
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #    elapsed_offset (timedelta): (Optional) The time the task started, relative
    #                                to buildstream's start time. Note scheduler tasks
    #                                use this as they don't report relative to wallclock time
    #                                if the Scheduler has been suspended.
    #
    def add_task(self, action_name, full_name, elapsed_offset=None):
        task_key = (action_name, full_name)
        assert task_key not in self.tasks, "Trying to add task '{}:{}' to '{}'".format(
            action_name, full_name, self.tasks
        )

        if not elapsed_offset:
            elapsed_offset = self.elapsed_time()

        task = _Task(self, action_name, full_name, elapsed_offset)
        self.tasks[task_key] = task

        for cb in self._task_added_cbs:
            cb(action_name, full_name)

        return task

    # remove_task()
    #
    # Remove the task and send appropriate notifications
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #
    def remove_task(self, action_name, full_name):
        # Rely on 'del' to raise an error when removing nonexistent tasks
        del self.tasks[(action_name, full_name)]

        for cb in self._task_removed_cbs:
            cb(action_name, full_name)

    # fail_task()
    #
    # Notify all registered callbacks that a task has failed.
    #
    # This is separate from the tasks changed callbacks because a failed task
    # requires the frontend to intervene to decide what happens next.
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    action_name (str): The name of the action, e.g. 'build'
    #    full_name (str): The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #    element (tuple): (optionally) The element unique_id and display keys if an
    #                                  element job
    #
    def fail_task(self, action_name, full_name, element=None):
        for cb in self._task_failed_cbs:
            cb(action_name, full_name, element)

    # retry_task()
    #
    # Notify all registered callbacks that a task is to be retried.
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    action_name: The name of the action, e.g. 'build'
    #    unique_id: The unique id of the plugin instance to look up
    #
    def retry_task(self, action_name: str, unique_id: str) -> None:
        for cb in self._task_retry_cbs:
            cb(action_name, unique_id)

    # elapsed_time()
    #
    # Fetches the current session elapsed time
    #
    # Args:
    #    start_time(time): Optional explicit start time, relative to caller.
    #
    # Returns:
    #    (timedelta): The amount of time since the start of the session,
    #                 discounting any time spent while jobs were suspended if
    #                 start_time given relative to the Scheduler
    #
    def elapsed_time(self, start_time=None):
        time_now = datetime.datetime.now()
        if start_time is None:
            start_time = self._session_start or time_now
        return time_now - start_time

    # offset_start_time()
    #
    # Update the 'start' time of the application by a given offset
    #
    # This allows modifying the time spent building when BuildStream
    # gets paused then restarted, to give an accurate view of the real
    # time spend building.
    #
    # Args:
    #   offset: the offset to add to the start time
    #
    def offset_start_time(self, offset: datetime.timedelta) -> None:
        self._session_start += offset


# _Task
#
# The state data stored for an individual task
#
# Args:
#    state (State): The State object
#    action_name (str): The name of the action, e.g. 'build'
#    full_name (str): The full name of the task, distinguishing
#                     it from other tasks with the same action name
#                     e.g. an element's name.
#    elapsed_offset (timedelta): The time the task started, relative to
#                                buildstream's start time.
class _Task:
    def __init__(self, state, action_name, full_name, elapsed_offset):
        self._state = state
        self.action_name = action_name
        self.full_name = full_name
        self.elapsed_offset = elapsed_offset
        self.current_progress = None
        self.maximum_progress = None

        self._render_cb = None  # Callback to call when something could be rendered

    # set_render_cb()
    #
    # Sets the callback to be called when the Task has changed and should be rendered
    #
    # NOTE: This should probably be removed once the frontend is running
    #       separately from the scheduler, since renders could be triggered
    #       by the scheduler.
    def set_render_cb(self, callback):
        self._render_cb = callback

    def set_current_progress(self, progress):
        self.current_progress = progress
        for cb in self._state._task_changed_cbs:
            cb(self.action_name, self.full_name)
        if self._render_cb:
            self._render_cb()

    def set_maximum_progress(self, progress):
        self.maximum_progress = progress
        for cb in self._state._task_changed_cbs:
            cb(self.action_name, self.full_name)

        if self._render_cb:
            self._render_cb()

    def add_current_progress(self):
        if self.current_progress is None:
            new_progress = 1
        else:
            new_progress = self.current_progress + 1
        self.set_current_progress(new_progress)
