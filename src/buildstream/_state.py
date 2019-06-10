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


from collections import OrderedDict


# TaskGroup
#
# The state data stored for a group of tasks (usually scheduler queues)
#
# Args:
#    name (str): The name of the Task Group, e.g. 'build'
#    state (State): The state object
#
class TaskGroup():
    def __init__(self, name, state):
        self.name = name
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
class State():
    def __init__(self):
        self.task_groups = OrderedDict()  # key is TaskGroup name

        # Note: A Task's full_name is technically unique, but only accidentally.
        self.tasks = OrderedDict()        # key is a tuple of action_name and full_name

        self._task_added_cbs = []
        self._task_removed_cbs = []
        self._task_groups_changed_cbs = []
        self._task_failed_cbs = []

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
    #    unique_id (int): (optionally) the element's unique ID, if the failure
    #                     came from an element
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
    #
    # Returns:
    #    TaskGroup: The task group created
    #
    def add_task_group(self, name):
        assert name not in self.task_groups, "Trying to add task group '{}' to '{}'".format(name, self.task_groups)
        group = TaskGroup(name, self)
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
    #    start_time (timedelta): The time the task started, relative to
    #                            buildstream's start time.
    #
    def add_task(self, action_name, full_name, start_time):
        task_key = (action_name, full_name)
        assert task_key not in self.tasks, \
            "Trying to add task '{}:{}' to '{}'".format(action_name, full_name, self.tasks)

        task = _Task(action_name, full_name, start_time)
        self.tasks[task_key] = task

        for cb in self._task_added_cbs:
            cb(action_name, full_name)

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
    #    unique_id (int): (optionally) the element's unique ID, if the failure came from an element
    #
    def fail_task(self, action_name, full_name, unique_id=None):
        for cb in self._task_failed_cbs:
            cb(action_name, full_name, unique_id)


# _Task
#
# The state data stored for an individual task
#
# Args:
#    action_name (str): The name of the action, e.g. 'build'
#    full_name (str): The full name of the task, distinguishing
#                     it from other tasks with the same action name
#                     e.g. an element's name.
#    start_time (timedelta): The time the task started, relative to
#                            buildstream's start time.
class _Task():
    def __init__(self, action_name, full_name, start_time):
        self.action_name = action_name
        self.full_name = full_name
        self.start_time = start_time
