#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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
import click
import pkg_resources  # From setuptools
from contextlib import contextmanager
from blessings import Terminal

# Import buildstream public symbols
from .. import Context, Project, Scope, Consistency

# Import various buildstream internals
from ..exceptions import _BstError
from .._message import MessageType, unconditional_messages
from .._pipeline import Pipeline, PipelineError
from .._scheduler import Scheduler
from .._profile import Topics, profile_start, profile_end

# Import frontend assets
from . import Profile, LogLine, Status

# Some globals resolved for default arguments in the cli
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()


##################################################################
#                          Main Options                          #
##################################################################
@click.group()
@click.version_option(version=build_stream_version)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="Project directory (default: current directory)")
@click.option('--on-error', default=None,
              type=click.Choice(['continue', 'quit', 'terminate']),
              help="What to do when an error is encountered")
@click.option('--fetchers', type=click.INT, default=None,
              help="Maximum simultaneous download tasks")
@click.option('--builders', type=click.INT, default=None,
              help="Maximum simultaneous build tasks")
@click.option('--pushers', type=click.INT, default=None,
              help="Maximum simultaneous upload tasks")
@click.option('--no-interactive', is_flag=True, default=False,
              help="Force non interactive mode, otherwise this is automatically decided")
@click.option('--verbose/--no-verbose', default=None,
              help="Be extra verbose")
@click.option('--debug/--no-debug', default=None,
              help="Print debugging output")
@click.option('--error-lines', type=click.INT, default=None,
              help="Maximum number of lines to show from a task log")
@click.option('--message-lines', type=click.INT, default=None,
              help="Maximum number of lines to show in a detailed message")
@click.option('--log-file',
              type=click.File(mode='w', encoding='UTF-8'),
              help="A file to store the main log (allows storing the main log while in interactive mode)")
@click.option('--colors/--no-colors', default=None,
              help="Force enable/disable ANSI color codes in output")
@click.option('--arch', '-a', default=host_machine,
              help="Machine architecture (default: %s)" % host_machine)
@click.option('--host-arch',
              help="Machine architecture for the sandbox (defaults to --arch)")
@click.option('--target-arch',
              help="Machine architecture for build output (defaults to --arch)")
@click.option('--strict/--no-strict', default=None, is_flag=True,
              help="Elements must be rebuilt when their dependencies have changed")
@click.pass_context
def cli(context, **kwargs):
    """Build and manipulate BuildStream projects

    Most of the main options override options in the
    user preferences configuration file.
    """

    # Create the App, giving it the main arguments
    context.obj = App(dict(kwargs))


##################################################################
#                          Build Command                         #
##################################################################
@cli.command(short_help="Build elements in a pipeline")
@click.option('--all', default=False, is_flag=True,
              help="Build elements that would not be needed for the current build plan")
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before building (implies --all)")
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.pass_obj
def build(app, target, variant, all, track):
    """Build elements in a pipeline"""

    app.initialize(target, variant, rewritable=track, inconsistent=track)
    app.print_heading()
    try:
        app.pipeline.build(app.scheduler, all, track)
        click.echo("")
        app.print_summary()
    except PipelineError:
        click.echo("")
        app.print_summary()
        sys.exit(-1)


##################################################################
#                          Fetch Command                         #
##################################################################
@cli.command(short_help="Fetch sources in a pipeline")
@click.option('--except', 'except_', multiple=True,
              help="Except certain dependencies from fetching")
@click.option('--deps', '-d', default='plan',
              type=click.Choice(['none', 'plan', 'all']),
              help='The dependencies to fetch (default: plan)')
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before fetching")
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.pass_obj
def fetch(app, target, variant, deps, track, except_):
    """Fetch sources required to build the pipeline

    By default this will only try to fetch sources which are
    required for the build plan of the specified target element,
    omitting sources for any elements which are already built
    and available in the artifact cache.

    Specify `--deps` to control which sources to fetch:

    \b
        none:  No dependencies, just the element itself
        plan:  Only dependencies required for the build plan
        all:   All dependencies
    """
    app.initialize(target, variant, rewritable=track, inconsistent=track)
    try:
        dependencies = app.pipeline.deps_elements(deps, except_)
        app.print_heading(deps=dependencies)
        app.pipeline.fetch(app.scheduler, dependencies, track)
        click.echo("")
        app.print_summary()
    except PipelineError as e:
        click.echo("{}".format(e))
        app.print_summary()
        sys.exit(-1)


##################################################################
#                          Track Command                         #
##################################################################
@cli.command(short_help="Track new source references")
@click.option('--except', 'except_', multiple=True,
              help="Except certain dependencies from tracking")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependencies to track (default: none)')
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.pass_obj
def track(app, target, variant, deps, except_):
    """Consults the specified tracking branches for new versions available
    to build and updates the project with any newly available references.

    By default this will track just the specified element, but you can also
    update a whole tree of dependencies in one go.

    Specify `--deps` to control which sources to track:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    app.initialize(target, variant, rewritable=True, inconsistent=True)
    try:
        dependencies = app.pipeline.deps_elements(deps, except_)
        app.print_heading(deps=dependencies)
        app.pipeline.track(app.scheduler, dependencies)
        click.echo("")
        app.print_summary()
    except PipelineError as e:
        click.echo("{}".format(e))
        app.print_summary()
        sys.exit(-1)


##################################################################
#                           Show Command                         #
##################################################################
@cli.command(short_help="Show elements in the pipeline")
@click.option('--except', 'except_', multiple=True,
              help="Except certain dependencies")
@click.option('--deps', '-d', default='all',
              type=click.Choice(['none', 'plan', 'run', 'build', 'all']),
              help='The dependencies to show (default: all)')
@click.option('--order', default="stage",
              type=click.Choice(['stage', 'alpha']),
              help='Staging or alphabetic ordering of dependencies')
@click.option('--format', '-f', metavar='FORMAT', default=None,
              type=click.STRING,
              help='Format string for each element')
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.pass_obj
def show(app, target, variant, deps, except_, order, format):
    """Show elements in the pipeline

    By default this will show all of the dependencies of the
    specified target element.

    Specify `--deps` to control which elements to show:

    \b
        none:  No dependencies, just the element itself
        plan:  Dependencies required for a build plan
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies

    \b
    FORMAT
    ~~~~~~
    The --format option controls what should be printed for each element,
    the following symbols can be used in the format string:

    \b
        %{name}           The element name
        %{variant}        The selected element variant
        %{key}            The abbreviated cache key (if all sources are consistent)
        %{full-key}       The full cache key (if all sources are consistent)
        %{state}          cached, buildable, waiting or inconsistent
        %{config}         The element configuration
        %{vars}           Variable configuration
        %{env}            Environment settings
        %{public}         Public domain data
        %{workspaced}     If the element is workspaced
        %{workspace-dirs} A list of workspace directories

    The value of the %{symbol} without the leading '%' character is understood
    as a pythonic formatting string, so python formatting features apply,
    examle:

    \b
        bst show target.bst --format \\
            'Name: %{name: ^20} Key: %{key: ^8} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        bst show target.bst --format \\
            $'---------- %{name} ----------\\n%{vars}'
    """
    app.initialize(target, variant)
    try:
        dependencies = app.pipeline.deps_elements(deps, except_)
    except PipelineError as e:
        click.echo("{}".format(e))
        sys.exit(-1)

    if order == "alpha":
        dependencies = sorted(dependencies)

    if not format:
        format = app.context.log_element_format

    report = app.logger.show_pipeline(dependencies, format)
    click.echo(report, color=app.colors)


##################################################################
#                          Shell Command                         #
##################################################################
@cli.command(short_help="Shell into an element's sandbox environment")
@click.option('--builddir', '-b', default=None,
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="Existing build directory")
@click.option('--scope', '-s', default=None,
              type=click.Choice(['build', 'run']),
              help='Specify element scope to stage')
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.pass_obj
def shell(app, target, variant, builddir, scope):
    """Shell into an element's sandbox environment

    This can be used either to debug building or to launch
    test and debug successful build results.

    Use the --builddir option with an existing build directory
    or use the --scope option instead to create a new staging
    area automatically.
    """
    if builddir is None and scope is None:
        click.echo("Must specify either --builddir or --scope")
        sys.exit(1)

    if scope == "run":
        scope = Scope.RUN
    elif scope == "build":
        scope = Scope.BUILD

    app.initialize(target, variant)

    # Assert we have everything we need built.
    missing_deps = []
    if scope is not None:
        for dep in app.pipeline.dependencies(scope):
            if not dep._cached():
                missing_deps.append(dep)

    if missing_deps:
        click.echo("")
        click.echo("Missing elements for staging an environment for a shell:")
        for dep in missing_deps:
            click.echo("   {}".format(dep.name))
        click.echo("")
        click.echo("Try building them first")
        sys.exit(-1)

    try:
        app.pipeline.target._shell(scope, builddir)
    except _BstError as e:
        click.echo("")
        click.echo("Errors shelling into this pipeline: %s" % str(e))
        sys.exit(-1)


##################################################################
#                        Checkout Command                        #
##################################################################
@cli.command(short_help="Checkout a built artifact")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
@click.argument('directory')
@click.pass_obj
def checkout(app, target, variant, directory, force):
    """Checkout a built artifact to the specified directory
    """
    app.initialize(target, variant)
    try:
        app.pipeline.checkout(directory, force)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                     Source Bundle Command                      #
##################################################################
@cli.command(name="source-bundle", short_help="Produce a build bundle to be manually executed")
@click.option('--except', 'except_', multiple=True,
              help="Elements to except from the tarball")
@click.option('--compression', default='gz',
              type=click.Choice(['none', 'gz', 'bz2', 'xz']),
              help="Compress the tar file using the given algorithm.")
@click.option('--deps', '-d', default='build',
              type=click.Choice(['none', 'run', 'build']),
              help='The elements to bundle (default: build)')
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before building")
@click.option('--variant',
              help='A variant of the specified target')
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--directory', default=os.getcwd(),
              help="The directory to write the tarball to")
@click.argument('target')
@click.pass_obj
def source_bundle(app, target, variant, force, directory,
                  track, deps, compression, except_):
    """Produce a build bundle to be manually executed

    Specify `--deps` to control which elements to show:

    \b
        none:  No dependencies, just the element itself
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
    """
    app.initialize(target, variant, rewritable=track, inconsistent=track)
    try:
        dependencies = app.pipeline.deps_elements(deps, except_)
        app.print_heading(dependencies)
        app.pipeline.source_bundle(app.scheduler, dependencies, force, track,
                                   compression, except_, directory)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                      Workspace Command                         #
##################################################################
@cli.group(short_help="")
def workspace():
    pass


##################################################################
#                     Workspace Open Command                     #
##################################################################
@workspace.command(name='open', short_help="Create a workspace for manual source modification")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--source', '-s', default=None,
              help="The source to create a workspace for. Projects with one source may omit this")
@click.option('--variant',
              help='A variant of the specified target')
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch new source references before checking out the workspace")
@click.argument('element')
@click.argument('directory')
@click.pass_obj
def workspace_open(app, no_checkout, force, source, variant, track, element, directory):
    app.initialize(element, variant, rewritable=track, inconsistent=track)
    try:
        app.pipeline.open_workspace(app.scheduler, directory, source, no_checkout, track, force)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                     Workspace Close Command                    #
##################################################################
@workspace.command(name='close', short_help="Close a workspace")
@click.option('--source', '-s', default=None,
              help="The source of the workspace to remove. Projects with one source may omit this")
@click.option('--remove-dir', default=False, is_flag=True,
              help="Remove the path that contains the closed workspace")
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('element')
@click.pass_obj
def workspace_close(app, source, remove_dir, variant, element):
    if remove_dir:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting')
            sys.exit(-1)

    app.initialize(element, variant)
    try:
        app.pipeline.close_workspace(source, remove_dir)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                     Workspace Reset Command                    #
##################################################################
@workspace.command(name='reset', short_help="Reset a workspace to its original state")
@click.option('--source', '-s', default=None,
              help="The source of the workspace to reset. Projects with one source may omit this")
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch the latest source before resetting")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.option('--variant',
              help='A variant of the specified target')
@click.confirmation_option(prompt='This will remove all your changes, are you sure?')
@click.argument('element')
@click.pass_obj
def workspace_reset(app, source, track, no_checkout, variant, element):
    app.initialize(element, variant)
    try:
        app.pipeline.reset_workspace(app.scheduler, source, track, no_checkout)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                     Workspace List Command                     #
##################################################################
@workspace.command(name='list', short_help="List open workspaces")
@click.pass_obj
def workspace_list(app):
    project = Project(app.main_options['directory'],
                      app.host_arch,
                      app.target_arch)

    logger = LogLine(app.content_profile,
                     app.format_profile,
                     app.success_profile,
                     app.error_profile,
                     app.detail_profile,
                     indent=4)

    report = logger.show_workspaces(project._workspaces())
    click.echo(report, color=app.colors)


##################################################################
#                    Main Application State                      #
##################################################################

class App():

    def __init__(self, main_options):
        self.main_options = main_options
        self.messaging_enabled = False
        self.logger = None
        self.status = None
        self.target = None
        self.variant = None
        self.host_arch = main_options['host_arch'] or main_options['arch']
        self.target_arch = main_options['target_arch'] or main_options['arch']

        # Main asset handles
        self.context = None
        self.project = None
        self.scheduler = None
        self.pipeline = None

        # For the initialization time tickers
        self.file_count = 0
        self.resolve_count = 0
        self.cache_count = 0

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

        # Early enable messaging in debug mode
        if self.main_options['debug']:
            click.echo("DEBUG: Early enablement of messages")
            self.messaging_enabled = True

        # Resolve whether to use colors in output
        if self.main_options['colors'] is None:
            self.colors = self.is_a_tty
        elif self.main_options['colors']:
            self.colors = True
        else:
            self.colors = False

    #
    # Initialize the main pipeline
    #
    def initialize(self, target, variant, rewritable=False, inconsistent=False):
        self.target = target
        self.variant = variant

        profile_start(Topics.LOAD_PIPELINE, target.replace(os.sep, '-') + '-' +
                      self.host_arch + '-' + self.target_arch)

        directory = self.main_options['directory']
        config = self.main_options['config']

        try:
            self.context = Context(self.host_arch, self.target_arch)
            self.context.load(config)
        except _BstError as e:
            click.echo("Error loading user configuration: %s" % str(e))
            sys.exit(1)

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
            'pushers': 'sched_pushers'
        }
        for cli_option, context_attr in override_map.items():
            option_value = self.main_options.get(cli_option)
            if option_value is not None:
                setattr(self.context, context_attr, option_value)

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
            indent=4,
            # Number of last lines in an element's log to print (when encountering errors)
            log_lines=self.context.log_error_lines,
            # Maximum number of lines to print in a detailed message
            message_lines=self.context.log_message_lines,
            # Whether to print additional debugging information
            debug=self.context.log_debug)

        # Propagate pipeline feedback to the user
        self.context._set_message_handler(self.message_handler)

        try:
            self.project = Project(directory, self.host_arch, self.target_arch)
        except _BstError as e:
            click.echo("Error loading project: %s" % str(e))
            sys.exit(1)

        try:
            self.pipeline = Pipeline(self.context, self.project, target, variant,
                                     inconsistent=inconsistent,
                                     rewritable=rewritable,
                                     load_ticker=self.load_ticker,
                                     resolve_ticker=self.resolve_ticker,
                                     cache_ticker=self.cache_ticker)
        except _BstError as e:
            click.echo("Error loading pipeline: %s" % str(e))
            sys.exit(1)

        # Create our status printer, only available in interactive
        self.status = Status(self.content_profile, self.format_profile,
                             self.success_profile, self.error_profile,
                             self.pipeline, self.scheduler,
                             colors=self.colors)

        # Pipeline is loaded, lets start displaying pipeline messages from tasks
        self.logger.size_request(self.pipeline)
        self.messaging_enabled = True

        profile_end(Topics.LOAD_PIPELINE, target.replace(os.sep, '-') + '-' + self.host_arch + '-' + self.target_arch)

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
                       "  continue  - Continue queueing jobs as much as possible\n" +
                       "  quit      - Exit after all ongoing jobs complete\n" +
                       "  terminate - Terminate any ongoing jobs and exit\n" +
                       "\n" +
                       "Pressing ^C again will terminate jobs and exit\n",
                       err=True)

            try:
                choice = click.prompt("Choice:",
                                      type=click.Choice(['continue', 'quit', 'terminate']),
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

    def job_completed(self, element, action_name, success):
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
                           .format(element))
            else:
                self.handle_failure(element, failure)

    def handle_failure(self, element, failure):

        # Handle non interactive mode setting of what to do when a job fails.
        if not self.interactive:
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
                       "  continue  - Continue queueing jobs as much as possible\n" +
                       "  quit      - Exit after all ongoing jobs complete\n" +
                       "  terminate - Terminate any ongoing jobs and exit\n")
            if failure.logfile:
                summary += "  log       - View the full log file\n"
            if failure.sandbox:
                summary += "  shell     - Drop into a shell in the failed build sandbox\n"
            summary += "\nPressing ^C will terminate jobs and exit\n"

            choices = ['continue', 'quit', 'terminate']
            if failure.logfile:
                choices += ['log']
            if failure.sandbox:
                choices += ['shell']

            choice = ''
            while choice not in ['continue', 'quit', 'terminate']:
                click.echo(summary, err=True)

                try:
                    choice = click.prompt("Choice:", type=click.Choice(choices),
                                          default='continue', err=True)
                except click.Abort:
                    # Ensure a newline after automatically printed '^C'
                    click.echo("", err=True)
                    choice = 'terminate'

                # Handle choices which you can come back from
                #
                if choice == 'shell':
                    click.echo("\nDropping into an interactive shell in the failed build sandbox\n", err=True)
                    element._shell(Scope.BUILD, failure.sandbox)
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

    def tick(self, elapsed):
        self.maybe_render_status()

    #
    # Prints the application startup heading, used for commands which
    # will process a pipeline.
    #
    def print_heading(self, deps=None):
        self.logger.print_heading(self.pipeline, self.variant,
                                  self.main_options['log_file'],
                                  styling=self.colors,
                                  deps=deps)

    #
    # Print a summary of the queues
    #
    def print_summary(self):
        self.logger.print_summary(self.pipeline, self.scheduler,
                                  self.main_options['log_file'],
                                  styling=self.colors)

    #
    # Handle messages from the pipeline
    #
    def message_handler(self, message, context):

        # Drop messages by default in the beginning while
        # loading the pipeline, unless debug is specified.
        if not self.messaging_enabled:
            return

        # Drop status messages from the UI if not verbose, we'll still see
        # info messages and status messages will still go to the log files.
        if not context.log_verbose and message.message_type == MessageType.STATUS:
            return

        # Hold on to the failure messages
        if message.message_type in [MessageType.FAIL, MessageType.BUG] and message.unique_id is not None:
            self.fail_messages[message.unique_id] = message

        # Send to frontend if appropriate
        if (self.context._silent_messages() and
            message.message_type not in unconditional_messages):
            return

        if self.status:
            self.status.clear()

        text = self.logger.render(message)
        click.echo(text, color=self.colors, nl=False)

        # Maybe render the status area
        self.maybe_render_status()

        # Additionally log to a file
        if self.main_options['log_file']:
            click.echo(text, file=self.main_options['log_file'], color=False, nl=False)

    #
    # Tickers at initialization time
    #
    def load_ticker(self, name):
        if name:
            self.file_count += 1

            if self.is_a_tty:
                click.echo("Loading:   {:0>3}\r"
                           .format(self.file_count), nl=False, err=True)
            elif self.file_count == 1:
                click.echo("Loading.", nl=False, err=True)
            else:
                click.echo(".", nl=False, err=True)
        else:
            click.echo('', err=True)

    def resolve_ticker(self, name):
        if name:
            self.resolve_count += 1

            if self.is_a_tty:
                click.echo("Resolving: {:0>3}/{:0>3}\r"
                           .format(self.file_count, self.resolve_count), nl=False, err=True)
            elif self.resolve_count == 1:
                click.echo("Resolving {} elements."
                           .format(self.file_count), nl=False, err=True)
            else:
                click.echo(".", nl=False, err=True)
        else:
            click.echo('', err=True)

    def cache_ticker(self, name):
        if name:
            self.cache_count += 1

            if self.is_a_tty:
                click.echo("Checking:  {:0>3}/{:0>3}\r"
                           .format(self.file_count, self.cache_count), nl=False, err=True)
            elif self.cache_count == 1:
                click.echo("Checking {} elements."
                           .format(self.file_count), nl=False, err=True)
            else:
                click.echo(".", nl=False, err=True)
        else:
            click.echo('', err=True)

    @contextmanager
    def interrupted(self):
        self.scheduler.disconnect_signals()

        self.status.clear()
        self.scheduler.suspend_jobs()

        yield

        self.maybe_render_status()
        self.scheduler.resume_jobs()
        self.scheduler.connect_signals()
