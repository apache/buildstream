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
import resource
from contextlib import contextmanager
from blessings import Terminal

import click
from click import UsageError

from .cli import cli

# Import buildstream public symbols
from .. import Scope

# Import various buildstream internals
from .._context import Context
from .._project import Project
from .._exceptions import BstError, LoadError
from .._message import MessageType, unconditional_messages
from .._pipeline import Pipeline, PipelineError
from .._scheduler import Scheduler
from .._profile import Topics, profile_start, profile_end
from .. import _yaml
from .. import __version__ as build_stream_version

# Import frontend assets
from . import Profile, LogLine, Status
from .complete import main_bashcomplete, complete_path, CompleteUnhandled

# Intendation for all logging
INDENT = 4


##################################################################
#                    Main Application State                      #
##################################################################

class App():

    def __init__(self, main_options):
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

    #
    # Initialize the main pipeline
    #
    def initialize(self, elements, except_=tuple(), rewritable=False,
                   use_configured_remote_caches=False, add_remote_cache=None,
                   track_elements=None, fetch_subprojects=False):

        profile_start(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

        directory = self.main_options['directory']
        config = self.main_options['config']

        try:
            self.context = Context(fetch_subprojects=fetch_subprojects)
            self.context.load(config)
        except BstError as e:
            click.echo("Error loading user configuration: {}".format(e), err=True)
            sys.exit(-1)

        # Override things in the context from our command line options,
        # the command line when used, trumps the config files.
        #
        override_map = {
            'strict': 'strict_build_plan',
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

        # Create the application's scheduler
        self.scheduler = Scheduler(self.context,
                                   interrupt_callback=self.interrupt_handler,
                                   ticker_callback=self.tick,
                                   job_start_callback=self.job_started,
                                   job_complete_callback=self.job_completed)

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
        self.context._set_message_handler(self.message_handler)

        try:
            self.project = Project(directory, self.context, cli_options=self.main_options['option'])
        except BstError as e:
            click.echo("Error loading project: {}".format(e), err=True)
            sys.exit(-1)

        try:
            self.pipeline = Pipeline(self.context, self.project, elements, except_,
                                     rewritable=rewritable)
        except BstError as e:
            click.echo("Error loading pipeline: {}".format(e), err=True)
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
            click.echo("Error initializing pipeline: {}".format(e), err=True)
            sys.exit(-1)

        # Pipeline is loaded, lets start displaying pipeline messages from tasks
        self.logger.size_request(self.pipeline)

        profile_end(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements))

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
    def print_error(self, error):
        click.echo("", err=True)
        click.echo("{}".format(error), err=True)
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
        if self.context._silent_messages() and (message.message_type not in unconditional_messages):
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
