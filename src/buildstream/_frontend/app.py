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
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

from contextlib import contextmanager
import os
import sys
import threading
import traceback
import datetime
from textwrap import TextWrapper
import click
from click import UsageError

# Import various buildstream internals
from .._context import Context
from .._project import Project
from .._exceptions import BstError, StreamError, LoadError, AppError
from ..exceptions import LoadErrorReason
from .._message import Message, MessageType, unconditional_messages
from .._stream import Stream
from ..types import _SchedulerErrorAction, _Scope
from .. import node
from .. import utils
from ..utils import UtilError

# Import frontend assets
from .profile import Profile
from .status import Status
from .widget import LogLine

# Intendation for all logging
INDENT = 4


# App()
#
# Main Application State
#
# Args:
#    main_options (dict): The main CLI options of the `bst`
#                         command, before any subcommand
#
class App:
    def __init__(self, main_options):

        #
        # Public members
        #
        self.context = None  # The Context object
        self.stream = None  # The Stream object
        self.project = None  # The toplevel Project object
        self.logger = None  # The LogLine object
        self.interactive = None  # Whether we are running in interactive mode
        self.colors = None  # Whether to use colors in logging

        #
        # Private members
        #
        self._session_start = datetime.datetime.now()
        self._session_name = None
        self._main_options = main_options  # Main CLI options, before any command
        self._status = None  # The Status object
        self._fail_messages = {}  # Failure messages by unique plugin id
        self._interactive_failures = None  # Whether to handle failures interactively
        self._started = False  # Whether a session has started
        self._set_project_dir = False  # Whether -C option was used
        self._state = None  # Frontend reads this and registers callbacks

        # UI Colors Profiles
        self._content_profile = Profile(fg="yellow")
        self._format_profile = Profile(fg="cyan", dim=True)
        self._success_profile = Profile(fg="green")
        self._error_profile = Profile(fg="red", dim=True)
        self._detail_profile = Profile(dim=True)

        # Cached messages
        self._cached_message_lock = threading.Lock()
        self._cached_message_text = ""
        self._cache_messages = None

        #
        # Early initialization
        #
        is_a_tty = sys.stdout.isatty() and sys.stderr.isatty()

        # Enable interactive mode if we're attached to a tty
        if main_options["no_interactive"]:
            self.interactive = False
        else:
            self.interactive = is_a_tty

        # Handle errors interactively if we're in interactive mode
        # and --on-error was not specified on the command line
        if main_options.get("on_error") is not None:
            self._interactive_failures = False
        else:
            self._interactive_failures = self.interactive

        # Use color output if we're attached to a tty, unless
        # otherwise specified on the command line
        if main_options["colors"] is None:
            self.colors = is_a_tty
        elif main_options["colors"]:
            self.colors = True
        else:
            self.colors = False

        if main_options["directory"]:
            self._set_project_dir = True
        else:
            main_options["directory"] = os.getcwd()

    # create()
    #
    # Should be used instead of the regular constructor.
    #
    # This will select a platform specific App implementation
    #
    # Args:
    #    The same args as the App() constructor
    #
    @classmethod
    def create(cls, *args, **kwargs):
        if sys.platform.startswith("linux"):
            # Use an App with linux specific features
            from .linuxapp import LinuxApp  # pylint: disable=cyclic-import

            return LinuxApp(*args, **kwargs)
        else:
            # The base App() class is default
            return App(*args, **kwargs)

    # initialized()
    #
    # Context manager to initialize the application and optionally run a session
    # within the context manager.
    #
    # This context manager will take care of catching errors from within the
    # context and report them consistently, so the CLI need not take care of
    # reporting the errors and exiting with a consistent error status.
    #
    # Args:
    #    session_name (str): The name of the session, or None for no session
    #
    # Note that the except_ argument may have a subtly different meaning depending
    # on the activity performed on the Pipeline. In normal circumstances the except_
    # argument excludes elements from the `elements` list. In a build session, the
    # except_ elements are excluded from the tracking plan.
    #
    # If a session_name is provided, we treat the block as a session, and print
    # the session header and summary, and time the main session from startup time.
    #
    @contextmanager
    def initialized(self, *, session_name=None):
        directory = self._main_options["directory"]
        config = self._main_options["config"]

        self._session_name = session_name

        # Instantiate Context
        with Context() as context:
            self.context = context

            #
            # Load the configuration
            #
            try:
                self.context.load(config)
            except BstError as e:
                self._error_exit(e, "Error loading user configuration")

            # Override things in the context from our command line options,
            # the command line when used, trumps the config files.
            #
            override_map = {
                "strict": "_strict_build_plan",
                "debug": "log_debug",
                "verbose": "log_verbose",
                "error_lines": "log_error_lines",
                "message_lines": "log_message_lines",
                "on_error": "sched_error_action",
                "fetchers": "sched_fetchers",
                "builders": "sched_builders",
                "pushers": "sched_pushers",
                "max_jobs": "build_max_jobs",
                "network_retries": "sched_network_retries",
                "pull_buildtrees": "pull_buildtrees",
                "cache_buildtrees": "cache_buildtrees",
            }
            for cli_option, context_attr in override_map.items():
                option_value = self._main_options.get(cli_option)
                if option_value is not None:
                    setattr(self.context, context_attr, option_value)
            try:
                self.context.platform
            except BstError as e:
                self._error_exit(e, "Error instantiating platform")

            # Create the stream right away, we'll need to pass it around.
            self.stream = Stream(
                self.context,
                self._session_start,
                session_start_callback=self.session_start_cb,
                interrupt_callback=self._interrupt_handler,
                ticker_callback=self._render_cached_messages,
            )

            self._state = self.stream.get_state()

            # Register callbacks with the State
            self._state.register_task_failed_callback(self._job_failed)

            # Create the logger right before setting the message handler
            self.logger = LogLine(
                self.context,
                self._state,
                self._content_profile,
                self._format_profile,
                self._success_profile,
                self._error_profile,
                self._detail_profile,
                indent=INDENT,
            )

            # Propagate pipeline feedback to the user
            self.context.messenger.set_message_handler(self._message_handler)

            # Check if throttling frontend updates to tick rate
            self._cache_messages = self.context.log_throttle_updates

            # Allow the Messenger to write status messages
            self.context.messenger.set_render_status_cb(self._render_status)

            # Preflight the artifact cache after initializing logging,
            # this can cause messages to be emitted.
            try:
                self.context.artifactcache.preflight()
            except BstError as e:
                self._error_exit(e, "Error instantiating artifact cache")

            # Now that we have a logger and message handler,
            # we can override the global exception hook.
            sys.excepthook = self._global_exception_handler

            # Initialize the parts of Stream that have side-effects
            self.stream.init()

            # Create our status printer, only available in interactive
            self._status = Status(
                self.context,
                self._state,
                self._content_profile,
                self._format_profile,
                self._success_profile,
                self._error_profile,
                self.stream,
            )

            # Mark the beginning of the session
            if session_name:
                self._message(MessageType.START, session_name)

            #
            # Load the Project
            #
            try:
                self.project = Project(
                    directory,
                    self.context,
                    cli_options=self._main_options["option"],
                    default_mirror=self._main_options.get("default_mirror"),
                )
            except LoadError as e:

                # If there was no project.conf at all then there was just no project found.
                #
                # Don't error out in this case, as Stream() supports some operations which
                # do not require a project. If Stream() requires a project and it is missing,
                # then it will raise an error.
                #
                if e.reason != LoadErrorReason.MISSING_PROJECT_CONF:
                    self._error_exit(e, "Error loading project")

            except BstError as e:
                self._error_exit(e, "Error loading project")

            # Set the project on the Stream, this can be None if there is no project.
            #
            self.stream.set_project(self.project)

            # Run the body of the session here, once everything is loaded
            try:
                yield
            except BstError as e:
                # Check that any cached messages are printed
                self._render_cached_messages()

                # Print a nice summary if this is a session
                if session_name:
                    elapsed = self._state.elapsed_time()

                    if isinstance(e, StreamError) and e.terminated:  # pylint: disable=no-member
                        self._message(MessageType.WARN, session_name + " Terminated", elapsed=elapsed)
                    else:
                        self._message(MessageType.FAIL, session_name, elapsed=elapsed)

                        # Notify session failure
                        self._notify("{} failed".format(session_name), e)

                    if self._started:
                        self._print_summary()

                # Exit with the error
                self._error_exit(e)
            except RecursionError:
                # Check that any cached messages are printed
                self._render_cached_messages()
                click.echo(
                    "RecursionError: Dependency depth is too large. Maximum recursion depth exceeded.", err=True
                )
                sys.exit(-1)
            else:
                # Check that any cached messages are printed
                self._render_cached_messages()

                # No exceptions occurred, print session time and summary
                if session_name:
                    self._message(MessageType.SUCCESS, session_name, elapsed=self._state.elapsed_time())

                    if self._started:
                        self._print_summary()

                    # Notify session success
                    self._notify("{} succeeded".format(session_name), "")

    # init_project()
    #
    # Initialize a new BuildStream project, either with the explicitly passed options,
    # or by starting an interactive session if project_name is not specified and the
    # application is running in interactive mode.
    #
    # Args:
    #    project_name (str): The project name, must be a valid symbol name
    #    min_version (str): The minimum required version of BuildStream (default is current version)
    #    element_path (str): The subdirectory to store elements in, default is 'elements'
    #    force (bool): Allow overwriting an existing project.conf
    #    target_directory (str): The target directory the project should be initialized in
    #
    def init_project(
        self,
        project_name,
        min_version=None,
        element_path="elements",
        force=False,
        target_directory=None,
    ):
        if target_directory:
            directory = os.path.abspath(target_directory)
        else:
            directory = self._main_options["directory"]
            directory = os.path.abspath(directory)

        project_path = os.path.join(directory, "project.conf")

        if min_version is None:
            bst_major, bst_minor = utils.get_bst_version()
            min_version = "{}.{}".format(bst_major, bst_minor)

        try:
            if self._set_project_dir:
                raise AppError(
                    "Attempted to use -C or --directory with init.",
                    reason="init-with-set-directory",
                    detail="Please use 'bst init {}' instead.".format(directory),
                )

            # Abort if the project.conf already exists, unless `--force` was specified in `bst init`
            if not force and os.path.exists(project_path):
                raise AppError("A project.conf already exists at: {}".format(project_path), reason="project-exists")

            if project_name:
                # If project name was specified, user interaction is not desired, just
                # perform some validation and write the project.conf
                node._assert_symbol_name(project_name, "project name")
                self._assert_min_version(min_version)
                self._assert_element_path(element_path)

            elif not self.interactive:
                raise AppError(
                    "Cannot initialize a new project without specifying the project name",
                    reason="unspecified-project-name",
                )
            else:
                # Collect the parameters using an interactive session
                project_name, min_version, element_path = self._init_project_interactive(
                    project_name, min_version, element_path
                )

            # Create the directory if it doesnt exist
            try:
                os.makedirs(directory, exist_ok=True)
            except IOError as e:
                raise AppError("Error creating project directory {}: {}".format(directory, e)) from e

            # Create the elements sub-directory if it doesnt exist
            elements_path = os.path.join(directory, element_path)
            try:
                os.makedirs(elements_path, exist_ok=True)
            except IOError as e:
                raise AppError("Error creating elements sub-directory {}: {}".format(elements_path, e)) from e

            # Dont use ruamel.yaml here, because it doesnt let
            # us programatically insert comments or whitespace at
            # the toplevel.
            try:
                with open(project_path, "w", encoding="utf-8") as f:
                    f.write(
                        "# Unique project name\n"
                        + "name: {}\n\n".format(project_name)
                        + "# Required BuildStream version\n"
                        + "min-version: {}\n\n".format(min_version)
                        + "# Subdirectory where elements are stored\n"
                        + "element-path: {}\n".format(element_path)
                    )
            except IOError as e:
                raise AppError("Error writing {}: {}".format(project_path, e)) from e

        except BstError as e:
            self._error_exit(e)

        click.echo("", err=True)
        click.echo("Created project.conf at: {}".format(project_path), err=True)
        sys.exit(0)

    # shell_prompt():
    #
    # Creates a prompt for a shell environment, using ANSI color codes
    # if they are available in the execution context.
    #
    # Args:
    #    element (Element): The element
    #
    # Returns:
    #    (str): The formatted prompt to display in the shell
    #
    def shell_prompt(self, element):

        element_name = element._get_full_name()
        display_key = element._get_display_key()

        if self.colors:
            dim_key = not display_key.strict
            prompt = (
                self._format_profile.fmt("[")
                + self._content_profile.fmt(display_key.brief, dim=dim_key)
                + self._format_profile.fmt("@")
                + self._content_profile.fmt(element_name)
                + self._format_profile.fmt(":")
                + self._content_profile.fmt("$PWD")
                + self._format_profile.fmt("]$")
                + " "
            )
        else:
            prompt = "[{}@{}:${{PWD}}]$ ".format(display_key.brief, element_name)

        return prompt

    # cleanup()
    #
    # Cleans up application state
    #
    # This is called by Click at exit time
    #
    def cleanup(self):
        if self.stream:
            self.stream.cleanup()

    ############################################################
    #                   Abstract Class Methods                 #
    ############################################################

    # notify()
    #
    # Notify the user of something which occurred, this
    # is intended to grab attention from the user.
    #
    # This is guaranteed to only be called in interactive mode
    #
    # Args:
    #    title (str): The notification title
    #    text (str): The notification text
    #
    def notify(self, title, text):
        pass

    ############################################################
    #                      Local Functions                     #
    ############################################################

    # Local function for calling the notify() virtual method
    #
    def _notify(self, title, text):
        if self.interactive:
            self.notify(str(title), str(text))

    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        self.context.messenger.message(Message(message_type, message, **kwargs))

        # Flush any potentially cached messages immediately
        self._render_cached_messages()

    # Exception handler
    #
    def _global_exception_handler(self, etype, value, tb, exc=True):

        # Print the regular BUG message
        formatted = None
        if exc:
            # Format the exception & traceback by default
            formatted = "".join(traceback.format_exception(etype, value, tb))
        self._message(MessageType.BUG, str(value), detail=formatted)

        # If the scheduler has started, try to terminate all jobs gracefully,
        # otherwise exit immediately.
        if self.stream.running:
            self.stream.terminate()
        else:
            sys.exit(-1)

    #
    # Cache messages
    #
    # Args:
    #    message (Message): The message to cache
    #
    # Returns:
    #    (str): The rendered text of only this message
    #
    def _cache_message(self, message):
        text = self.logger.render(message)

        with self._cached_message_lock:
            self._cached_message_text += text

        return text

    #
    # Render cached messages in case throttling messages during regular sessions
    #
    def _render_cached_messages(self):
        # First clear the status area
        if self._status:
            self._status.clear()

        # Render pending messages
        with self._cached_message_lock:
            if self._cached_message_text:
                click.echo(self._cached_message_text, nl=False, err=True)
                self._cached_message_text = ""

        # Render the status area again
        self._render_status()

    #
    # Render status, this is used in some timed messages while not running the scheduler,
    # and also used to render the status bar in regular sessions.
    #
    def _render_status(self):
        # If we're suspended or terminating, then dont render the status area
        if self._status and self.stream and not (self.stream.suspended or self.stream.terminated):
            self._status.render()

    #
    # Handle ^C SIGINT interruptions in the scheduling main loop
    #
    def _interrupt_handler(self):

        # Only handle ^C interactively in interactive mode
        if not self.interactive:
            self._status.clear()
            self.stream.terminate()
            return

        # Here we can give the user some choices, like whether they would
        # like to continue, abort immediately, or only complete processing of
        # the currently ongoing tasks. We can also print something more
        # intelligent, like how many tasks remain to complete overall.
        with self._interrupted():
            click.echo(
                "\nUser interrupted with ^C\n" + "\n"
                "Choose one of the following options:\n"
                + "  (c)ontinue  - Continue queueing jobs as much as possible\n"
                + "  (q)uit      - Exit after all ongoing jobs complete\n"
                + "  (t)erminate - Terminate any ongoing jobs and exit\n"
                + "\n"
                + "Pressing ^C again will terminate jobs and exit\n",
                err=True,
            )

            try:
                choice = click.prompt(
                    "Choice:",
                    value_proc=_prefix_choice_value_proc(["continue", "quit", "terminate"]),
                    default="continue",
                    err=True,
                )
            except (click.Abort, SystemError):
                # In some cases, the readline buffer underlying the prompt gets corrupted on the second CTRL+C
                # This throws a SystemError, which doesn't seem to be problematic for the rest of the program

                # Ensure a newline after automatically printed '^C'
                click.echo("", err=True)
                choice = "terminate"

            if choice == "terminate":
                click.echo("\nTerminating all jobs at user request\n", err=True)
                self.stream.terminate()
            else:
                if choice == "quit":
                    click.echo("\nCompleting ongoing tasks before quitting\n", err=True)
                    self.stream.quit()
                elif choice == "continue":
                    click.echo("\nContinuing\n", err=True)

    # Callback that a job has failed
    #
    # XXX: This accesses the core directly, which is discouraged.
    #      Removing use of the core would require delegating to Shell
    #      the creation of an interactive shell, and the retrying of jobs.
    #
    # Args:
    #    task_id (str): The unique identifier of the task
    #    element (tuple): If an element job failed a tuple of Element instance unique_id & display key
    #
    def _job_failed(self, task_id, element=None):
        task = self._state.tasks[task_id]

        # Flush any pending messages when handling a failure
        self._render_cached_messages()

        # Dont attempt to handle a failure if the user has already opted to
        # terminate
        if not self.stream.terminated:
            if element:
                # Get the last failure message for additional context
                failure = self._fail_messages.get(task.full_name)

                # XXX This is dangerous, sometimes we get the job completed *before*
                # the failure message reaches us ??
                if not failure:
                    self._status.clear()
                    click.echo(
                        "\n\n\nBUG: Message handling out of sync, "
                        + "unable to retrieve failure message for element {}\n\n\n\n\n".format(task.full_name),
                        err=True,
                    )
                else:
                    self._handle_failure(element, task, failure)

            else:
                # Not an element_job, we don't handle the failure
                click.echo("\nTerminating all jobs\n", err=True)
                self.stream.terminate()

    def _handle_failure(self, element, task, failure):
        full_name = task.full_name

        # Handle non interactive mode setting of what to do when a job fails.
        if not self._interactive_failures:

            if self.context.sched_error_action == _SchedulerErrorAction.TERMINATE:
                self.stream.terminate()
            elif self.context.sched_error_action == _SchedulerErrorAction.QUIT:
                self.stream.quit()
            elif self.context.sched_error_action == _SchedulerErrorAction.CONTINUE:
                pass
            return

        # Interactive mode for element failures
        with self._interrupted():

            summary = (
                "\n{} failure on element: {}\n".format(failure.action_name, full_name)
                + "\n"
                + "Choose one of the following options:\n"
                + "  (c)ontinue  - Continue queueing jobs as much as possible\n"
                + "  (q)uit      - Exit after all ongoing jobs complete\n"
                + "  (t)erminate - Terminate any ongoing jobs and exit\n"
                + "  (r)etry     - Retry this job\n"
            )
            if failure.logfile:
                summary += "  (l)og       - View the full log file\n"
            if failure.sandbox:
                summary += "  (s)hell     - Drop into a shell in the failed build sandbox\n"
            summary += "\nPressing ^C will terminate jobs and exit\n"

            choices = ["continue", "quit", "terminate", "retry"]
            if failure.logfile:
                choices += ["log"]
            if failure.sandbox:
                choices += ["shell"]

            choice = ""
            while choice not in ["continue", "quit", "terminate", "retry"]:
                click.echo(summary, err=True)

                self._notify("BuildStream failure", "{} on element {}".format(failure.action_name, full_name))

                try:
                    choice = click.prompt(
                        "Choice:", default="continue", err=True, value_proc=_prefix_choice_value_proc(choices)
                    )
                except (click.Abort, SystemError):
                    # In some cases, the readline buffer underlying the prompt gets corrupted on the second CTRL+C
                    # This throws a SystemError, which doesn't seem to be problematic for the rest of the program

                    # Ensure a newline after automatically printed '^C'
                    click.echo("", err=True)
                    choice = "terminate"

                # Handle choices which you can come back from
                #
                if choice == "shell":
                    click.echo("\nDropping into an interactive shell in the failed build sandbox\n", err=True)
                    try:
                        unique_id, _ = element
                        self.stream.shell(
                            None,
                            _Scope.BUILD,
                            self.shell_prompt,
                            isolate=True,
                            usebuildtree=True,
                            unique_id=unique_id,
                        )
                    except BstError as e:
                        click.echo("Error while attempting to create interactive shell: {}".format(e), err=True)
                elif choice == "log":
                    with open(failure.logfile, "r", encoding="utf-8") as logfile:
                        content = logfile.read()
                        click.echo_via_pager(content)

            if choice == "terminate":
                click.echo("\nTerminating all jobs\n", err=True)
                self.stream.terminate()
            else:
                if choice == "quit":
                    click.echo("\nCompleting ongoing tasks before quitting\n", err=True)
                    self.stream.quit()
                elif choice == "continue":
                    click.echo("\nContinuing with other non failing elements\n", err=True)
                elif choice == "retry":
                    click.echo("\nRetrying failed job\n", err=True)
                    unique_id = element[0]
                    self.stream.retry_job(task.action_name, unique_id)

    #
    # Print the session heading if we've loaded a pipeline and there
    # is going to be a session
    #
    def session_start_cb(self):
        self._started = True
        if self._session_name:
            self.logger.print_heading(self.project, self.stream, log_file=self._main_options["log_file"])

    #
    # Print a summary of the queues
    #
    def _print_summary(self):
        # Ensure all status & messages have been processed
        self._render_cached_messages()
        click.echo("", err=True)

        try:
            self.logger.print_summary(self.stream, self._main_options["log_file"])
        except BstError as e:
            self._error_exit(e)

    # _error_exit()
    #
    # Exit with an error
    #
    # This will print the passed error to stderr and exit the program
    # with -1 status
    #
    # Args:
    #   error (BstError): A BstError exception to print
    #   prefix (str): An optional string to prepend to the error message
    #
    def _error_exit(self, error, prefix=None):
        click.echo("", err=True)

        if self.context is None or self.context.log_debug is None:  # Context might not be initialized, default to cmd
            debug = self._main_options["debug"]
        else:
            debug = self.context.log_debug

        if debug:
            main_error = "\n\n" + traceback.format_exc()
        else:
            main_error = str(error)

        if prefix is not None:
            main_error = "{}: {}".format(prefix, main_error)

        click.echo(main_error, err=True)
        if error.detail:
            indent = " " * INDENT
            detail = "\n" + indent + indent.join(error.detail.splitlines(True))
            click.echo(detail, err=True)

        sys.exit(-1)

    #
    # Handle messages from the pipeline
    #
    def _message_handler(self, message, is_silenced):

        # Drop status messages from the UI if not verbose, we'll still see
        # info messages and status messages will still go to the log files.
        if not self.context.log_verbose and message.message_type == MessageType.STATUS:
            return

        # Hold on to the failure messages
        if message.message_type in [MessageType.FAIL, MessageType.BUG] and message.element_name is not None:
            self._fail_messages[message.element_name] = message

        # Send to frontend if appropriate
        if is_silenced and (message.message_type not in unconditional_messages):
            return

        # Cache the message
        text = self._cache_message(message)

        # If we're not rate limiting messaging, or the scheduler tick isn't active then render
        if not self._cache_messages or not self.stream.running:
            self._render_cached_messages()

        # Additionally log to a file
        if self._main_options["log_file"]:
            click.echo(text, file=self._main_options["log_file"], color=False, nl=False)

    @contextmanager
    def _interrupted(self):
        self._status.clear()
        try:
            with self.stream.suspend():
                yield
        finally:
            self._render_cached_messages()

    # Some validation routines for project initialization
    #
    def _assert_min_version(self, min_version):
        bst_major, bst_minor = utils._get_bst_api_version()
        message = "The minimum version must be a known version of BuildStream {}".format(bst_major)

        # Validate the version format
        try:
            min_version_major, min_version_minor = utils._parse_version(min_version)
        except UtilError as e:
            raise AppError(str(e), reason="invalid-min-version") from e

        # Validate that this version can be loaded by the installed version of BuildStream
        if min_version_major != bst_major or min_version_minor > bst_minor:
            raise AppError(message, reason="invalid-min-version")

    def _assert_element_path(self, element_path):
        message = "The element path cannot be an absolute path or contain any '..' components\n"

        # Validate the path is not absolute
        if os.path.isabs(element_path):
            raise AppError(message, reason="invalid-element-path")

        # Validate that the path does not contain any '..' components
        path = element_path
        while path:
            split = os.path.split(path)
            path = split[0]
            basename = split[1]
            if basename == "..":
                raise AppError(message, reason="invalid-element-path")

    # _init_project_interactive()
    #
    # Collect the user input for an interactive session for App.init_project()
    #
    # Args:
    #    project_name (str): The project name, must be a valid symbol name
    #    min_version (str): The minimum BuildStream version, default is the latest version
    #    element_path (str): The subdirectory to store elements in, default is 'elements'
    #
    # Returns:
    #    project_name (str): The user selected project name
    #    min_version (int): The user selected minimum BuildStream version
    #    element_path (str): The user selected element path
    #
    def _init_project_interactive(self, project_name, min_version=None, element_path="elements"):

        bst_major, bst_minor = utils._get_bst_api_version()

        if min_version is None:
            min_version = "{}.{}".format(bst_major, bst_minor)

        def project_name_proc(user_input):
            try:
                node._assert_symbol_name(user_input, "project name")
            except LoadError as e:
                message = "{}\n\n{}\n".format(e, e.detail)
                raise UsageError(message) from e
            return user_input

        def min_version_proc(user_input):
            try:
                self._assert_min_version(user_input)
            except AppError as e:
                raise UsageError(str(e)) from e
            return user_input

        def element_path_proc(user_input):
            try:
                self._assert_element_path(user_input)
            except AppError as e:
                raise UsageError(str(e)) from e
            return user_input

        w = TextWrapper(initial_indent="  ", subsequent_indent="  ", width=79)

        # Collect project name
        click.echo("", err=True)
        click.echo(self._content_profile.fmt("Choose a unique name for your project"), err=True)
        click.echo(self._format_profile.fmt("-------------------------------------"), err=True)
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "The project name is a unique symbol for your project and will be used "
                    "to distinguish your project from others in user preferences, namespacing "
                    "of your project's artifacts in shared artifact caches, and in any case where "
                    "BuildStream needs to distinguish between multiple projects."
                )
            ),
            err=True,
        )
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "The project name must contain only alphanumeric characters, "
                    "may not start with a digit, and may contain dashes or underscores."
                )
            ),
            err=True,
        )
        click.echo("", err=True)
        project_name = click.prompt(self._content_profile.fmt("Project name"), value_proc=project_name_proc, err=True)
        click.echo("", err=True)

        # Collect minimum BuildStream version
        click.echo(
            self._content_profile.fmt("Select the minimum required BuildStream version for your project"), err=True
        )
        click.echo(
            self._format_profile.fmt("----------------------------------------------------------------"), err=True
        )
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "The minimum version is used to provide users who build your project "
                    "with a helpful error message in the case that they do not have a recent "
                    "enough version of BuildStream to support all the features which your "
                    "project uses."
                )
            ),
            err=True,
        )
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "The lowest version allowed is {major}.0, the currently installed version of BuildStream is {major}.{minor}".format(
                        major=bst_major, minor=bst_minor
                    )
                )
            ),
            err=True,
        )

        click.echo("", err=True)
        min_version = click.prompt(
            self._content_profile.fmt("Minimum version"),
            value_proc=min_version_proc,
            default=min_version,
            err=True,
        )
        click.echo("", err=True)

        # Collect element path
        click.echo(self._content_profile.fmt("Select the element path"), err=True)
        click.echo(self._format_profile.fmt("-----------------------"), err=True)
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "The element path is a project subdirectory where element .bst files are stored "
                    "within your project."
                )
            ),
            err=True,
        )
        click.echo("", err=True)
        click.echo(
            self._detail_profile.fmt(
                w.fill(
                    "Elements will be displayed in logs as filenames relative to "
                    "the element path, and similarly, dependencies must be expressed as filenames "
                    "relative to the element path."
                )
            ),
            err=True,
        )
        click.echo("", err=True)
        element_path = click.prompt(
            self._content_profile.fmt("Element path"), value_proc=element_path_proc, default=element_path, err=True
        )

        return (project_name, min_version, element_path)


#
# Return a value processor for partial choice matching.
# The returned values processor will test the passed value with all the item
# in the 'choices' list. If the value is a prefix of one of the 'choices'
# element, the element is returned. If no element or several elements match
# the same input, a 'click.UsageError' exception is raised with a description
# of the error.
#
# Note that Click expect user input errors to be signaled by raising a
# 'click.UsageError' exception. That way, Click display an error message and
# ask for a new input.
#
def _prefix_choice_value_proc(choices):
    def value_proc(user_input):
        remaining_candidate = [choice for choice in choices if choice.startswith(user_input)]

        if not remaining_candidate:
            raise UsageError("Expected one of {}, got {}".format(choices, user_input))

        if len(remaining_candidate) == 1:
            return remaining_candidate[0]
        else:
            raise UsageError("Ambiguous input. '{}' can refer to one of {}".format(user_input, remaining_candidate))

    return value_proc
