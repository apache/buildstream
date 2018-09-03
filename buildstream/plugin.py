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
"""
Plugin - Base plugin class
==========================
BuildStream supports third party plugins to define additional kinds of
:mod:`Elements <buildstream.element>` and :mod:`Sources <buildstream.source>`.

The common API is documented here, along with some information on how
external plugin packages are structured.


.. _core_plugin_abstract_methods:

Abstract Methods
----------------
For both :mod:`Elements <buildstream.element>` and :mod:`Sources <buildstream.source>`,
it is mandatory to implement the following abstract methods:

* :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`

  Loads the user provided configuration YAML for the given source or element

* :func:`Plugin.preflight() <buildstream.plugin.Plugin.preflight>`

  Early preflight checks allow plugins to bail out early with an error
  in the case that it can predict that failure is inevitable.

* :func:`Plugin.get_unique_key() <buildstream.plugin.Plugin.get_unique_key>`

  Once all configuration has been loaded and preflight checks have passed,
  this method is used to inform the core of a plugin's unique configuration.


Plugin Structure
----------------
A plugin should consist of a `setuptools package
<http://setuptools.readthedocs.io/en/latest/setuptools.html>`_ that
advertises contained plugins using `entry points
<http://setuptools.readthedocs.io/en/latest/setuptools.html#dynamic-discovery-of-services-and-plugins>`_.

A plugin entry point must be a module that extends a class in the
:ref:`core_framework` to be discovered by BuildStream. A YAML file
defining plugin default settings with the same name as the module can
also be defined in the same directory as the plugin module.

.. note::

    BuildStream does not support function/class entry points.

A sample plugin could be structured as such:

.. code-block:: text

    .
    ├── elements
    │   ├── autotools.py
    │   ├── autotools.yaml
    │   └── __init__.py
    ├── MANIFEST.in
    └── setup.py

The setuptools configuration should then contain at least:

setup.py:

.. literalinclude:: ../source/sample_plugin/setup.py
   :language: python

MANIFEST.in:

.. literalinclude:: ../source/sample_plugin/MANIFEST.in
   :language: text

Class Reference
---------------
"""

import os
import subprocess
from contextlib import contextmanager
from weakref import WeakValueDictionary

from . import _yaml
from . import utils
from ._exceptions import PluginError, ImplError
from ._message import Message, MessageType


class Plugin():
    """Plugin()

    Base Plugin class.

    Some common features to both Sources and Elements are found
    in this class.

    .. note::

        Derivation of plugins is not supported. Plugins may only
        derive from the base :mod:`Source <buildstream.source>` and
        :mod:`Element <buildstream.element>` types, and any convenience
        subclasses (like :mod:`BuildElement <buildstream.buildelement>`)
        which are included in the buildstream namespace.
    """

    BST_REQUIRED_VERSION_MAJOR = 0
    """Minimum required major version"""

    BST_REQUIRED_VERSION_MINOR = 0
    """Minimum required minor version"""

    BST_FORMAT_VERSION = 0
    """The plugin's YAML format version

    This should be set to ``1`` the first time any new configuration
    is understood by your :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`
    implementation and subsequently bumped every time your
    configuration is enhanced.

    .. note::

       Plugins are expected to maintain backward compatibility
       in the format and configurations they expose. The versioning
       is intended to track availability of new features only.

       For convenience, the format version for plugins maintained and
       distributed with BuildStream are revisioned with BuildStream's
       core format version :ref:`core format version <project_format_version>`.
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
        self.__configuring = False      # Whether we are currently configuring

        # Infer the kind identifier
        modulename = type(self).__module__
        self.__kind = modulename.split('.')[-1]

        self.debug("Created: {}".format(self))

    def __del__(self):
        # Dont send anything through the Message() pipeline at destruction time,
        # any subsequent lookup of plugin by unique id would raise KeyError.
        if self.__context.log_debug:
            print("DEBUG: Destroyed: {}".format(self))

    def __str__(self):
        return "{kind} {typetag} at {provenance}".format(
            kind=self.__kind,
            typetag=self.__type_tag,
            provenance=self.__provenance)

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def configure(self, node):
        """Configure the Plugin from loaded configuration data

        Args:
           node (dict): The loaded configuration dictionary

        Raises:
           :class:`.SourceError`: If its a :class:`.Source` implementation
           :class:`.ElementError`: If its an :class:`.Element` implementation

        Plugin implementors should implement this method to read configuration
        data and store it.

        Plugins should use the :func:`Plugin.node_get_member() <buildstream.plugin.Plugin.node_get_member>`
        and :func:`Plugin.node_get_list_element() <buildstream.plugin.Plugin.node_get_list_element>`
        methods to fetch values from the passed `node`. This will ensure that a nice human readable error
        message will be raised if the expected configuration is not found, indicating the filename,
        line and column numbers.

        Further the :func:`Plugin.node_validate() <buildstream.plugin.Plugin.node_validate>` method
        should be used to ensure that the user has not specified keys in `node` which are unsupported
        by the plugin.

        .. note::

           For Elements, when variable substitution is desirable, the
           :func:`Element.node_subst_member() <buildstream.element.Element.node_subst_member>`
           and :func:`Element.node_subst_list_element() <buildstream.element.Element.node_subst_list_element>`
           methods can be used.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement configure()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    def preflight(self):
        """Preflight Check

        Raises:
           :class:`.SourceError`: If its a :class:`.Source` implementation
           :class:`.ElementError`: If its an :class:`.Element` implementation

        This method is run after :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`
        and after the pipeline is fully constructed.

        Implementors should simply raise :class:`.SourceError` or :class:`.ElementError`
        with an informative message in the case that the host environment is
        unsuitable for operation.

        Plugins which require host tools (only sources usually) should obtain
        them with :func:`utils.get_host_tool() <buildstream.utils.get_host_tool>` which
        will raise an error automatically informing the user that a host tool is needed.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement preflight()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    def get_unique_key(self):
        """Return something which uniquely identifies the plugin input

        Returns:
           A string, list or dictionary which uniquely identifies the input

        This is used to construct unique cache keys for elements and sources,
        sources should return something which uniquely identifies the payload,
        such as an sha256 sum of a tarball content.

        Elements and Sources should implement this by collecting any configurations
        which could possibly effect the output and return a dictionary of these settings.

        For Sources, this is guaranteed to only be called if
        :func:`Source.get_consistency() <buildstream.source.Source.get_consistency>`
        has not returned :func:`Consistency.INCONSISTENT <buildstream.source.Consistency.INCONSISTENT>`
        which is to say that the Source is expected to have an exact *ref* indicating
        exactly what source is going to be staged.
        """
        raise ImplError("{tag} plugin '{kind}' does not implement get_unique_key()".format(
            tag=self.__type_tag, kind=self.get_kind()))

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def get_kind(self):
        """Fetches the kind of this plugin

        Returns:
           (str): The kind of this plugin
        """
        return self.__kind

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
        yield from _yaml.node_items(node)

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

    def node_get_member(self, node, expected_type, member_name, default=utils._sentinel):
        """Fetch the value of a node member, raising an error if the value is
        missing or incorrectly typed.

        Args:
           node (dict): A dictionary loaded from YAML
           expected_type (type): The expected type of the node member
           member_name (str): The name of the member to fetch
           default (expected_type): A value to return when *member_name* is not specified in *node*

        Returns:
           The value of *member_name* in *node*, otherwise *default*

        Raises:
           :class:`.LoadError`: When *member_name* is not found and no *default* was provided

        Note:
           Returned strings are stripped of leading and trailing whitespace

        **Example:**

        .. code:: python

          # Expect a string 'name' in 'node'
          name = self.node_get_member(node, str, 'name')

          # Fetch an optional integer
          level = self.node_get_member(node, int, 'level', -1)
        """
        return _yaml.node_get(node, expected_type, member_name, default_value=default)

    def node_get_project_path(self, node, key, *,
                              check_is_file=False, check_is_dir=False):
        """Fetches a project path from a dictionary node and validates it

        Paths are asserted to never lead to a directory outside of the
        project directory. In addition, paths can not point to symbolic
        links, fifos, sockets and block/character devices.

        The `check_is_file` and `check_is_dir` parameters can be used to
        perform additional validations on the path. Note that an
        exception will always be raised if both parameters are set to
        ``True``.

        Args:
           node (dict): A dictionary loaded from YAML
           key (str): The key whose value contains a path to validate
           check_is_file (bool): If ``True`` an error will also be raised
                                 if path does not point to a regular file.
                                 Defaults to ``False``
           check_is_dir (bool): If ``True`` an error will also be raised
                                if path does not point to a directory.
                                Defaults to ``False``

        Returns:
           (str): The project path

        Raises:
           :class:`.LoadError`: In the case that the project path is not
                                valid or does not exist

        *Since: 1.2*

        **Example:**

        .. code:: python

          path = self.node_get_project_path(node, 'path')

        """

        return _yaml.node_get_project_path(node, key,
                                           self.__project.directory,
                                           check_is_file=check_is_file,
                                           check_is_dir=check_is_dir)

    def node_validate(self, node, valid_keys):
        """This should be used in :func:`~buildstream.plugin.Plugin.configure`
        implementations to assert that users have only entered
        valid configuration keys.

        Args:
            node (dict): A dictionary loaded from YAML
            valid_keys (iterable): A list of valid keys for the node

        Raises:
            :class:`.LoadError`: When an invalid key is found

        **Example:**

        .. code:: python

          # Ensure our node only contains valid autotools config keys
          self.node_validate(node, [
              'configure-commands', 'build-commands',
              'install-commands', 'strip-commands'
          ])

        """
        _yaml.node_validate(node, valid_keys)

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

    def debug(self, brief, *, detail=None):
        """Print a debugging message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        if self.__context.log_debug:
            self.__message(MessageType.DEBUG, brief, detail=detail)

    def status(self, brief, *, detail=None):
        """Print a status message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output

        Note: Status messages tell about what a plugin is currently doing
        """
        self.__message(MessageType.STATUS, brief, detail=detail)

    def info(self, brief, *, detail=None):
        """Print an informative message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output

        Note: Informative messages tell the user something they might want
              to know, like if refreshing an element caused it to change.
        """
        self.__message(MessageType.INFO, brief, detail=detail)

    def warn(self, brief, *, detail=None):
        """Print a warning message

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        self.__message(MessageType.WARN, brief, detail=detail)

    def log(self, brief, *, detail=None):
        """Log a message into the plugin's log file

        The message will not be shown in the master log at all (so it will not
        be displayed to the user on the console).

        Args:
           brief (str): The brief message
           detail (str): An optional detailed message, can be multiline output
        """
        self.__message(MessageType.LOG, brief, detail=detail)

    @contextmanager
    def timed_activity(self, activity_name, *, detail=None, silent_nested=False):
        """Context manager for performing timed activities in plugins

        Args:
           activity_name (str): The name of the activity
           detail (str): An optional detailed message, can be multiline output
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
        with self.__context.timed_activity(activity_name,
                                           unique_id=self.__unique_id,
                                           detail=detail,
                                           silent_nested=silent_nested):
            yield

    def call(self, *popenargs, fail=None, fail_temporarily=False, **kwargs):
        """A wrapper for subprocess.call()

        Args:
           popenargs (list): Popen() arguments
           fail (str): A message to display if the process returns
                       a non zero exit code
           fail_temporarily (bool): Whether any exceptions should
                                    be raised as temporary. (*Since: 1.2*)
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
        exit_code, _ = self.__call(*popenargs, fail=fail, fail_temporarily=fail_temporarily, **kwargs)
        return exit_code

    def check_output(self, *popenargs, fail=None, fail_temporarily=False, **kwargs):
        """A wrapper for subprocess.check_output()

        Args:
           popenargs (list): Popen() arguments
           fail (str): A message to display if the process returns
                       a non zero exit code
           fail_temporarily (bool): Whether any exceptions should
                                    be raised as temporary. (*Since: 1.2*)
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
        return self.__call(*popenargs, collect_stdout=True, fail=fail, fail_temporarily=fail_temporarily, **kwargs)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _get_context()
    #
    # Fetches the invocation context
    #
    def _get_context(self):
        return self.__context

    # _get_project()
    #
    # Fetches the project object associated with this plugin
    #
    def _get_project(self):
        return self.__project

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

    # Context manager for getting the open file handle to this
    # plugin's log. Used in the child context to add stuff to
    # a log.
    #
    @contextmanager
    def _output_file(self):
        log = self.__context.get_log_handle()
        if log is None:
            with open(os.devnull, "w") as output:
                yield output
        else:
            yield log

    # _configure():
    #
    # Calls configure() for the plugin, this must be called by
    # the core instead of configure() directly, so that the
    # _get_configuring() state is up to date.
    #
    # Args:
    #    node (dict): The loaded configuration dictionary
    #
    def _configure(self, node):
        self.__configuring = True
        self.configure(node)
        self.__configuring = False

    # _get_configuring():
    #
    # Checks whether the plugin is in the middle of having
    # its Plugin.configure() method called
    #
    # Returns:
    #    (bool): Whether we are currently configuring
    def _get_configuring(self):
        return self.__configuring

    # _preflight():
    #
    # Calls preflight() for the plugin, and allows generic preflight
    # checks to be added
    #
    # Raises:
    #    SourceError: If it's a Source implementation
    #    ElementError: If it's an Element implementation
    #    ProgramNotFoundError: If a required host tool is not found
    #
    def _preflight(self):
        self.preflight()

    #############################################################
    #                     Local Private Methods                 #
    #############################################################

    # Internal subprocess implementation for the call() and check_output() APIs
    #
    def __call(self, *popenargs, collect_stdout=False, fail=None, fail_temporarily=False, **kwargs):

        with self._output_file() as output_file:
            if 'stdout' not in kwargs:
                kwargs['stdout'] = output_file
            if 'stderr' not in kwargs:
                kwargs['stderr'] = output_file
            if collect_stdout:
                kwargs['stdout'] = subprocess.PIPE

            self.__note_command(output_file, *popenargs, **kwargs)

            exit_code, output = utils._call(*popenargs, **kwargs)

            if fail and exit_code:
                raise PluginError("{plugin}: {message}".format(plugin=self, message=fail),
                                  temporary=fail_temporarily)

        return (exit_code, output)

    def __message(self, message_type, brief, **kwargs):
        message = Message(self.__unique_id, message_type, brief, **kwargs)
        self.__context.message(message)

    def __note_command(self, output, *popenargs, **kwargs):
        workdir = os.getcwd()
        if 'cwd' in kwargs:
            workdir = kwargs['cwd']
        command = " ".join(popenargs[0])
        output.write('Running host command {}: {}\n'.format(workdir, command))
        output.flush()
        self.status('Running host command', detail=command)

    def _get_full_name(self):
        project = self.__project
        if project.junction:
            return '{}:{}'.format(project.junction.name, self.name)
        else:
            return self.name


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
    assert unique_id in __PLUGINS_TABLE, "Could not find plugin with ID {}".format(unique_id)
    return __PLUGINS_TABLE[unique_id]


# No need for unregister, WeakValueDictionary() will remove entries
# in itself when the referenced plugins are garbage collected.
def _plugin_register(plugin):
    global __PLUGINS_UNIQUE_ID                # pylint: disable=global-statement
    __PLUGINS_UNIQUE_ID += 1
    __PLUGINS_TABLE[__PLUGINS_UNIQUE_ID] = plugin
    return __PLUGINS_UNIQUE_ID
