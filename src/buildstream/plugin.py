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

Configurable Warnings
---------------------
Warnings raised through calling :func:`Plugin.warn() <buildstream.plugin.Plugin.warn>` can provide an optional
parameter ``warning_token``, this will raise a :class:`PluginError` if the warning is configured as fatal within
the project configuration.

Configurable warnings will be prefixed with :func:`Plugin.get_kind() <buildstream.plugin.Plugin.get_kind>`
within buildstream and must be prefixed as such in project configurations. For more detail on project configuration
see :ref:`Configurable Warnings <configurable_warnings>`.

It is important to document these warnings in your plugin documentation to allow users to make full use of them
while configuring their projects.

Example
~~~~~~~
If the :class:`git <buildstream.plugins.sources.git.GitSource>` plugin uses the warning ``"inconsistent-submodule"``
then it could be referenced in project configuration as ``"git:inconsistent-submodule"``.

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

import itertools
import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Generator, Optional, Tuple, TYPE_CHECKING
from weakref import WeakValueDictionary

from . import utils
from ._exceptions import PluginError, ImplError
from ._message import Message, MessageType
from .node import MappingNode, ProvenanceInformation
from .types import CoreWarnings, SourceRef

if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from ._context import Context
    from ._project import Project

    # pylint: enable=cyclic-import


class Plugin:
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

    BST_MIN_VERSION = None
    """The minimum required version of BuildStream required by this plugin.

    The version must be expressed as the string *"<major>.<minor>"*, where the
    *major* version number is the API version and the *minor* version number is
    the revision of the same BuildStream API where new symbols might have been
    added to the API.

    **Example:**

    The following statement means that this plugin works with *BuildStream 2.X*,
    only if *X >= 2*:

    .. code:: python

       class Foo(Source):

           # Our plugin requires 2.2
           BST_MIN_VERSION = "2.2"

    .. note::

       This version works exactly the same was as the :ref:`min-version <project_min_version>`
       which must be specified in the project.conf file.
    """

    BST_PLUGIN_DEPRECATED = False
    """True if this element plugin has been deprecated.

    If this is set to true, BuildStream will emit a deprecation warning
    in any place where this plugin is used.

    The deprecation warnings can be suppressed when defining the
    :ref:`plugin origins in your project configuration <project_plugins_deprecation>`
    """

    BST_PLUGIN_DEPRECATION_MESSAGE = None
    """An additional message to report when a plugin is deprecated

    This can be used to refer the user to a suitable replacement or
    alternative approach when the plugin is deprecated.
    """

    # Unique id generator for Plugins
    #
    # Each plugin gets a unique id at creation.
    #
    # Ids are a monotically increasing integer which
    # starts as 1 (a falsy plugin ID is considered unset
    # in various parts of the codebase).
    #
    __id_generator = itertools.count(1)

    # Hold on to a lookup table by counter of all instantiated plugins.
    # We use this to send the id back from child processes so we can lookup
    # corresponding element/source in the master process.
    #
    # Use WeakValueDictionary() so the map we use to lookup objects does not
    # keep the plugins alive after pipeline destruction.
    #
    # Note that Plugins can only be instantiated in the main process before
    # scheduling tasks.
    __TABLE = WeakValueDictionary()  # type: WeakValueDictionary[int, Plugin]

    def __init__(
        self,
        name: str,
        context: "Context",
        project: "Project",
        provenance: ProvenanceInformation,
        type_tag: str,
        unique_id: Optional[int] = None,
    ):

        self.name = name
        """The plugin name

        For elements, this is the project relative bst filename,
        for sources this is the owning element's name with a suffix
        indicating its index on the owning element.

        For sources this is for display purposes only.
        """

        # Unique ID
        #
        # This id allows to uniquely identify a plugin.
        #
        # /!\ the unique id must be an increasing value /!\
        # This is because we are depending on it in buildstream.element.Element
        # to give us a topological sort over all elements.
        # Modifying how we handle ids here will modify the behavior of the
        # Element's state handling.
        if unique_id is None:
            # Register ourself in the table containing all existing plugins
            self._unique_id = next(self.__id_generator)
            self.__TABLE[self._unique_id] = self
        else:
            # If the unique ID is passed in the constructor, then it is a cloned
            # plugin in a subprocess and should use the same ID.
            self._unique_id = unique_id

        self.__context = context  # The Context object

        # Note that when pickling jobs over to a child process, we rely on this
        # reference to the Project, it keeps the plugin factory alive. If the
        # factory were to be GC'd then we would see undefined behaviour. Make
        # sure to test plugin pickling if this reference is to be removed.
        self.__project = project  # The Project object

        self.__provenance = provenance  # The Provenance information
        self.__type_tag = type_tag  # The type of plugin (element or source)
        self.__configuring = False  # Whether we are currently configuring

        # Get the full_name as project & type_tag are resolved
        self.__full_name = self.__get_full_name()

        # Infer the kind identifier
        modulename = type(self).__module__
        self.__kind = modulename.split(".")[-1]
        self.debug("Created: {}".format(self))

    def __del__(self):
        # Dont send anything through the Message() pipeline at destruction time,
        # any subsequent lookup of plugin by unique id would raise KeyError.
        if self.__context.log_debug:
            sys.stderr.write("DEBUG: Destroyed: {}\n".format(self))

    def __str__(self):
        return "{kind} {typetag} at {provenance}".format(
            kind=self.__kind, typetag=self.__type_tag, provenance=self.__provenance
        )

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def configure(self, node: MappingNode) -> None:
        """Configure the Plugin from loaded configuration data

        Args:
           node: The loaded configuration dictionary

        Raises:
           :class:`.SourceError`: If it's a :class:`.Source` implementation
           :class:`.ElementError`: If it's an :class:`.Element` implementation

        Plugin implementors should implement this method to read configuration
        data and store it.

        The :func:`MappingNode.validate_keys() <buildstream.node.MappingNode.validate_keys>` method
        should be used to ensure that the user has not specified keys in `node` which are unsupported
        by the plugin.

        """
        raise ImplError(
            "{tag} plugin '{kind}' does not implement configure()".format(tag=self.__type_tag, kind=self.get_kind())
        )

    def preflight(self) -> None:
        """Preflight Check

        Raises:
           :class:`.SourceError`: If it's a :class:`.Source` implementation
           :class:`.ElementError`: If it's an :class:`.Element` implementation

        This method is run after :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`
        and after the pipeline is fully constructed.

        Implementors should simply raise :class:`.SourceError` or :class:`.ElementError`
        with an informative message in the case that the host environment is
        unsuitable for operation.

        Plugins which require host tools (only sources usually) should obtain
        them with :func:`utils.get_host_tool() <buildstream.utils.get_host_tool>` which
        will raise an error automatically informing the user that a host tool is needed.
        """
        raise ImplError(
            "{tag} plugin '{kind}' does not implement preflight()".format(tag=self.__type_tag, kind=self.get_kind())
        )

    def get_unique_key(self) -> SourceRef:
        """Return something which uniquely identifies the plugin input

        Returns:
           A string, list or dictionary which uniquely identifies the input

        This is used to construct unique cache keys for elements and sources,
        sources should return something which uniquely identifies the payload,
        such as an sha256 sum of a tarball content.

        Elements and Sources should implement this by collecting any configurations
        which could possibly affect the output and return a dictionary of these settings.

        For Sources, this is guaranteed to only be called if
        :func:`Source.is_resolved() <buildstream.source.Source.is_resolved>`
        has returned `True`
        which is to say that the Source is expected to have an exact *ref* indicating
        exactly what source is going to be staged.
        """
        raise ImplError(
            "{tag} plugin '{kind}' does not implement get_unique_key()".format(
                tag=self.__type_tag, kind=self.get_kind()
            )
        )

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def get_kind(self) -> str:
        """Fetches the kind of this plugin

        Returns:
           The kind of this plugin
        """
        return self.__kind

    def node_get_project_path(self, node, *, check_is_file=False, check_is_dir=False):
        """Fetches a project path from a dictionary node and validates it

        Paths are asserted to never lead to a directory outside of the
        project directory. In addition, paths can not point to symbolic
        links, fifos, sockets and block/character devices.

        The `check_is_file` and `check_is_dir` parameters can be used to
        perform additional validations on the path. Note that an
        exception will always be raised if both parameters are set to
        ``True``.

        Args:
           node (ScalarNode): A Node loaded from YAML containing the path to validate
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

        **Example:**

        .. code:: python

          path = self.node_get_project_path(node, 'path')

        """

        return self.__project.get_path_from_node(node, check_is_file=check_is_file, check_is_dir=check_is_dir)

    def debug(self, brief: str, *, detail: Optional[str] = None) -> None:
        """Print a debugging message

        Args:
           brief: The brief message
           detail: An optional detailed message, can be multiline output
        """
        if self.__context.log_debug:
            self.__message(MessageType.DEBUG, brief, detail=detail)

    def status(self, brief: str, *, detail: Optional[str] = None) -> None:
        """Print a status message

        Args:
           brief: The brief message
           detail: An optional detailed message, can be multiline output

        Note: Status messages tell about what a plugin is currently doing
        """
        self.__message(MessageType.STATUS, brief, detail=detail)

    def info(self, brief: str, *, detail: Optional[str] = None) -> None:
        """Print an informative message

        Args:
           brief: The brief message
           detail: An optional detailed message, can be multiline output

        Note: Informative messages tell the user something they might want
              to know, like if refreshing an element caused it to change.
              The instance full name of the plugin will be generated with the
              message, this being the name of the given element, as appose to
              the class name of the underlying plugin __kind identifier.
        """
        self.__message(MessageType.INFO, brief, detail=detail)

    def warn(self, brief: str, *, detail: Optional[str] = None, warning_token: Optional[str] = None) -> None:
        """Print a warning message, checks warning_token against project configuration

        Args:
           brief: The brief message
           detail: An optional detailed message, can be multiline output
           warning_token: An optional configurable warning assosciated with this warning,
                          this will cause PluginError to be raised if this warning is configured as fatal.

        Raises:
           (:class:`.PluginError`): When warning_token is considered fatal by the project configuration
        """
        if warning_token:
            warning_token = _prefix_warning(self, warning_token)
            brief = "[{}]: {}".format(warning_token, brief)
            project = self._get_project()

            if project._warning_is_fatal(warning_token):
                detail = detail if detail else ""
                raise PluginError(message="{}\n{}".format(brief, detail), reason=warning_token)

        self.__message(MessageType.WARN, brief=brief, detail=detail)

    def log(self, brief: str, *, detail: Optional[str] = None) -> None:
        """Log a message into the plugin's log file

        The message will not be shown in the master log at all (so it will not
        be displayed to the user on the console).

        Args:
           brief: The brief message
           detail: An optional detailed message, can be multiline output
        """
        self.__message(MessageType.LOG, brief, detail=detail)

    @contextmanager
    def timed_activity(
        self, activity_name: str, *, detail: Optional[str] = None, silent_nested: bool = False
    ) -> Generator[None, None, None]:
        """Context manager for performing timed activities in plugins

        Args:
           activity_name: The name of the activity
           detail: An optional detailed message, can be multiline output
           silent_nested: If specified, nested messages will be silenced

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
        with self.__context.messenger.timed_activity(
            activity_name, element_name=self._get_full_name(), detail=detail, silent_nested=silent_nested
        ):
            yield

    def call(self, *popenargs, fail: Optional[str] = None, fail_temporarily: bool = False, **kwargs) -> int:
        """A wrapper for subprocess.call()

        Args:
           popenargs (list): Popen() arguments
           fail: A message to display if the process returns
                 a non zero exit code
           fail_temporarily: Whether any exceptions should
                             be raised as temporary.
           rest_of_args (kwargs): Remaining arguments to subprocess.call()

        Returns:
           The process exit code.

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

    def check_output(self, *popenargs, fail=None, fail_temporarily=False, **kwargs) -> Tuple[int, str]:
        """A wrapper for subprocess.check_output()

        Args:
           popenargs (list): Popen() arguments
           fail (str): A message to display if the process returns
                       a non zero exit code
           fail_temporarily (bool): Whether any exceptions should
                                    be raised as temporary.
           rest_of_args (kwargs): Remaining arguments to subprocess.call()

        Returns:
           A 2-tuple of form (process exit code, process standard output)

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

    # _lookup():
    #
    # Fetch a plugin in the current process by its
    # unique identifier
    #
    # Args:
    #    unique_id: The unique identifier as returned by
    #               plugin._unique_id
    #
    # Returns:
    #    (Plugin): The plugin for the given ID, or None
    #
    @classmethod
    def _lookup(cls, unique_id):
        assert unique_id != 0, "Looking up invalid plugin ID 0, ID counter starts at 1"
        try:
            return cls.__TABLE[unique_id]
        except KeyError:
            assert False, "Could not find plugin with ID {}".format(unique_id)
            raise  # In case a user is running with "python -O"

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
        log = self.__context.messenger.get_log_handle()
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
    #    node (buildstream.node.MappingNode): The loaded configuration dictionary
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

    # _get_full_name():
    #
    # The instance full name of the plugin prepended with the owning
    # junction if appropriate. This being the name of the given element,
    # as appose to the class name of the underlying plugin __kind identifier.
    #
    # Returns:
    #    (str): element full name, with prepended owning junction if appropriate
    #
    def _get_full_name(self):
        return self.__full_name

    #############################################################
    #                     Local Private Methods                 #
    #############################################################

    # Internal subprocess implementation for the call() and check_output() APIs
    #
    def __call(self, *popenargs, collect_stdout=False, fail=None, fail_temporarily=False, **kwargs):

        with self._output_file() as output_file:
            if "stdout" not in kwargs:
                kwargs["stdout"] = output_file
            if "stderr" not in kwargs:
                kwargs["stderr"] = output_file
            if collect_stdout:
                kwargs["stdout"] = subprocess.PIPE

            self.__note_command(output_file, *popenargs, **kwargs)

            exit_code, output = utils._call(*popenargs, **kwargs)

            if fail and exit_code:
                raise PluginError("{plugin}: {message}".format(plugin=self, message=fail), temporary=fail_temporarily)

        return (exit_code, output)

    def __message(self, message_type, brief, **kwargs):
        message = Message(message_type, brief, element_name=self._get_full_name(), **kwargs)
        self.__context.messenger.message(message)

    def __note_command(self, output, *popenargs, **kwargs):
        workdir = kwargs.get("cwd", os.getcwd())
        command = " ".join(popenargs[0])
        output.write("Running host command {}: {}\n".format(workdir, command))
        output.flush()
        self.status("Running host command", detail=command)

    def __get_full_name(self):
        project = self.__project
        # Set the name, depending on element or source plugin type
        name = self._element_name if self.__type_tag == "source" else self.name  # pylint: disable=no-member
        if project.junction:
            return "{}:{}".format(project.junction._get_full_name(), name)
        else:
            return name


# A local table for _prefix_warning()
#
__CORE_WARNINGS = [value for name, value in CoreWarnings.__dict__.items() if not name.startswith("__")]


# _prefix_warning():
#
# Prefix a warning with the plugin kind. CoreWarnings are not prefixed.
#
# Args:
#   plugin (Plugin): The plugin which raised the warning
#   warning (str): The warning to prefix
#
# Returns:
#    (str): A prefixed warning
#
def _prefix_warning(plugin, warning):
    if any((warning is core_warning for core_warning in __CORE_WARNINGS)):
        return warning
    return "{}:{}".format(plugin.get_kind(), warning)
