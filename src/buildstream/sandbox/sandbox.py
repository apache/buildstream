#
#  Copyright (C) 2017 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
"""
Sandbox - The build sandbox
===========================
:class:`.Element` plugins which want to interface with the sandbox
need only understand this interface, while it may be given a different
sandbox implementation, any sandbox implementation it is given will
conform to this interface.

See also: :ref:`sandboxing`.
"""

import os
import shlex
import contextlib
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional, TYPE_CHECKING

from .._exceptions import ImplError, SandboxError
from .._message import Message, MessageType
from ..storage.directory import Directory
from ..storage._casbaseddirectory import CasBasedDirectory

if TYPE_CHECKING:
    from typing import Union

    # pylint: disable=cyclic-import
    from .._context import Context
    from .._project import Project

    # pylint: enable=cyclic-import


class SandboxFlags:
    """Flags indicating how the sandbox should be run.
    """

    NONE = 0
    """Use default sandbox configuration.
    """

    ROOT_READ_ONLY = 0x01
    """The root filesystem is read only.

    This is normally true except when running integration commands
    on staged dependencies, where we have to update caches and run
    things such as ldconfig.
    """

    NETWORK_ENABLED = 0x02
    """Whether to expose host network.

    This should not be set when running builds, but can
    be allowed for running a shell in a sandbox.
    """

    INTERACTIVE = 0x04
    """Whether to run the sandbox interactively

    This determines if the sandbox should attempt to connect
    the terminal through to the calling process, or detach
    the terminal entirely.
    """

    INHERIT_UID = 0x08
    """Whether to use the user id and group id from the host environment

    This determines if processes in the sandbox should run with the
    same user id and group id as BuildStream itself. By default,
    processes run with user id and group id 0, protected by a user
    namespace where available.
    """


class SandboxCommandError(SandboxError):
    """Raised by :class:`.Sandbox` implementations when a command fails.

    Args:
       message (str): The error message to report to the user
       detail (str): The detailed error string
       collect (str): An optional directory containing partial install contents
       reason (str): An optional reason string (defaults to 'command-failed')
    """

    def __init__(self, message, *, detail=None, collect=None, reason="command-failed"):
        super().__init__(message, detail=detail, reason=reason)

        self.collect = collect


class Sandbox:
    """Sandbox()

    Sandbox programming interface for :class:`.Element` plugins.
    """

    # Minimal set of devices for the sandbox
    DEVICES = ["/dev/urandom", "/dev/random", "/dev/zero", "/dev/null"]
    _dummy_reasons = []  # type: List[str]

    def __init__(self, context: "Context", project: "Project", directory: str, **kwargs):
        self.__context = context
        self.__project = project
        self.__directories = []  # type: List[Dict[str, Union[int, str]]]
        self.__cwd = None  # type: Optional[str]
        self.__env = None  # type: Optional[Dict[str, str]]
        self.__mount_sources = {}  # type: Dict[str, str]
        self.__allow_run = True

        # Plugin element full name for logging
        plugin = kwargs.get("plugin", None)
        if plugin:
            self.__element_name = plugin._get_full_name()
        else:
            self.__element_name = None

        # Configuration from kwargs common to all subclasses
        self.__config = kwargs["config"]
        self.__stdout = kwargs["stdout"]
        self.__stderr = kwargs["stderr"]

        self._output_directory = None  # type: Optional[str]
        self._build_directory = None
        self._build_directory_always = None
        self._vdir = None  # type: Optional[Directory]
        self._usebuildtree = False

        # Pending command batch
        self.__batch = None

    def get_virtual_directory(self) -> Directory:
        """Fetches the sandbox root directory as a virtual Directory.

        The root directory is where artifacts for the base
        runtime environment should be staged.

        Returns:
           The sandbox root directory

        """
        if self._vdir is None:
            cascache = self.__context.get_cascache()
            self._vdir = CasBasedDirectory(cascache)
        return self._vdir

    def set_environment(self, environment: Dict[str, str]) -> None:
        """Sets the environment variables for the sandbox

        Args:
           environment: The environment variables to use in the sandbox
        """
        self.__env = environment

    def set_work_directory(self, directory: str) -> None:
        """Sets the work directory for commands run in the sandbox

        Args:
           directory: An absolute path within the sandbox
        """
        self.__cwd = directory

    def set_output_directory(self, directory: str) -> None:
        """Sets the output directory - the directory which is preserved
        as an artifact after assembly.

        Args:
           directory: An absolute path within the sandbox
        """
        self._output_directory = directory

    def mark_directory(self, directory: str, *, artifact: bool = False) -> None:
        """Marks a sandbox directory and ensures it will exist

        Args:
           directory: An absolute path within the sandbox to mark
           artifact: Whether the content staged at this location
                     contains artifacts

        .. note::
           Any marked directories will be read-write in the sandboxed
           environment, only the root directory is allowed to be readonly.
        """
        self.__directories.append({"directory": directory, "artifact": artifact})

    def run(
        self,
        command: List[str],
        flags: int,
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        label: str = None
    ) -> Optional[int]:
        """Run a command in the sandbox.

        If this is called outside a batch context, the command is immediately
        executed.

        If this is called in a batch context, the command is added to the batch
        for later execution. If the command fails, later commands will not be
        executed. Command flags must match batch flags.

        Args:
            command: The command to run in the sandboxed environment, as a list
                     of strings starting with the binary to run.
            flags (:class:`.SandboxFlags`): The flags for running this command.
            cwd: The sandbox relative working directory in which to run the command.
            env: A dictionary of string key, value pairs to set as environment
                 variables inside the sandbox environment.
            label: An optional label for the command, used for logging.

        Returns:
            The program exit code, or None if running in batch context.

        Raises:
            (:class:`.ProgramNotFoundError`): If a host tool which the given sandbox
                                              implementation requires is not found.

        .. note::

           The optional *cwd* argument will default to the value set with
           :func:`~buildstream.sandbox.Sandbox.set_work_directory` and this
           function must make sure the directory will be created if it does
           not exist yet, even if a workspace is being used.
        """

        if not self.__allow_run:
            raise SandboxError("Sandbox.run() has been disabled")

        # Fallback to the sandbox default settings for
        # the cwd and env.
        #
        cwd = self._get_work_directory(cwd=cwd)
        env = self._get_environment(cwd=cwd, env=env)

        assert cwd.startswith("/"), "The working directory must be an absolute path"

        # Convert single-string argument to a list
        if isinstance(command, str):
            command = [command]

        if self.__batch:
            assert flags == self.__batch.flags, "Inconsistent sandbox flags in single command batch"

            batch_command = _SandboxBatchCommand(command, cwd=cwd, env=env, label=label)

            current_group = self.__batch.current_group
            current_group.append(batch_command)
            return None
        else:
            return self._run(command, flags, cwd=cwd, env=env)

    @contextmanager
    def batch(self, flags: int, *, label: str = None, collect: str = None) -> Generator[None, None, None]:
        """Context manager for command batching

        This provides a batch context that defers execution of commands until
        the end of the context. If a command fails, the batch will be aborted
        and subsequent commands will not be executed.

        Command batches may be nested. Execution will start only when the top
        level batch context ends.

        Args:
            flags (:class:`.SandboxFlags`): The flags for this command batch.
            label: An optional label for the batch group, used for logging.
            collect: An optional directory containing partial install contents
                           on command failure.

        Raises:
            (:class:`.SandboxCommandError`): If a command fails.
        """

        group = _SandboxBatchGroup(label=label)

        if self.__batch:
            # Nested batch
            assert flags == self.__batch.flags, "Inconsistent sandbox flags in single command batch"

            parent_group = self.__batch.current_group
            parent_group.append(group)
            self.__batch.current_group = group
            try:
                yield
            finally:
                self.__batch.current_group = parent_group
        else:
            # Top-level batch
            batch = self._create_batch(group, flags, collect=collect)

            self.__batch = batch
            try:
                yield
            finally:
                self.__batch = None

            batch.execute()

    #####################################################
    #    Abstract Methods for Sandbox implementations   #
    #####################################################

    # _run()
    #
    # Abstract method for running a single command
    #
    # Args:
    #    command (list): The command to run in the sandboxed environment, as a list
    #                    of strings starting with the binary to run.
    #    flags (:class:`.SandboxFlags`): The flags for running this command.
    #    cwd (str): The sandbox relative working directory in which to run the command.
    #    env (dict): A dictionary of string key, value pairs to set as environment
    #                variables inside the sandbox environment.
    #
    # Returns:
    #    (int): The program exit code.
    #
    def _run(self, command, flags, *, cwd, env):
        raise ImplError("Sandbox of type '{}' does not implement _run()".format(type(self).__name__))

    # _create_batch()
    #
    # Abstract method for creating a batch object. Subclasses can override
    # this method to instantiate a subclass of _SandboxBatch.
    #
    # Args:
    #    main_group (:class:`_SandboxBatchGroup`): The top level batch group.
    #    flags (:class:`.SandboxFlags`): The flags for commands in this batch.
    #    collect (str): An optional directory containing partial install contents
    #                   on command failure.
    #
    def _create_batch(self, main_group, flags, *, collect=None):
        return _SandboxBatch(self, main_group, flags, collect=collect)

    # _fetch_missing_blobs()
    #
    # Fetch required file blobs missing from the local cache for sandboxes using
    # remote execution. This is a no-op for local sandboxes.
    #
    # Args:
    #    vdir (Directory): The virtual directory whose blobs to fetch
    #
    def _fetch_missing_blobs(self, vdir):
        pass

    ################################################
    #               Private methods                #
    ################################################
    # _get_context()
    #
    # Fetches the context BuildStream was launched with.
    #
    # Returns:
    #    (Context): The context of this BuildStream invocation
    def _get_context(self):
        return self.__context

    # _get_project()
    #
    # Fetches the Project this sandbox was created to build for.
    #
    # Returns:
    #    (Project): The project this sandbox was created for.
    def _get_project(self):
        return self.__project

    # _get_marked_directories()
    #
    # Fetches the marked directories in the sandbox
    #
    # Returns:
    #    (list): A list of directory mark objects.
    #
    # The returned objects are dictionaries with the following attributes:
    #    directory: The absolute path within the sandbox
    #    artifact: Whether the path will contain artifacts or not
    #
    def _get_marked_directories(self):
        return self.__directories

    # _get_mount_source()
    #
    # Fetches the list of mount sources
    #
    # Returns:
    #    (dict): A dictionary where keys are mount points and values are the mount sources
    def _get_mount_sources(self):
        return self.__mount_sources

    # _set_mount_source()
    #
    # Sets the mount source for a given mountpoint
    #
    # Args:
    #    mountpoint (str): The absolute mountpoint path inside the sandbox
    #    mount_source (str): the host path to be mounted at the mount point
    def _set_mount_source(self, mountpoint, mount_source):
        self.__mount_sources[mountpoint] = mount_source

    # _get_environment()
    #
    # Fetches the environment variables for running commands
    # in the sandbox.
    #
    # Args:
    #    cwd (str): The working directory the command has been requested to run in, if any.
    #    env (str): The environment the command has been requested to run in, if any.
    #
    # Returns:
    #    (str): The sandbox work directory
    def _get_environment(self, *, cwd=None, env=None):
        cwd = self._get_work_directory(cwd=cwd)
        if env is None:
            env = self.__env

        # Naive getcwd implementations can break when bind-mounts to different
        # paths on the same filesystem are present. Letting the command know
        # what directory it is in makes it unnecessary to call the faulty
        # getcwd.
        env = dict(env)
        env["PWD"] = cwd

        return env

    # _get_work_directory()
    #
    # Fetches the working directory for running commands
    # in the sandbox.
    #
    # Args:
    #    cwd (str): The working directory the command has been requested to run in, if any.
    #
    # Returns:
    #    (str): The sandbox work directory
    def _get_work_directory(self, *, cwd=None) -> str:
        return cwd or self.__cwd or "/"

    # _get_output()
    #
    # Fetches the stdout & stderr
    #
    # Returns:
    #    (file): The stdout, or None to inherit
    #    (file): The stderr, or None to inherit
    def _get_output(self):
        return (self.__stdout, self.__stderr)

    # _get_config()
    #
    # Fetches the sandbox configuration object.
    #
    # Returns:
    #    (SandboxConfig): An object containing the configuration
    #              data passed in during construction.
    def _get_config(self):
        return self.__config

    # _has_command()
    #
    #  Tests whether a command exists inside the sandbox
    #
    #     Args:
    #         command (list): The command to test.
    #         env (dict): A dictionary of string key, value pairs to set as environment
    #                     variables inside the sandbox environment.
    #     Returns:
    #         (bool): Whether a command exists inside the sandbox.
    def _has_command(self, command, env=None):
        vroot = self.get_virtual_directory()
        command_as_parts = command.lstrip(os.sep).split(os.sep)
        if os.path.isabs(command):
            return vroot.exists(*command_as_parts, follow_symlinks=True)

        if len(command_as_parts) > 1:
            return False

        for path in env.get("PATH").split(":"):
            path_as_parts = path.lstrip(os.sep).split(os.sep)
            if vroot.exists(*path_as_parts, command, follow_symlinks=True):
                return True

        return False

    # _create_empty_file()
    #
    # Creates an empty file in the current working directory.
    #
    # If this is called outside a batch context, the file is created
    # immediately.
    #
    # If this is called in a batch context, creating the file is deferred.
    #
    # Args:
    #    path (str): The path of the file to be created
    #
    def _create_empty_file(self, name):
        if self.__batch:
            batch_file = _SandboxBatchFile(name)

            current_group = self.__batch.current_group
            current_group.append(batch_file)
        else:
            vdir = self.get_virtual_directory()
            cwd = self._get_work_directory()
            cwd_vdir = vdir.descend(*cwd.lstrip(os.sep).split(os.sep), create=True)
            cwd_vdir._create_empty_file(name)

    # _get_element_name()
    #
    # Get the plugin's element full name
    #
    def _get_element_name(self):
        return self.__element_name

    # _disable_run()
    #
    # Raise exception if `Sandbox.run()` is called. This enables use of
    # CasBasedDirectory for faster staging when command execution is not
    # required.
    #
    def _disable_run(self):
        self.__allow_run = False

    # _set_build_directory()
    #
    # Sets the build directory - the directory which may be preserved as
    # buildtree in the artifact.
    #
    # Args:
    #    directory (str): An absolute path within the sandbox
    #    always (bool): True if the build directory should always be downloaded,
    #                   False if it should be downloaded only on failure
    #
    def _set_build_directory(self, directory, *, always):
        self._build_directory = directory
        self._build_directory_always = always


# _SandboxBatch()
#
# A batch of sandbox commands.
#
class _SandboxBatch:
    def __init__(self, sandbox, main_group, flags, *, collect=None):
        self.sandbox = sandbox
        self.main_group = main_group
        self.current_group = main_group
        self.flags = flags
        self.collect = collect

    def execute(self):
        self.main_group.execute(self)

    def execute_group(self, group):
        if group.label:
            context = self.sandbox._get_context()
            cm = context.messenger.timed_activity(group.label, element_name=self.sandbox._get_element_name())
        else:
            cm = contextlib.suppress()

        with cm:
            group.execute_children(self)

    def execute_command(self, command):
        if command.label:
            context = self.sandbox._get_context()
            message = Message(
                MessageType.STATUS,
                "Running command",
                detail=command.label,
                element_name=self.sandbox._get_element_name(),
            )
            context.messenger.message(message)

        exitcode = self.sandbox._run(command.command, self.flags, cwd=command.cwd, env=command.env)
        if exitcode != 0:
            cmdline = " ".join(shlex.quote(cmd) for cmd in command.command)
            label = command.label or cmdline
            raise SandboxCommandError(
                "Command failed with exitcode {}".format(exitcode), detail=label, collect=self.collect
            )

    def create_empty_file(self, name):
        vdir = self.sandbox.get_virtual_directory()
        cwd = self.sandbox._get_work_directory()
        cwd_vdir = vdir.descend(*cwd.lstrip(os.sep).split(os.sep), create=True)
        cwd_vdir._create_empty_file(name)


# _SandboxBatchItem()
#
# An item in a command batch.
#
class _SandboxBatchItem:
    def __init__(self, *, label=None):
        self.label = label

    def combined_label(self):
        return self.label


# _SandboxBatchCommand()
#
# A command item in a command batch.
#
class _SandboxBatchCommand(_SandboxBatchItem):
    def __init__(self, command, *, cwd, env, label=None):
        super().__init__(label=label)

        self.command = command
        self.cwd = cwd
        self.env = env

    def execute(self, batch):
        batch.execute_command(self)


# _SandboxBatchGroup()
#
# A group in a command batch.
#
class _SandboxBatchGroup(_SandboxBatchItem):
    def __init__(self, *, label=None):
        super().__init__(label=label)

        self.children = []

    def append(self, item):
        self.children.append(item)

    def execute(self, batch):
        batch.execute_group(self)

    def execute_children(self, batch):
        for item in self.children:
            item.execute(batch)

    def combined_label(self):
        return "\n".join(filter(None, (item.combined_label() for item in self.children)))


# _SandboxBatchFile()
#
# A file creation item in a command batch.
#
class _SandboxBatchFile(_SandboxBatchItem):
    def __init__(self, name):
        super().__init__()

        self.name = name

    def execute(self, batch):
        batch.create_empty_file(self.name)
