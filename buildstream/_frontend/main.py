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
from .. import Context, Project, Scope, Consistency, LoadError

# Import various buildstream internals
from ..exceptions import _BstError
from .._message import MessageType, unconditional_messages
from .._pipeline import Pipeline, PipelineError
from .._scheduler import Scheduler
from .._profile import Topics, profile_start, profile_end
from .. import _yaml

# Import frontend assets
from . import Profile, LogLine, Status
from .complete import main_bashcomplete, complete_path, CompleteUnhandled

# Some globals resolved for default arguments in the cli
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()


##################################################################
#            Override of click's main entry point                #
##################################################################

# Special completion for completing the bst elements in a project dir
def complete_target(ctx, args, incomplete):
    app = ctx.obj

    # First resolve the directory, in case there is an
    # active --directory/-C option
    #
    base_directory = '.'
    idx = -1
    try:
        idx = args.index('-C')
    except ValueError:
        try:
            idx = args.index('--directory')
        except ValueError:
            pass

    if idx >= 0 and len(args) > idx + 1:
        base_directory = args[idx + 1]

    # Now parse the project.conf just to find the element path,
    # this is unfortunately a bit heavy.
    project_file = os.path.join(base_directory, 'project.conf')
    try:
        project = _yaml.load(project_file)
    except LoadError:
        # If there is no project directory in context, just dont
        # even bother trying to complete anything.
        return []

    # The project is not required to have an element-path
    element_directory = project.get('element-path')

    # If a project was loaded, use it's element-path to
    # adjust our completion's base directory
    if element_directory:
        base_directory = os.path.join(base_directory, element_directory)

    return complete_path("File", incomplete, base_directory=base_directory)


def override_completions(cmd_param, ctx, args, incomplete):

    # We can't easily extend click's data structures without
    # modifying click itself, so just do some weak special casing
    # right here and select which parameters we want to handle specially.
    if isinstance(cmd_param.type, click.Path) and \
       (cmd_param.name == 'elements' or
        cmd_param.name == 'element'):
        return complete_target(ctx, args, incomplete)

    raise CompleteUnhandled()


def override_main(self, args=None, prog_name=None, complete_var=None,
                  standalone_mode=True, **extra):

    # Hook for the Bash completion.  This only activates if the Bash
    # completion is actually enabled, otherwise this is quite a fast
    # noop.
    if main_bashcomplete(self, prog_name, override_completions):

        # If we're running tests we cant just go calling exit()
        # from the main process.
        #
        # The below is a quicker exit path for the sake
        # of making completions respond faster.
        if 'BST_TEST_SUITE' not in os.environ:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)

        # Regular client return for test cases
        return

    original_main(self, args=args, prog_name=prog_name, complete_var=None,
                  standalone_mode=standalone_mode, **extra)


original_main = click.BaseCommand.main
click.BaseCommand.main = override_main


##################################################################
#                          Main Options                          #
##################################################################
@click.group(context_settings=dict(help_option_names=['-h', '--help']))
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
@click.option('--network-retries', type=click.INT, default=None,
              help="Maximum retries for network tasks")
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
@click.option('--option', '-o', type=click.Tuple([str, str]), multiple=True,
              help="Specify a project option")
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
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def build(app, elements, all, track):
    """Build elements in a pipeline"""

    app.initialize(elements, rewritable=track, inconsistent=track, fetch_remote_refs=True)
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
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def fetch(app, elements, deps, track, except_):
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
    app.initialize(elements, except_=except_,
                   rewritable=track, inconsistent=track)
    try:
        dependencies = app.pipeline.deps_elements(deps)
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
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def track(app, elements, deps, except_):
    """Consults the specified tracking branches for new versions available
    to build and updates the project with any newly available references.

    By default this will track just the specified element, but you can also
    update a whole tree of dependencies in one go.

    Specify `--deps` to control which sources to track:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    app.initialize(elements, except_=except_,
                   rewritable=True, inconsistent=True)
    try:
        dependencies = app.pipeline.deps_elements(deps)
        app.print_heading(deps=dependencies)
        app.pipeline.track(app.scheduler, dependencies)
        click.echo("")
        app.print_summary()
    except PipelineError as e:
        click.echo("{}".format(e))
        app.print_summary()
        sys.exit(-1)


##################################################################
#                           Pull Command                         #
##################################################################
@cli.command(short_help="Pull a built artifact")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependency artifacts to pull (default: none)')
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def pull(app, elements, deps):
    """Pull a built artifact from the configured remote artifact cache.

    Specify `--deps` to control which artifacts to pull:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    app.initialize(elements, fetch_remote_refs=True)
    try:
        to_pull = app.pipeline.deps_elements(deps)
        app.pipeline.pull(app.scheduler, to_pull)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                           Push Command                         #
##################################################################
@cli.command(short_help="Push a built artifact")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependencies to push (default: none)')
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def push(app, elements, deps):
    """Push a built artifact to the configured remote artifact cache.

    Specify `--deps` to control which artifacts to push:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    app.initialize(elements, fetch_remote_refs=True)
    try:
        to_push = app.pipeline.deps_elements(deps)
        app.pipeline.push(app.scheduler, to_push)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
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
@click.option('--downloadable', default=False, is_flag=True,
              help="Refresh downloadable state")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def show(app, elements, deps, except_, order, format, downloadable):
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
    app.initialize(elements, except_=except_, fetch_remote_refs=downloadable)
    try:
        dependencies = app.pipeline.deps_elements(deps)
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
@click.option('--build', '-b', is_flag=True, default=False,
              help='Create a build sandbox')
@click.option('--sysroot', '-s', default=None,
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="An existing sysroot")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('command', type=click.STRING, nargs=-1)
@click.pass_obj
def shell(app, element, sysroot, build, command):
    """Run a command in the target element's sandbox environment

    This will first stage a temporary sysroot for running
    the target element, assuming it has already been built
    and all required artifacts are in the local cache.

    Use the --build option to create a temporary sysroot for
    building the element instead.

    Use the --sysroot option with an existing failed build
    directory or with a checkout of the given target, in order
    to use a specific sysroot.

    If no COMMAND is specified, the default is to attempt
    to run an interactive shell with `sh -i`.
    """
    if build:
        scope = Scope.BUILD
    else:
        scope = Scope.RUN

    app.initialize((element,))

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
        exitcode = app.pipeline.targets[0]._shell(scope, sysroot, command=command)
        sys.exit(exitcode)
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
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('directory', type=click.Path(file_okay=False))
@click.pass_obj
def checkout(app, element, directory, force):
    """Checkout a built artifact to the specified directory
    """
    app.initialize((element,))
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
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before building")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--directory', default=os.getcwd(),
              help="The directory to write the tarball to")
@click.argument('target',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def source_bundle(app, target, force, directory,
                  track, compression, except_):
    """Produce a source bundle to be manually executed"""
    app.initialize((target,), rewritable=track, inconsistent=track)
    try:
        dependencies = app.pipeline.deps_elements('all')
        app.print_heading(dependencies)
        app.pipeline.source_bundle(app.scheduler, dependencies, force, track,
                                   compression, directory)
        click.echo("")
    except _BstError as e:
        click.echo("")
        click.echo("ERROR: {}".format(e))
        sys.exit(-1)


##################################################################
#                      Workspace Command                         #
##################################################################
@cli.group(short_help="Manipulate developer workspaces")
def workspace():
    """Manipulate developer workspaces"""
    pass


##################################################################
#                     Workspace Open Command                     #
##################################################################
@workspace.command(name='open', short_help="Open a new workspace")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--source', '-s', default=None, type=click.INT, metavar='INDEX',
              help="The source to create a workspace for. Projects with one source may omit this")
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch new source references before checking out the workspace")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('directory', type=click.Path(file_okay=False))
@click.pass_obj
def workspace_open(app, no_checkout, force, source, track, element, directory):
    """Open a workspace for manual source modification"""

    app.initialize((element,), rewritable=track, inconsistent=track)
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
@click.option('--source', '-s', default=None, type=click.INT, metavar='INDEX',
              help="The source of the workspace to remove. Projects with one source may omit this")
@click.option('--remove-dir', default=False, is_flag=True,
              help="Remove the path that contains the closed workspace")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_close(app, source, remove_dir, element):
    """Close a workspace"""

    app.initialize((element,))
    if app.interactive and remove_dir:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting')
            sys.exit(-1)

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
@click.option('--source', '-s', default=None, type=click.INT, metavar='INDEX',
              help="The source of the workspace to reset. Projects with one source may omit this")
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch the latest source before resetting")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_reset(app, source, track, no_checkout, element):
    """Reset a workspace to its original state"""
    app.initialize((element,))
    if app.interactive:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting')
            sys.exit(-1)

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
    """List open workspaces"""

    directory = app.main_options['directory']
    config = app.main_options['config']

    try:
        context = Context(app.main_options['option'], app.host_arch, app.target_arch)
        context.load(config)
    except _BstError as e:
        click.echo("Error loading user configuration: {}".format(e))
        sys.exit(-1)

    try:
        project = Project(directory, context)
    except _BstError as e:
        click.echo("Error loading project: {}".format(e))
        sys.exit(-1)

    workspaces = []
    for element_name, source_index, directory in project._list_workspaces():
        workspace = {
            'element': element_name,
            'directory': directory,
        }
        if source_index > 0:
            workspace['index'] = source_index

        workspaces.append(workspace)

    _yaml.dump({
        'workspaces': workspaces
    })


##################################################################
#                    Main Application State                      #
##################################################################

class App():

    def __init__(self, main_options):
        self.main_options = main_options
        self.messaging_enabled = False
        self.startup_messages = []
        self.logger = None
        self.status = None
        self.target = None
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

        # Check if we are connected to a tty, ensuring that tests are
        # always treated the same regardless of environment.
        if 'BST_TEST_SUITE' not in os.environ:
            self.is_a_tty = Terminal().is_a_tty
        else:
            self.is_a_tty = False

        # Figure out interactive mode
        if self.main_options['no_interactive']:
            self.interactive = False
        else:
            self.interactive = self.is_a_tty

        # Whether we handle failures interactively
        # defaults to whether we are interactive or not.
        self.interactive_failures = self.interactive

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
    def initialize(self, elements, except_=tuple(), rewritable=False,
                   inconsistent=False, fetch_remote_refs=False):

        profile_start(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements) + '-' +
                      self.host_arch + '-' + self.target_arch)

        directory = self.main_options['directory']
        config = self.main_options['config']

        try:
            self.context = Context(self.main_options['option'], self.host_arch, self.target_arch)
            self.context.load(config)
        except _BstError as e:
            click.echo("Error loading user configuration: %s" % str(e))
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
            self.project = Project(directory, self.context)
        except _BstError as e:
            click.echo("Error loading project: %s" % str(e))
            sys.exit(-1)

        try:
            self.pipeline = Pipeline(self.context, self.project, elements, except_,
                                     inconsistent=inconsistent,
                                     rewritable=rewritable,
                                     fetch_remote_refs=fetch_remote_refs,
                                     load_ticker=self.load_ticker,
                                     resolve_ticker=self.resolve_ticker,
                                     remote_ticker=self.remote_ticker,
                                     cache_ticker=self.cache_ticker)
        except _BstError as e:
            click.echo("Error loading pipeline: %s" % str(e))
            sys.exit(-1)

        # Create our status printer, only available in interactive
        self.status = Status(self.content_profile, self.format_profile,
                             self.success_profile, self.error_profile,
                             self.pipeline, self.scheduler,
                             colors=self.colors)

        # Pipeline is loaded, lets start displaying pipeline messages from tasks
        self.logger.size_request(self.pipeline)
        self.messaging_enabled = True

        profile_end(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, '-') for t in elements) + '-' +
                    self.host_arch + '-' + self.target_arch)

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
                           .format(element))
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
                       "  continue  - Continue queueing jobs as much as possible\n" +
                       "  quit      - Exit after all ongoing jobs complete\n" +
                       "  terminate - Terminate any ongoing jobs and exit\n" +
                       "  retry     - Retry this job\n")
            if failure.logfile:
                summary += "  log       - View the full log file\n"
            if failure.sandbox:
                summary += "  shell     - Drop into a shell in the failed build sandbox\n"
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
                elif choice == 'retry':
                    click.echo("\nRetrying failed job\n", err=True)
                    queue.failed_elements.remove(element)
                    queue.enqueue([element])

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

        # Print any held messages from startup after printing the heading
        for message in self.startup_messages:
            self.message_handler(message, self.context)
        self.startup_messages = []

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
            if message.message_type in unconditional_messages:
                self.startup_messages.append(message)
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
        if not self.context.log_verbose:
            return

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
        if not self.context.log_verbose:
            return

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

    def remote_ticker(self, name):
        if not self.context.log_verbose:
            return

        click.echo("Fetching artifact list from {}".format(name), err=True)

    def cache_ticker(self, name):
        if not self.context.log_verbose:
            return

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
