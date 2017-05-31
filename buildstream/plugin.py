#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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
import datetime
import subprocess
import signal
import sys
from subprocess import CalledProcessError
from contextlib import contextmanager
from weakref import WeakValueDictionary
import psutil

from . import _yaml, _signals
from . import utils
from . import PluginError, ImplError
from .exceptions import _BstError
from ._message import Message, MessageType


class Plugin():
    """Plugin()

    Base Plugin class.

    Some common features to both Sources and Elements are found
    in this class.
    """
    def __init__(self, name, context, project, provenance, type_tag):

        self.name = name
        """The plugin name

        For elements, this is the project relative bst filename,
        for sources this is the owning element's name with a suffix
        indicating it's index on the owning element.

        For sources this is for display purposes only.
        """

        self.__context = context        # The Context object
        self.__project = project        # The Project object
        self.__provenance = provenance  # The Provenance information
        self.__type_tag = type_tag      # The type of plugin (element or source)
        self.__unique_id = _plugin_register(self)  # Unique ID
        self.__log = None               # The log handle when running a task

        self.debug("Created: {}".format(self))

    def __del__(self):
        # Dont send anything through the Message() pipeline at destruction time,
        # any subsequent lookup of plugin by unique id would raise KeyError.
        if self.__context.log_debug:
            print("DEBUG: Destroyed: {}".format(self))

    def __str__(self):
        return "{kind} {typetag} at {provenance}".format(
            kind=self.get_kind(),
            typetag=self.__type_tag,
            provenance=self.__provenance)

    def get_kind(self):
        """Fetches the kind of this plugin

        Returns:
           (str): The kind of this plugin
        """
        modulename = type(self).__module__
        return modulename.split('.')[-1]

    def get_context(self):
        """Fetches the context

        Returns:
           (object): The :class:`.Context`
        """
        return self.__context

    def get_project(self):
        """Fetches the project

        Returns:
           (object): The :class:`.Project`
        """
        return self.__project

    def node_items(self, node):
        """Iterate over a dictionary loaded from YAML

        Args:
            node (dict): The YAML loaded dictionary object

        Returns:
           list: List of key/value tuples to iterate over

        BuildStream holds some private data in dictionaries loaded from
        the YAML in order to preserve information to report in errors.

        This convenience function should be used instead of the dict.items()
        builtin function provided by python.
        """
        for key, value in node.items():
            if key == _yaml.PROVENANCE_KEY:
                continue
            yield (key, value)

    def node_provenance(self, node, member_name=None):
        """Gets the provenance for `node` and `member_name`

        This reports a string with file, line and column information suitable
        for reporting an error or warning.

        Args:
            node (dict): The YAML loaded dictionary object
            member_name (str): The name of the member to check, or None for the node itself

        Returns:
            (str): A string describing the provenance of the node and member
        """
        provenance = _yaml.node_get_provenance(node, key=member_name)
        return str(provenance)

    def node_get_member(self, node, expected_type, member_name, default_value=None):
        """Fetch the value of a node member, raising an error if the value is
        missing or incorrectly typed.

        Args:
           node (dict): A dictionary loaded from YAML
           expected_type (type): The expected type of the node member
           member_name (str): The name of the member to fetch
           default_value (expected_type): A value to return when *member_name* is not specified in *node*

        Returns:
           The value of *member_name* in *node*, otherwise *default_value*

        Raises:
           :class:`.LoadError`: When *member_name* is not found and no *default_value* was provided

        Note:
           Returned strings are stripped of leading and trailing whitespace

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node'
          name = self.node_get_member(node, str, 'name')

          # Fetch an optional integer
          level = self.node_get_member(node, int, 'level', -1)
        """
        return _yaml.node_get(node, expected_type, member_name, default_value=default_value)

    def node_get_list_element(self, node, expected_type, member_name, indices):
        """Fetch the value of a list element from a node member, raising an error if the
        value is incorrectly typed.

        Args:
           node (dict): A dictionary loaded from YAML
           expected_type (type): The expected type of the node member
           member_name (str): The name of the member to fetch
           indices (list of int): List of indices to search, in case of nested lists

        Returns:
           The value of the list element in *member_name* at the specified *indices*

        Raises:
           :class:`.LoadError`

        Note:
           Returned strings are stripped of leading and trailing whitespace

        **Example:**

        .. code:: python

          # Fetch the list itself
          things = self.node_get_member(node, list, 'things')

          # Iterate over the list indices
          for i in range(len(things)):

              # Fetch dict things
              thing = self.node_get_list_element(
                  node, dict, 'things', [ i ])
        """
        return _yaml.node_get(node, expected_type, member_name, indices=indices)

    def configure(self, node):
        """Configure the Plugin from loaded configuration data

        Args:
           node (dict): The loaded configuration dictionary

        Raises:
           :class:`.SourceError`: If its a :class:`.Source` implementation
           :class:`.ElementError`: If its an :class:`.Element` implementation
           :class:`.LoadError`: If one of the *node* handling methods fail

        Plugin implementors should implement this method to read configuration
        data and store it. Use of the :func:`~buildstream.plugin.Plugin.node_get_member`
        convenience method will ensure that a nice :class:`.LoadError` is triggered
        whenever the YAML input configuration is faulty.

        Implementations may raise :class:`.SourceError` or :class:`.ElementError` for other errors.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement configure()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    def preflight(self):
        """Preflight Check

        Raises:
           :class:`.SourceError`: If its a :class:`.Source` implementation
           :class:`.ElementError`: If its an :class:`.Element` implementation
           :class:`.ProgramNotFoundError`: If a required host tool is not found

        This method is run after :func:`~buildstream.plugin.Plugin.configure` and
        after the pipeline is fully constructed. :class:`.Element` plugins are free
        to use the :func:`~buildstream.element.Element.dependencies` method and inspect
        public data at this time.

        Implementors should simply raise :class:`.SourceError` or :class:`.ElementError`
        with an informative message in the case that the host environment is
        unsuitable for operation.

        Plugins which require host tools (only sources usually) should obtain
        them with :func:`.utils.get_host_tool` which will raise
        :class:`.ProgramNotFoundError` automatically.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement preflight()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    def get_unique_key(self):
        """Return something which uniquely identifies the plugin input

        Returns:
           A string, list or dictionary which uniquely identifies the sources to use

        This is used to construct unique cache keys for elements and sources,
        sources should return something which uniquely identifies the payload,
        such as an sha256 sum of a tarball content. Elements should implement
        this by collecting any configurations which could possibly effect the
        output and return a dictionary of these settings.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement get_unique_key()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    def debug(self, brief, detail=None):
        """Print a debugging message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        if self.__context.log_debug:
            self.__message(MessageType.DEBUG, brief, detail=detail)

    def status(self, brief, detail=None):
        """Print a status message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output

        Note: Status messages tell about what a plugin is currently doing
        """
        self.__message(MessageType.STATUS, brief, detail=detail)

    def info(self, brief, detail=None):
        """Print an informative message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output

        Note: Informative messages tell the user something they might want
              to know, like if refreshing an element caused it to change.
        """
        self.__message(MessageType.INFO, brief, detail=detail)

    def warn(self, brief, detail=None):
        """Print a warning message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        self.__message(MessageType.WARN, brief, detail=detail)

    def error(self, brief, detail=None):
        """Print an error message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        self.__message(MessageType.ERROR, brief, detail=detail)

    @contextmanager
    def timed_activity(self, activity_name, silent_nested=False):
        """Context manager for performing timed activities in plugins

        Args:
           activity_name (str): The name of the activity
           silent_nested (bool): If specified, nested messages will be silenced

        This function lets you perform timed tasks in your plugin,
        the core will take care of timing the duration of your
        task and printing start / fail / success messages.

        **Example**

        .. code:: python

          # Activity will be logged and timed
          with self.timed_activity("Mirroring {}".format(self.url)):

              # This will raise SourceError on its own
              self.call(... command which takes time ...)
        """
        starttime = datetime.datetime.now()
        stopped_time = None

        def stop_time():
            nonlocal stopped_time
            stopped_time = datetime.datetime.now()

        def resume_time():
            nonlocal stopped_time
            nonlocal starttime
            sleep_time = datetime.datetime.now() - stopped_time
            starttime += sleep_time

        with _signals.suspendable(stop_time, resume_time):
            try:
                # Push activity depth for status messages
                self.__message(MessageType.START, activity_name)
                self.__context._push_message_depth(silent_nested)
                yield

            except _BstError as e:
                # Note the failure in status messages and reraise, the scheduler
                # expects an error when there is an error.
                elapsed = datetime.datetime.now() - starttime
                self.__context._pop_message_depth()
                self.__message(MessageType.FAIL, activity_name, elapsed=elapsed)
                raise

            elapsed = datetime.datetime.now() - starttime
            self.__context._pop_message_depth()
            self.__message(MessageType.SUCCESS, activity_name, elapsed=elapsed)

    def call(self, *popenargs, fail=None, **kwargs):
        """A wrapper for subprocess.call()

        Args:
           popenargs (list): Popen() arguments
           fail (str): A message to display if the process returns
                       a non zero exit code
           rest_of_args (kwargs): Remaining arguments to subprocess.call()

        Returns:
           (int): The process exit code.

        Raises:
           (:class:`.PluginError`): If a non-zero return code is received and *fail* is specified

        Note: If *fail* is not specified, then the return value of subprocess.call()
              is returned even on error, and no exception is automatically raised.

        **Example**

        .. code:: python

          # Call some host tool
          self.tool = utils.get_host_tool('toolname')
          self.call(
              [self.tool, '--download-ponies', self.mirror_directory],
              "Failed to download ponies from {}".format(
                  self.mirror_directory))
        """
        exit_code, _ = self.__call(*popenargs, fail=fail, **kwargs)
        return exit_code

    def check_output(self, *popenargs, fail=None, **kwargs):
        """A wrapper for subprocess.check_output()

        Args:
           popenargs (list): Popen() arguments
           fail (str): A message to display if the process returns
                       a non zero exit code
           rest_of_args (kwargs): Remaining arguments to subprocess.call()

        Returns:
           (int): The process exit code
           (str): The process standard output

        Raises:
           (:class:`.PluginError`): If a non-zero return code is received and *fail* is specified

        Note: If *fail* is not specified, then the return value of subprocess.check_output()
              is returned even on error, and no exception is automatically raised.

        **Example**

        .. code:: python

          # Get the tool at preflight time
          self.tool = utils.get_host_tool('toolname')

          # Call the tool, automatically raise an error
          _, output = self.check_output(
              [self.tool, '--print-ponies'],
              "Failed to print the ponies in {}".format(
                  self.mirror_directory),
              cwd=self.mirror_directory)

          # Call the tool, inspect exit code
          exit_code, output = self.check_output(
              [self.tool, 'get-ref', tracking],
              cwd=self.mirror_directory)

          if exit_code == 128:
              return
          elif exit_code != 0:
              fmt = "{plugin}: Failed to get ref for tracking: {track}"
              raise SourceError(
                  fmt.format(plugin=self, track=tracking)) from e
        """
        return self.__call(*popenargs, collect_stdout=True, fail=fail, **kwargs)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _get_unique_id():
    #
    # Fetch the plugin's unique identifier
    #
    def _get_unique_id(self):
        return self.__unique_id

    # _get_provenance():
    #
    # Fetch bst file, line and column of the entity
    #
    def _get_provenance(self):
        return self.__provenance

    # Accessor for logging handle
    #
    def _get_log_handle(self, log):
        return self.__log

    # Mutator for logging handle
    #
    def _set_log_handle(self, log):
        self.__log = log

    # Context manager for getting the open file handle to this
    # plugin's log. Used in the child context to add stuff to
    # a log.
    #
    @contextmanager
    def _output_file(self):
        if 'BST_TEST_SUITE' in os.environ:
            yield sys.stdout
        elif not self.__log:
            with open(os.devnull, "w") as output:
                yield output
        else:
            yield self.__log

    #############################################################
    #                     Local Private Methods                 #
    #############################################################

    # Internal subprocess implementation for the call() and check_output() APIs
    #
    def __call(self, *popenargs, collect_stdout=False, fail=None, **kwargs):

        if 'stdout' in kwargs or 'stderr' in kwargs:
            raise ValueError('May not override destination output')

        with self._output_file() as output_file:
            kwargs['stdout'] = output_file
            kwargs['stderr'] = output_file
            kwargs['start_new_session'] = True
            if collect_stdout:
                kwargs['stdout'] = subprocess.PIPE

            self.__note_command(output_file, *popenargs, **kwargs)

            # Handle termination, suspend and resume
            def kill_proc():
                if process:
                    # FIXME: This is a brutal but reliable approach
                    #
                    # Other variations I've tried which try SIGTERM first
                    # and then wait for child processes to exit gracefully
                    # have not reliably cleaned up process trees and have
                    # left orphaned git or ssh processes alive.
                    #
                    # This cleans up the subprocesses reliably but may
                    # cause side effects such as possibly leaving stale
                    # locks behind. Hopefully this should not be an issue
                    # as long as any child processes only interact with
                    # the temp directories which we control and cleanup
                    # ourselves.
                    #
                    proc = psutil.Process(process.pid)
                    children = proc.children(recursive=True)
                    for child in children:
                        child.kill()
                    proc.kill()

            def suspend_proc():
                if process:
                    group_id = os.getpgid(process.pid)
                    os.killpg(group_id, signal.SIGSTOP)

            def resume_proc():
                if process:
                    group_id = os.getpgid(process.pid)
                    os.killpg(group_id, signal.SIGCONT)

            with _signals.suspendable(suspend_proc, resume_proc), _signals.terminator(kill_proc):
                process = subprocess.Popen(*popenargs, **kwargs)
                output, _ = process.communicate()
                exit_code = process.poll()

            if fail and exit_code:
                raise PluginError("{plugin}: {message}".format(plugin=self, message=fail))

            # Program output is returned as bytes, we want utf8 strings
            if output is not None:
                output = output.decode('UTF-8')

        return (exit_code, output)

    def __message(self, message_type, brief, **kwargs):
        message = Message(self.__unique_id, message_type, brief, **kwargs)
        self.__context._message(message)

    def __note_command(self, output, *popenargs, **kwargs):
        workdir = os.getcwd()
        if 'cwd' in kwargs:
            workdir = kwargs['cwd']
        command = " ".join(popenargs[0])
        output.write('Running host command {}: {}\n'.format(workdir, command))
        output.flush()
        self.status('Running host command', detail=command)


# Hold on to a lookup table by counter of all instantiated plugins.
# We use this to send the id back from child processes so we can lookup
# corresponding element/source in the master process.
#
# Use WeakValueDictionary() so the map we use to lookup objects does not
# keep the plugins alive after pipeline destruction.
#
# Note that Plugins can only be instantiated in the main process before
# scheduling tasks.
__PLUGINS_UNIQUE_ID = 0
__PLUGINS_TABLE = WeakValueDictionary()


# _plugin_lookup():
#
# Fetch a plugin in the current process by its
# unique identifier
#
# Args:
#    unique_id: The unique identifier as returned by
#               plugin._get_unique_id()
#
# Returns:
#    (Plugin): The plugin for the given ID, or None
#
def _plugin_lookup(unique_id):
    try:
        plugin = __PLUGINS_TABLE[unique_id]
    except (AttributeError, KeyError) as e:
        print("Could not find plugin with ID {}".format(unique_id))
        raise

    return plugin


# No need for unregister, WeakValueDictionary() will remove entries
# in itself when the referenced plugins are garbage collected.
def _plugin_register(plugin):
    global __PLUGINS_UNIQUE_ID
    __PLUGINS_UNIQUE_ID += 1
    __PLUGINS_TABLE[__PLUGINS_UNIQUE_ID] = plugin
    return __PLUGINS_UNIQUE_ID
