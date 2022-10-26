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

import datetime
from typing import Optional, Tuple, List, Dict, Callable
from .types import _DisplayKey


# TaskGroup
#
# The state data stored for a group of tasks (usually scheduler queues)
#
# Args:
#    name: The name of the Task Group, e.g. 'build'
#    state: The state object
#    complete_name: Optional name for frontend status rendering, e.g. 'built'
#
class TaskGroup:
    def __init__(self, name: str, state: "State", complete_name: Optional[str] = None) -> None:

        #
        # Public members
        #
        self.name: str = name  # The name of tasks in this group
        self.complete_name: Optional[str] = complete_name  # Optional name for frontend status rendering, e.g. 'built'

        self.processed_tasks: int = 0  # Number of processed tasks
        self.skipped_tasks: int = 0  # Number of skipped tasks
        self.failed_tasks: List[str] = []  # List of element full names which failed

        #
        # Private members
        #
        self._state: "State" = state

    ###########################################
    # Core-facing APIs to drive notifications #
    ###########################################

    # add_processed_task()
    #
    # Update the TaskGroup's count of processed tasks and notify of changes
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_processed_task(self) -> None:
        self.processed_tasks += 1
        for cb in self._state._task_groups_changed_cbs:
            cb()

    # add_skipped_task()
    #
    # Update the TaskGroup's count of skipped tasks and notify of changes
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_skipped_task(self) -> None:
        self.skipped_tasks += 1

        for cb in self._state._task_groups_changed_cbs:
            cb()

    # add_failed_task()
    #
    # Update the TaskGroup's list of failed tasks and notify of changes
    #
    # Args:
    #    full_name: The full name of the task, distinguishing
    #               it from other tasks with the same action name
    #               e.g. an element's name.
    #
    # This is a core-facing API and should not be called from the frontend
    #
    def add_failed_task(self, full_name: str) -> None:
        self.failed_tasks.append(full_name)

        for cb in self._state._task_groups_changed_cbs:
            cb()


# Task
#
# The state data stored for an individual task
#
# Args:
#    state: The State object
#    task_id: The unique identifier of the task
#    action_name: The name of the action, e.g. 'build'
#    full_name: The full name of the task, distinguishing
#                     it from other tasks with the same action name
#                     e.g. an element's name.
#    elapsed_offset: The time the task started, relative to
#                                buildstream's start time.
class Task:
    def __init__(
        self, state: "State", task_id: str, action_name: str, full_name: str, elapsed_offset: datetime.timedelta
    ) -> None:

        #
        # Public members
        #
        self.id: str = task_id
        self.action_name: str = action_name
        self.full_name: str = full_name
        self.elapsed_offset: datetime.timedelta = elapsed_offset
        self.current_progress: Optional[int] = None
        self.maximum_progress: Optional[int] = None

        #
        # Private members
        #
        self._state: "State" = state
        self._task_changed_cb: Optional[Callable[[], None]] = None  # Callback to call when something could be rendered

    ##############################################
    # Core-facing APIs for driving notifications #
    ##############################################

    # set_task_changed_callback()
    #
    # Sets the callback to be called when this task has
    # changed.
    #
    # This is just a convenience codepath for the Messenger object
    # run simple tasks outside of the scheduler context, rather
    # than connecting to the State callbacks which are there for the
    # purpose of the frontend to get notifications of task progress.
    #
    # Args:
    #    callback: The callback to call when progress changed
    #
    def set_task_changed_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._task_changed_cb = callback

    # set_maximum_progress()
    #
    # Sets the maximum progress possible for this task.
    #
    # Args:
    #    progress: The maximum progress possible for this task
    #
    def set_maximum_progress(self, progress: int) -> None:
        self.maximum_progress = progress
        self._notify_task_changed()

    # set_current_progress()
    #
    # Sets the current progress of the task, this should
    # be a number between 0 and the maximum progress, if a
    # maximum progress has been set.
    #
    # Args:
    #    progress: The current progress
    #
    def set_current_progress(self, progress: int) -> None:
        self.current_progress = progress
        self._notify_task_changed()

    # add_current_progress()
    #
    # A convenience function for incrementing the current
    # progress of this task by 1.
    #
    def add_current_progress(self) -> None:
        if self.current_progress is None:
            new_progress = 1
        else:
            new_progress = self.current_progress + 1
        self.set_current_progress(new_progress)

    ##############################################
    #             Private methods                #
    ##############################################
    def _notify_task_changed(self) -> None:
        for cb in self._state._task_changed_cbs:
            cb(self.id)

        if self._task_changed_cb:
            self._task_changed_cb()


# State
#
# The state data that is stored for the purpose of sharing with the frontend.
#
# BuildStream's Core is responsible for making changes to this data.
# BuildStream's Frontend may register callbacks with State to be notified
# when parts of State change, and read State to know what has changed.
#
# Args:
#    session_start: The time the session started
#
class State:
    def __init__(self, session_start: datetime.datetime) -> None:

        #
        # Public members
        #
        self.task_groups: Dict[str, TaskGroup] = {}  # Dictionary of active task groups by group name
        self.tasks: Dict[str, Task] = {}  # Dictionary of active tasks by unique task ID

        #
        # Private members
        #
        self._session_start: datetime.datetime = session_start
        self._task_added_cbs: List[Callable[[str], None]] = []
        self._task_removed_cbs: List[Callable[[str], None]] = []
        self._task_changed_cbs: List[Callable[[str], None]] = []
        self._task_failed_cbs: List[Callable[[str, Optional[Tuple[int, _DisplayKey]]], None]] = []
        self._task_groups_changed_cbs: List[Callable[[], None]] = []

    #####################################
    # Frontend-facing notification APIs #
    #####################################

    # register_task_added_callback()
    #
    # Registers a callback to be notified when a task is added
    #
    # Args:
    #    callback: The callback to be notified
    #
    # Callback Args:
    #    task_id: The unique identifier of the task
    #
    def register_task_added_callback(self, callback: Callable[[str], None]) -> None:
        self._task_added_cbs.append(callback)

    # unregister_task_added_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_added_callback()
    #
    # Args:
    #    callback: The callback to be removed
    #
    def unregister_task_added_callback(self, callback: Callable[[str], None]) -> None:
        self._task_added_cbs.remove(callback)

    # register_task_removed_callback()
    #
    # Registers a callback to be notified when a task is removed
    #
    # Args:
    #    callback: The callback to be notified
    #
    # Callback Args:
    #    task_id: The unique identifier of the task
    #
    def register_task_removed_callback(self, callback: Callable[[str], None]) -> None:
        self._task_removed_cbs.append(callback)

    # unregister_task_removed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_removed_callback()
    #
    # Args:
    #    callback: The callback to be notified
    #
    def unregister_task_removed_callback(self, callback: Callable[[str], None]) -> None:
        self._task_removed_cbs.remove(callback)

    # register_task_changed_callback()
    #
    # Register a callback to be notified when a task has changed
    #
    # Args:
    #    callback: The callback to be notified
    #
    # Callback Args:
    #    task_id: The unique identifier of the task
    #
    def register_task_changed_callback(self, callback: Callable[[str], None]) -> None:
        self._task_changed_cbs.append(callback)

    # unregister_task_changed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_changed_callback()
    #
    # Args:
    #    callback: The callback to be notified
    #
    def unregister_task_changed_callback(self, callback: Callable[[str], None]) -> None:
        self._task_changed_cbs.remove(callback)

    # register_task_failed_callback()
    #
    # Registers a callback to be notified when a task has failed
    #
    # Args:
    #    callback (function): The callback to be notified
    #
    # Callback Args:
    #    task_id: The unique identifier of the task
    #    element: (optionally) The element unique_id and DisplayKey of an element job
    #
    def register_task_failed_callback(
        self, callback: Callable[[str, Optional[Tuple[int, _DisplayKey]]], None]
    ) -> None:
        self._task_failed_cbs.append(callback)

    # unregister_task_failed_callback()
    #
    # Unregisters a callback previously registered by
    # register_task_failed_callback()
    #
    # Args:
    #    callback (function): The callback to be removed
    #
    def unregister_task_failed_callback(
        self, callback: Callable[[str, Optional[Tuple[int, _DisplayKey]]], None]
    ) -> None:
        self._task_failed_cbs.remove(callback)

    # register_task_groups_changed_callback()
    #
    # Registers a callback to be notified whenever the task groups info has changed
    #
    # Args:
    #    callback: The callback to be notified
    #
    # Callback Args:
    #    task_id: The unique identifier of the task
    #    element: (optionally) The element unique_id and DisplayKey of an element job
    #
    def register_task_groups_changed_callback(self, callback: Callable[[], None]) -> None:
        self._task_groups_changed_cbs.append(callback)

    # unregister_task_groups_changed_callback()
    #
    # Unregisters a callback previously registered by register_task_groups_changed_callback()
    #
    # Args:
    #    callback (function): The callback to be removed
    #
    def unregister_task_groups_changed_callback(self, callback: Callable[[], None]) -> None:
        self._task_groups_changed_cbs.remove(callback)

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
    def add_task_group(self, name, complete_name=None) -> TaskGroup:
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
    def remove_task_group(self, name) -> None:
        # Rely on 'del' to raise an error when removing nonexistent task groups
        del self.task_groups[name]

    # add_task()
    #
    # Add a task and send appropriate notifications
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    task_id: The unique identifier of the task
    #    action_name: The name of the action, e.g. 'build'
    #    full_name: The full name of the task, distinguishing
    #                     it from other tasks with the same action name
    #                     e.g. an element's name.
    #    elapsed_offset (timedelta): (Optional) The time the task started, relative
    #                                to buildstream's start time. Note scheduler tasks
    #                                use this as they don't report relative to wallclock time
    #                                if the Scheduler has been suspended.
    #
    # Returns:
    #    The new task
    #
    def add_task(
        self, task_id: str, action_name: str, full_name: str, elapsed_offset: Optional[datetime.timedelta] = None
    ) -> Task:
        assert task_id not in self.tasks, "Trying to add task '{}:{}' with ID '{}' to '{}'".format(
            action_name, full_name, task_id, self.tasks
        )

        if not elapsed_offset:
            elapsed_offset = self.elapsed_time()

        task = Task(self, task_id, action_name, full_name, elapsed_offset)
        self.tasks[task_id] = task

        for cb in self._task_added_cbs:
            cb(task_id)

        return task

    # remove_task()
    #
    # Remove the task and send appropriate notifications
    #
    # This is a core-facing API and should not be called from the frontend
    #
    # Args:
    #    task_id: The unique identifier of the task
    #
    def remove_task(self, task_id: str) -> None:
        # Rely on 'del' to raise an error when removing nonexistent tasks
        del self.tasks[task_id]

        for cb in self._task_removed_cbs:
            cb(task_id)

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
    #    task_id: The unique identifier of the task
    #    element: (optionally) The element unique_id and display keys if an
    #                                  element job
    #
    def fail_task(self, task_id: str, element: Optional[Tuple[int, _DisplayKey]] = None) -> None:
        for cb in self._task_failed_cbs:
            cb(task_id, element)

    # elapsed_time()
    #
    # Fetches the current session elapsed time
    #
    # Args:
    #    start_time: Optional explicit start time, relative to caller.
    #
    # Returns:
    #    The amount of time since the start of the session,
    #    discounting any time spent while jobs were suspended if
    #    start_time given relative to the Scheduler
    #
    def elapsed_time(self, start_time: Optional[datetime.datetime] = None) -> datetime.timedelta:
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
