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
#  Author:
#        Tristan Daniël Maat <tristan.maat@codethink.co.uk>
#
import os
from contextlib import contextmanager

from ruamel import yaml

from ..._message import Message, MessageType
from ...plugin import _plugin_lookup
from ... import _signals

from .job import Job


# ElementJob()
#
# A job to run an element's commands. When this job is spawned
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
#        success (bool): True if the action_cb did not raise an exception
#        result (object): The deserialized object returned by the `action_cb`, or None
#                         if `success` is False
#
class ElementJob(Job):
    def __init__(self, *args, element, queue, action_cb, complete_cb, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue
        self._element = element
        self._action_cb = action_cb            # The action callable function
        self._complete_cb = complete_cb        # The complete callable function

    @property
    def element(self):
        return self._element

    # _child_process()
    #
    # This will be executed after fork(), and is intended to perform
    # the job's task.
    #
    # Returns:
    #    (any): A (simple!) object to be returned to the main thread
    #           as the result.
    #
    def _child_process(self):
        return self._action_cb(self._element)

    def _parent_complete(self, success, result):
        self._complete_cb(self, self._element, success, self._result)

    # _child_logging_enabled()
    #
    # Start the log for this job. This function will be given a
    # template string for the path to a log file - this will contain
    # "{pid}", which should be replaced with the current process'
    # PID. (i.e., call something like `logfile.format(pid=os.getpid())`).
    #
    # Args:
    #    logfile (str): A template string that points to the logfile
    #                   that should be used - replace {pid} first.
    #
    # Yields:
    #    (str) The path to the logfile with {pid} replaced.
    #
    @contextmanager
    def _child_logging_enabled(self, logfile):
        self._logfile = logfile.format(pid=os.getpid())

        with open(self._logfile, 'a') as log:
            # Write one last line to the log and flush it to disk
            def flush_log():

                # If the process currently had something happening in the I/O stack
                # then trying to reenter the I/O stack will fire a runtime error.
                #
                # So just try to flush as well as we can at SIGTERM time
                try:
                    # FIXME: Better logging

                    log.write('\n\nAction {} for element {} forcefully terminated\n'
                              .format(self.action_name, self._element.name))
                    log.flush()
                except RuntimeError:
                    os.fsync(log.fileno())

            self._element._set_log_handle(log)
            with _signals.terminator(flush_log):
                self._print_start_message(self._element, self._logfile)
                yield self._logfile
            self._element._set_log_handle(None)
            self._logfile = None

    # _message():
    #
    # Sends a message to the frontend
    #
    # Args:
    #    message_type (MessageType): The type of message to send
    #    message (str): The message
    #    kwargs: Remaining Message() constructor arguments
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        args['scheduler'] = True
        self._scheduler.context.message(
            Message(self._element._get_unique_id(),
                    message_type,
                    message,
                    **args))

    def _print_start_message(self, element, logfile):
        self._message(MessageType.START, self.action_name, logfile=logfile)

        # Print the element's environment at the beginning of any element's log file.
        #
        # This should probably be omitted for non-build tasks but it's harmless here
        elt_env = element.get_environment()
        env_dump = yaml.round_trip_dump(elt_env, default_flow_style=False, allow_unicode=True)
        self._message(MessageType.LOG,
                      "Build environment for element {}".format(element.name),
                      detail=env_dump, logfile=logfile)

    # _child_log()
    #
    # Log a message returned by the frontend's main message handler
    # and return it to the main process.
    #
    # Arguments:
    #     message (str): The message to log
    #
    # Returns:
    #     message (Message): A message object
    #
    def _child_log(self, message):
        # Tag them on the way out the door...
        message.action_name = self.action_name
        message.task_id = self._element._get_unique_id()

        # Use the plugin for the task for the output, not a plugin
        # which might be acting on behalf of the task
        plugin = _plugin_lookup(message.task_id)

        with plugin._output_file() as output:
            message_text = self._format_frontend_message(message, '[{}]'.format(plugin.name))
            output.write('{}\n'.format(message_text))
            output.flush()

        return message

    # _child_process_data()
    #
    # Abstract method to retrieve additional data that should be
    # returned to the parent process. Note that the job result is
    # retrieved independently.
    #
    # Values can later be retrieved in Job.child_data.
    #
    # Returns:
    #    (dict) A dict containing values later to be read by _process_sync_data
    #
    def _child_process_data(self):
        data = {}

        workspace = self._element._get_workspace()
        artifact_size = self._element._get_artifact_size()
        cache_size = self._element._get_artifact_cache().cache_size

        if workspace is not None:
            data['workspace'] = workspace.to_dict()
        if artifact_size is not None:
            data['artifact_size'] = artifact_size
        data['cache_size'] = cache_size

        return data
