#!/usr/bin/env python3
#
#  Copyright (C) 2016-2018 Codethink Limited
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
import sys
import shutil
import resource
import datetime
from textwrap import TextWrapper
from contextlib import contextmanager
from blessings import Terminal

import click
from click import UsageError

# Import buildstream public symbols
from .. import Scope, Consistency

# Import various buildstream internals
from .._context import Context
from .._project import Project
from .._exceptions import BstError, PipelineError, LoadError, LoadErrorReason, AppError
from .._message import Message, MessageType, unconditional_messages
from .._pipeline import Pipeline
from .._scheduler import Scheduler
from .._profile import Topics, profile_start, profile_end
from .._versions import BST_FORMAT_VERSION
from .. import __version__ as build_stream_version
from .. import _yaml

# Import frontend assets
from . import Profile, LogLine, Status

# Intendation for all logging
INDENT = 4


##################################################################
#                    Main Application State                      #
##################################################################
class App():

    def __init__(self, main_options):

        # Snapshot the start time of the session at the earliest opportunity,
        # this is used for inclusive session time logging
        self.session_start = datetime.datetime.now()

        self.main_options = main_options
        self.logger = None
        self.status = None
        self.target = None

        # Main asset handles
        self.context = None
        self.project = None
        self.scheduler = None
        self.pipeline = None

        # Failure messages, hashed by unique plugin id
        self.fail_messages = {}

        # UI Colors Profiles
        self.content_profile = Profile(fg='yellow')
        self.format_profile = Profile(fg='cyan', dim=True)
        self.success_profile = Profile(fg='green')
        self.error_profile = Profile(fg='red', dim=True)
        self.detail_profile = Profile(dim=True)

        # Check if we are connected to a tty
        self.is_a_tty = Terminal().is_a_tty

        # Figure out interactive mode
        if self.main_options['no_interactive']:
            self.interactive = False
        else:
            self.interactive = self.is_a_tty

        # Whether we handle failures interactively
        # defaults to whether we are interactive or not.
        self.interactive_failures = self.interactive

        # Resolve whether to use colors in output
        if self.main_options['colors'] is None:
            self.colors = self.is_a_tty
        elif self.main_options['colors']:
            self.colors = True
        else:
            self.colors = False

        # Increase the soft limit for open file descriptors to the maximum.
        # SafeHardlinks FUSE needs to hold file descriptors for all processes in the sandbox.
        # Avoid hitting the limit too quickly.
        limits = resource.getrlimit(resource.RLIMIT_NOFILE)
        if limits[0] != limits[1]:
            # Set soft limit to hard limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (limits[1], limits[1]))

    # partially_initialized()
    #
    # Early stage initialization context manager which only initializes the
    # Context, Project and the logger.
    #
    # partial initialization is useful for some contexts where we dont
    # want to load the pipeline, such as executing workspace commands.
    #
    # Args:
    #    fetch_subprojects (bool): Whether we should fetch subprojects as a part of the
    #                              loading process, if they are not yet locally cached
    #
    @contextmanager
    def partially_initialized(self, *, fetch_subprojects=False):
        directory = self.main_options['directory']
        config = self.main_options['config']

        try:
            self.context = Context(fetch_subprojects=fetch_subprojects)
            self.context.load(config)
        except BstError as e:
            self.print_error(e, "Error loading user configuration")
            sys.exit(-1)

        # Override things in the context from our command line options,
        # the command line when used, trumps the config files.
        #
        override_map = {
            'strict': '_strict_build_plan',
            'debug': 'log_debug',
            'verbose': 'log_verbose',
            'error_lines': 'log_error_lines',
            'message_lines': 'log_message_lines',
            'on_error': 'sched_error_action',
            'fetchers': 'sched_fetchers',
            'builders': 'sched_builders',
            'pushers': 'sched_pushers',
            'network_retries': 'sched_network_retries'
        }
        for cli_option, context_attr in override_map.items():
            option_value = self.main_options.get(cli_option)
            if option_value is not None:
                setattr(self.context, context_attr, option_value)

        # Disable interactive failures if --on-error was specified
        # on the command line, but not if it was only specified
        # in the config.
        if self.main_options.get('on_error') is not None:
            self.interactive_failures = False

        # Create the logger right before setting the message handler
        self.logger = LogLine(
            self.content_profile,
            self.format_profile,
            self.success_profile,
            self.error_profile,
            self.detail_profile,
            # Indentation for detailed messages
            indent=INDENT,
            # Number of last lines in an element's log to print (when encountering errors)
            log_lines=self.context.log_error_lines,
            # Maximum number of lines to print in a detailed message
            message_lines=self.context.log_message_lines,
            # Whether to print additional debugging information
            debug=self.context.log_debug,
            message_format=self.context.log_message_format)

        # Propagate pipeline feedback to the user
        self.context.set_message_handler(self.message_handler)

        try:
            self.project = Project(directory, self.context, cli_options=self.main_options['option'])
        except LoadError as e:

            # Let's automatically start a `bst init` session in this case
            if e.reason == LoadErrorReason.MISSING_PROJECT_CONF and self.interactive:
                click.echo("A project was not detected in the directory: {}".format(directory), err=True)
                click.echo("", err=True)
                if click.confirm("Would you like to create a new project here ?"):
                    self.init_project(None)

            self.print_error(e, "Error loading project")
            sys.exit(-1)

        except BstError as e:
            self.print_error(e, "Error loading project")
            sys.exit(-1)

        # Run the body of the session here, once everything is loaded
        try:
            yield
        except BstError as e:
            self.print_error(e)
            sys.exit(-1)

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
    #    elements (list of elements): The elements to load recursively
    #    session_name (str): The name of the session, or None for no session
    #    except_ (list of elements): The elements to except
    #    rewritable (bool): Whether we should load the YAML files for roundtripping
    #    use_configured_remote_caches (bool): Whether we should contact remotes
    #    add_remote_cache (str): The URL for an explicitly mentioned remote cache
    #    track_elements (list of elements): Elements which are to be tracked
    #    fetch_subprojects (bool): Whether we should fetch subprojects as a part of the
    #                              loading process, if they are not yet locally cached
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
    def initialized(self, elements, *, session_name=None,
                    except_=tuple(), rewritable=False,
                    use_configured_remote_caches=False, add_remote_cache=None,
                    track_elements=None, fetch_subprojects=False):
        profile_start(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

        # Start with the early stage init, this enables logging right away
        with self.partially_initialized(fetch_subprojects=fetch_subprojects):

            # Mark the beginning of the session
            if session_name:
                self.message(MessageType.START, session_name)

            # Create the application's scheduler
            self.scheduler = Scheduler(self.context, self.session_start,
                                       interrupt_callback=self.interrupt_handler,
                                       ticker_callback=self.tick,
                                       job_start_callback=self.job_started,
                                       job_complete_callback=self.job_completed)

            try:
                self.pipeline = Pipeline(self.context, self.project, elements, except_,
                                         rewritable=rewritable)
            except BstError as e:
                self.print_error(e, "Error loading pipeline")
                sys.exit(-1)

            # Create our status printer, only available in interactive
            self.status = Status(self.content_profile, self.format_profile,
                                 self.success_profile, self.error_profile,
                                 self.pipeline, self.scheduler,
                                 colors=self.colors)

            # Initialize pipeline
            try:
                self.pipeline.initialize(use_configured_remote_caches=use_configured_remote_caches,
                                         add_remote_cache=add_remote_cache,
                                         track_elements=track_elements)
            except BstError as e:
                self.print_error(e, "Error initializing pipeline")
                sys.exit(-1)

            # Pipeline is loaded, now we can tell the logger about it
            self.logger.size_request(self.pipeline)

            profile_end(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

            # Print the heading
            if session_name:
                self.print_heading()

            # Run the body of the session here, once everything is loaded
            try:
                yield
            except BstError as e:

                # Catch the error and summarize what happened
                elapsed = self.scheduler.elapsed_time()

                if session_name:
                    if isinstance(e, PipelineError) and e.terminated:  # pylint: disable=no-member
                        self.message(MessageType.WARN, session_name + ' Terminated', elapsed=elapsed)
                    else:
                        self.message(MessageType.FAIL, session_name, elapsed=elapsed)

                if session_name:
                    self.print_summary()

                # Let the outer context manager print the error and exit
                raise
            else:
                # No exceptions occurred, print session time and summary
                if session_name:
                    self.message(MessageType.SUCCESS, session_name, elapsed=self.scheduler.elapsed_time())
                    self.print_summary()

    # init_project()
    #
    # Initialize a new BuildStream project, either with the explicitly passed options,
    # or by starting an interactive session if project_name is not specified and the
    # application is running in interactive mode.
    #
    # Args:
    #    project_name (str): The project name, must be a valid symbol name
    #    format_version (int): The project format version, default is the latest version
    #    element_directory (str): The subdirectory to store elements in, default is 'elements'
    #    force (bool): Allow overwriting an existing project.conf
    #
    def init_project(self, project_name, format_version=BST_FORMAT_VERSION, element_path='elements', force=False):
        directory = self.main_options['directory']
        directory = os.path.abspath(directory)
        project_path = os.path.join(directory, 'project.conf')

        try:
            # Abort if the project.conf already exists, unless `--force` was specified in `bst init`
            if not force and os.path.exists(project_path):
                raise AppError("A project.conf already exists at: {}".format(project_path),
                               reason='project-exists')

            if project_name:
                # If project name was specified, user interaction is not desired, just
                # perform some validation and write the project.conf
                _yaml.assert_symbol_name(None, project_name, 'project name')
                self.assert_format_version(format_version)
                self.assert_element_path(element_path)

            elif not self.interactive:
                raise AppError("Cannot initialize a new project without specifying the project name",
                               reason='unspecified-project-name')
            else:
                # Collect the parameters using an interactive session
                project_name, format_version, element_path = \
                    self.init_project_interactive(project_name, format_version, element_path)

        except BstError as e:
            self.print_error(e)
            sys.exit(-1)

        # Create the directory if it doesnt exist
        os.makedirs(directory, exist_ok=True)

        # Dont use ruamel.yaml here, because it doesnt let
        # us programatically insert comments or whitespace at
        # the toplevel.
        #
        try:
            with open(project_path, 'w') as f:
                f.write("# Unique project name\n" +
                        "name: {}\n\n".format(project_name) +
                        "# Required BuildStream format version\n" +
                        "format-version: {}\n\n".format(format_version) +
                        "# Subdirectory where elements are stored\n" +
                        "element-path: {}\n".format(element_path))
        except IOError as e:
            click.echo("", err=True)
            click.echo("Error writing {}: {}".format(project_path, e), err=True)
            sys.exit(-1)

        click.echo("", err=True)
        click.echo("Created project.conf at: {}".format(project_path), err=True)
        sys.exit(0)

    ############################################################
    #                   Workspace Commands                     #
    ############################################################

    # open_workspace
    #
    # Open a project workspace - this requires full initialization
    #
    # Args:
    #    directory (str): The directory to stage the source in
    #    no_checkout (bool): Whether to skip checking out the source
    #    track_first (bool): Whether to track and fetch first
    #    force (bool): Whether to ignore contents in an existing directory
    #
    def open_workspace(self, directory, no_checkout, track_first, force):

        # When working on workspaces we only have one target
        target = self.pipeline.targets[0]
        workdir = os.path.abspath(directory)

        if not list(target.sources()):
            build_depends = [x.name for x in target.dependencies(Scope.BUILD, recurse=False)]
            if not build_depends:
                raise AppError("The given element has no sources")
            detail = "Try opening a workspace on one of its dependencies instead:\n"
            detail += "  \n".join(build_depends)
            raise AppError("The given element has no sources", detail=detail)

        # Check for workspace config
        if self.project.workspaces.get_workspace(target):
            raise AppError("Workspace '{}' is already defined.".format(target.name))

        # If we're going to checkout, we need at least a fetch,
        # if we were asked to track first, we're going to fetch anyway.
        if not no_checkout or track_first:
            self.pipeline.fetch(self.scheduler, [target], track_first=track_first)

        if not no_checkout and target._get_consistency() != Consistency.CACHED:
            raise PipelineError("Could not stage uncached source. " +
                                "Use `--track` to track and " +
                                "fetch the latest version of the " +
                                "source.")

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise AppError("Failed to create workspace directory: {}".format(e)) from e

        workspace = self.project.workspaces.create_workspace(target.name, workdir)

        if not no_checkout:
            if not force and os.listdir(directory):
                raise AppError("Checkout directory is not empty: {}".format(directory))

            with target.timed_activity("Staging sources to {}".format(directory)):
                target._open_workspace()

        self.project.workspaces.save_config()
        self.message(MessageType.INFO, "Saved workspace configuration")

    # close_workspace
    #
    # Close a project workspace - this requires only partial initialization
    #
    # Args:
    #    element_name (str): The element name to close the workspace for
    #    remove_dir (bool): Whether to remove the associated directory
    #
    def close_workspace(self, element_name, remove_dir):

        workspace = self.project.workspaces.get_workspace(element_name)

        if workspace is None:
            raise AppError("Workspace '{}' does not exist".format(element_name))

        # Remove workspace directory if prompted
        if remove_dir:
            with self.context.timed_activity("Removing workspace directory {}"
                                             .format(workspace.path)):
                try:
                    shutil.rmtree(workspace.path)
                except OSError as e:
                    raise AppError("Could not remove  '{}': {}"
                                   .format(workspace.path, e)) from e

        # Delete the workspace and save the configuration
        self.project.workspaces.delete_workspace(element_name)
        self.project.workspaces.save_config()
        self.message(MessageType.INFO, "Saved workspace configuration")

    # reset_workspace
    #
    # Reset a workspace to its original state, discarding any user
    # changes.
    #
    # Args:
    #    track (bool): Whether to also track the source
    #
    def reset_workspace(self, track):
        # When working on workspaces we only have one target
        target = self.pipeline.targets[0]
        workspace = self.project.workspaces.get_workspace(target.name)

        if workspace is None:
            raise AppError("Workspace '{}' is currently not defined"
                           .format(target.name))

        self.close_workspace(target.name, True)
        self.open_workspace(workspace.path, False, track, False)

    ############################################################
    #                      Local Functions                     #
    ############################################################

    # Local message propagator
    #
    def message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context.message(
            Message(None, message_type, message, **args))

    #
    # Render the status area, conditional on some internal state
    #
    def maybe_render_status(self):

        # If we're suspended or terminating, then dont render the status area
        if self.status and self.scheduler and \
           not (self.scheduler.suspended or self.scheduler.terminated):
            self.status.render()

    #
    # Handle ^C SIGINT interruptions in the scheduling main loop
    #
    def interrupt_handler(self):

        # Only handle ^C interactively in interactive mode
        if not self.interactive:
            self.status.clear()
            self.scheduler.terminate_jobs()
            return

        # Here we can give the user some choices, like whether they would
        # like to continue, abort immediately, or only complete processing of
        # the currently ongoing tasks. We can also print something more
        # intelligent, like how many tasks remain to complete overall.
        with self.interrupted():
            click.echo("\nUser interrupted with ^C\n" +
                       "\n"
                       "Choose one of the following options:\n" +
                       "  (c)ontinue  - Continue queueing jobs as much as possible\n" +
                       "  (q)uit      - Exit after all ongoing jobs complete\n" +
                       "  (t)erminate - Terminate any ongoing jobs and exit\n" +
                       "\n" +
                       "Pressing ^C again will terminate jobs and exit\n",
                       err=True)

            try:
                choice = click.prompt("Choice:",
                                      value_proc=prefix_choice_value_proc(['continue', 'quit', 'terminate']),
                                      default='continue', err=True)
            except click.Abort:
                # Ensure a newline after automatically printed '^C'
                click.echo("", err=True)
                choice = 'terminate'

            if choice == 'terminate':
                click.echo("\nTerminating all jobs at user request\n", err=True)
                self.scheduler.terminate_jobs()
            else:
                if choice == 'quit':
                    click.echo("\nCompleting ongoing tasks before quitting\n", err=True)
                    self.scheduler.stop_queueing()
                elif choice == 'continue':
                    click.echo("\nContinuing\n", err=True)

    def job_started(self, element, action_name):
        self.status.add_job(element, action_name)
        self.maybe_render_status()

    def job_completed(self, element, queue, action_name, success):
        self.status.remove_job(element, action_name)
        self.maybe_render_status()

        # Dont attempt to handle a failure if the user has already opted to
        # terminate
        if not success and not self.scheduler.terminated:

            # Get the last failure message for additional context
            failure = self.fail_messages.get(element._get_unique_id())

            # XXX This is dangerous, sometimes we get the job completed *before*
            # the failure message reaches us ??
            if not failure:
                self.status.clear()
                click.echo("\n\n\nBUG: Message handling out of sync, " +
                           "unable to retrieve failure message for element {}\n\n\n\n\n"
                           .format(element), err=True)
            else:
                self.handle_failure(element, queue, failure)

    def handle_failure(self, element, queue, failure):

        # Handle non interactive mode setting of what to do when a job fails.
        if not self.interactive_failures:

            if self.context.sched_error_action == 'terminate':
                self.scheduler.terminate_jobs()
            elif self.context.sched_error_action == 'quit':
                self.scheduler.stop_queueing()
            elif self.context.sched_error_action == 'continue':
                pass
            return

        # Interactive mode for element failures
        with self.interrupted():

            summary = ("\n{} failure on element: {}\n".format(failure.action_name, element.name) +
                       "\n" +
                       "Choose one of the following options:\n" +
                       "  (c)ontinue  - Continue queueing jobs as much as possible\n" +
                       "  (q)uit      - Exit after all ongoing jobs complete\n" +
                       "  (t)erminate - Terminate any ongoing jobs and exit\n" +
                       "  (r)etry     - Retry this job\n")
            if failure.logfile:
                summary += "  (l)og       - View the full log file\n"
            if failure.sandbox:
                summary += "  (s)hell     - Drop into a shell in the failed build sandbox\n"
            summary += "\nPressing ^C will terminate jobs and exit\n"

            choices = ['continue', 'quit', 'terminate', 'retry']
            if failure.logfile:
                choices += ['log']
            if failure.sandbox:
                choices += ['shell']

            choice = ''
            while choice not in ['continue', 'quit', 'terminate', 'retry']:
                click.echo(summary, err=True)

                try:
                    choice = click.prompt("Choice:", default='continue', err=True,
                                          value_proc=prefix_choice_value_proc(choices))
                except click.Abort:
                    # Ensure a newline after automatically printed '^C'
                    click.echo("", err=True)
                    choice = 'terminate'

                # Handle choices which you can come back from
                #
                if choice == 'shell':
                    click.echo("\nDropping into an interactive shell in the failed build sandbox\n", err=True)
                    try:
                        self.shell(element, Scope.BUILD, failure.sandbox, isolate=True)
                    except BstError as e:
                        click.echo("Error while attempting to create interactive shell: {}".format(e), err=True)
                elif choice == 'log':
                    with open(failure.logfile, 'r') as logfile:
                        content = logfile.read()
                        click.echo_via_pager(content)

            if choice == 'terminate':
                click.echo("\nTerminating all jobs\n", err=True)
                self.scheduler.terminate_jobs()
            else:
                if choice == 'quit':
                    click.echo("\nCompleting ongoing tasks before quitting\n", err=True)
                    self.scheduler.stop_queueing()
                elif choice == 'continue':
                    click.echo("\nContinuing with other non failing elements\n", err=True)
                elif choice == 'retry':
                    click.echo("\nRetrying failed job\n", err=True)
                    queue.failed_elements.remove(element)
                    queue.enqueue([element])

    def shell(self, element, scope, directory, *, mounts=None, isolate=False, command=None):
        _, key, dim = element._get_full_display_key()
        element_name = element._get_full_name()

        if self.colors:
            prompt = self.format_profile.fmt('[') + \
                self.content_profile.fmt(key, dim=dim) + \
                self.format_profile.fmt('@') + \
                self.content_profile.fmt(element_name) + \
                self.format_profile.fmt(':') + \
                self.content_profile.fmt('$PWD') + \
                self.format_profile.fmt(']$') + ' '
        else:
            prompt = '[{}@{}:${{PWD}}]$ '.format(key, element_name)

        return element._shell(scope, directory, mounts=mounts, isolate=isolate, prompt=prompt, command=command)

    def tick(self, elapsed):
        self.maybe_render_status()

    #
    # Prints the application startup heading, used for commands which
    # will process a pipeline.
    #
    def print_heading(self, deps=None):
        self.logger.print_heading(self.pipeline,
                                  self.main_options['log_file'],
                                  styling=self.colors,
                                  deps=deps)

    #
    # Print a summary of the queues
    #
    def print_summary(self):
        click.echo("", err=True)
        self.logger.print_summary(self.pipeline, self.scheduler,
                                  self.main_options['log_file'],
                                  styling=self.colors)

    #
    # Print an error
    #
    def print_error(self, error, prefix=None):
        click.echo("", err=True)
        main_error = "{}".format(error)
        if prefix is not None:
            main_error = "{}: {}".format(prefix, main_error)

        click.echo(main_error, err=True)
        if error.detail:
            indent = " " * INDENT
            detail = '\n' + indent + indent.join(error.detail.splitlines(True))
            click.echo("{}".format(detail), err=True)

    #
    # Handle messages from the pipeline
    #
    def message_handler(self, message, context):

        # Drop status messages from the UI if not verbose, we'll still see
        # info messages and status messages will still go to the log files.
        if not context.log_verbose and message.message_type == MessageType.STATUS:
            return

        # Hold on to the failure messages
        if message.message_type in [MessageType.FAIL, MessageType.BUG] and message.unique_id is not None:
            self.fail_messages[message.unique_id] = message

        # Send to frontend if appropriate
        if self.context.silent_messages() and (message.message_type not in unconditional_messages):
            return

        if self.status:
            self.status.clear()

        text = self.logger.render(message)
        click.echo(text, color=self.colors, nl=False, err=True)

        # Maybe render the status area
        self.maybe_render_status()

        # Additionally log to a file
        if self.main_options['log_file']:
            click.echo(text, file=self.main_options['log_file'], color=False, nl=False)

    @contextmanager
    def interrupted(self):
        self.scheduler.disconnect_signals()

        self.status.clear()
        self.scheduler.suspend_jobs()

        yield

        self.maybe_render_status()
        self.scheduler.resume_jobs()
        self.scheduler.connect_signals()

    def cleanup(self):
        if self.pipeline:
            self.pipeline.cleanup()

    # Some validation routines for project initialization
    #
    def assert_format_version(self, format_version):
        message = "The version must be supported by this " + \
                  "version of buildstream (0 - {})\n".format(BST_FORMAT_VERSION)

        # Validate that it is an integer
        try:
            number = int(format_version)
        except ValueError as e:
            raise AppError(message, reason='invalid-format-version') from e

        # Validate that the specified version is supported
        if number < 0 or number > BST_FORMAT_VERSION:
            raise AppError(message, reason='invalid-format-version')

    def assert_element_path(self, element_path):
        message = "The element path cannot be an absolute path or contain any '..' components\n"

        # Validate the path is not absolute
        if os.path.isabs(element_path):
            raise AppError(message, reason='invalid-element-path')

        # Validate that the path does not contain any '..' components
        path = element_path
        while path:
            split = os.path.split(path)
            path = split[0]
            basename = split[1]
            if basename == '..':
                raise AppError(message, reason='invalid-element-path')

    # init_project_interactive()
    #
    # Collect the user input for an interactive session for App.init_project()
    #
    # Args:
    #    project_name (str): The project name, must be a valid symbol name
    #    format_version (int): The project format version, default is the latest version
    #    element_path (str): The subdirectory to store elements in, default is 'elements'
    #
    # Returns:
    #    project_name (str): The user selected project name
    #    format_version (int): The user selected format version
    #    element_path (str): The user selected element path
    #
    def init_project_interactive(self, project_name, format_version=BST_FORMAT_VERSION, element_path='elements'):

        def project_name_proc(user_input):
            try:
                _yaml.assert_symbol_name(None, user_input, 'project name')
            except LoadError as e:
                message = "{}\n\n{}\n".format(e, e.detail)
                raise UsageError(message) from e
            return user_input

        def format_version_proc(user_input):
            try:
                self.assert_format_version(user_input)
            except AppError as e:
                raise UsageError(str(e)) from e
            return user_input

        def element_path_proc(user_input):
            try:
                self.assert_element_path(user_input)
            except AppError as e:
                raise UsageError(str(e)) from e
            return user_input

        w = TextWrapper(initial_indent='  ', subsequent_indent='  ', width=79)

        # Collect project name
        click.echo("", err=True)
        click.echo(self.content_profile.fmt("Choose a unique name for your project"), err=True)
        click.echo(self.format_profile.fmt("-------------------------------------"), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("The project name is a unique symbol for your project and will be used "
                   "to distinguish your project from others in user preferences, namspaceing "
                   "of your project's artifacts in shared artifact caches, and in any case where "
                   "BuildStream needs to distinguish between multiple projects.")), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("The project name must contain only alphanumeric characters, "
                   "may not start with a digit, and may contain dashes or underscores.")), err=True)
        click.echo("", err=True)
        project_name = click.prompt(self.content_profile.fmt("Project name"),
                                    value_proc=project_name_proc, err=True)
        click.echo("", err=True)

        # Collect format version
        click.echo(self.content_profile.fmt("Select the minimum required format version for your project"), err=True)
        click.echo(self.format_profile.fmt("-----------------------------------------------------------"), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("The format version is used to provide users who build your project "
                   "with a helpful error message in the case that they do not have a recent "
                   "enough version of BuildStream supporting all the features which your "
                   "project might use.")), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("The lowest version allowed is 0, the currently installed version of BuildStream "
                   "supports up to format version {}.".format(BST_FORMAT_VERSION))), err=True)

        click.echo("", err=True)
        format_version = click.prompt(self.content_profile.fmt("Format version"),
                                      value_proc=format_version_proc,
                                      default=format_version, err=True)
        click.echo("", err=True)

        # Collect element path
        click.echo(self.content_profile.fmt("Select the element path"), err=True)
        click.echo(self.format_profile.fmt("-----------------------"), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("The element path is a project subdirectory where element .bst files are stored "
                   "within your project.")), err=True)
        click.echo("", err=True)
        click.echo(self.detail_profile.fmt(
            w.fill("Elements will be displayed in logs as filenames relative to "
                   "the element path, and similarly, dependencies must be expressed as filenames "
                   "relative to the element path.")), err=True)
        click.echo("", err=True)
        element_path = click.prompt(self.content_profile.fmt("Element path"),
                                    value_proc=element_path_proc,
                                    default=element_path, err=True)

        return (project_name, format_version, element_path)


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
def prefix_choice_value_proc(choices):

    def value_proc(user_input):
        remaining_candidate = [choice for choice in choices if choice.startswith(user_input)]

        if not remaining_candidate:
            raise UsageError("Expected one of {}, got {}".format(choices, user_input))
        elif len(remaining_candidate) == 1:
            return remaining_candidate[0]
        else:
            raise UsageError("Ambiguous input. '{}' can refer to one of {}".format(user_input, remaining_candidate))

    return value_proc
