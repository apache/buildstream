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
import copy
from ruamel import yaml

from . import Context, Project, Scope, Consistency
from .exceptions import _BstError
from ._message import MessageType
from ._pipeline import Pipeline, PipelineError
from . import utils
from ._profile import Topics, profile_start, profile_end
from ._widget import Profile, LogLine

# Some nasty globals
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()

main_options = {}
main_options_set = {}
main_context = None
messaging_enabled = False
logger = None


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
              type=click.Choice(['continue', 'quit']),
              help="What to do when an error is encountered")
@click.option('--fetchers', type=click.INT, default=None,
              help="Maximum simultaneous download tasks")
@click.option('--builders', type=click.INT, default=None,
              help="Maximum simultaneous build tasks")
@click.option('--verbose/--no-verbose', default=None,
              help="Be extra verbose")
@click.option('--debug/--no-debug', default=None,
              help="Print debugging output")
@click.option('--error-lines', type=click.INT, default=None,
              help="Maximum number of lines to show from a task log")
@click.option('--log-file',
              type=click.File(mode='w', encoding='UTF-8'),
              help="A file to store the main log (allows storing the main log while in interactive mode)")
def cli(**kwargs):
    """Build and manipulate BuildStream projects

    Most of the main options override options in the
    user preferences configuration file.
    """
    # Record main options for usage in create_pipeline()
    for key, value in dict(kwargs).items():
        main_options[key] = value

    # Early enable messaging in debug mode
    global messaging_enabled
    if main_options['debug']:
        print("DEBUG: Early enablement of messages")
        messaging_enabled = True


##################################################################
#                          Build Command                         #
##################################################################
@cli.command(short_help="Build elements in a pipeline")
@click.option('--all', default=False, is_flag=True,
              help="Build elements that would not be needed for the current build plan")
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def build(target, arch, variant, all):
    """Build elements in a pipeline"""
    pipeline = create_pipeline(target, arch, variant)
    try:
        changed = pipeline.build(all)
        click.echo("")
    except PipelineError:
        click.echo("")
        click.echo("Error building this pipeline")
        sys.exit(1)

    click.echo(("Successfully built {changed} elements in pipeline " +
                "with target '{target}' in directory: {directory}").format(
                    changed=len(changed), target=target, directory=main_options['directory']))


##################################################################
#                          Fetch Command                         #
##################################################################
@cli.command(short_help="Fetch sources in a pipeline")
@click.option('--needed', default=False, is_flag=True,
              help="Fetch only sources required to build missing artifacts")
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def fetch(target, arch, variant, needed):
    """Fetch sources in a pipeline"""
    pipeline = create_pipeline(target, arch, variant)
    try:
        inconsistent, cached, plan = pipeline.fetch(needed)
        click.echo("")
    except PipelineError:
        click.echo("")
        click.echo("Error fetching sources for this pipeline")
        sys.exit(1)

    click.echo("Fetched sources for {} elements, {} inconsistent elements, {} cached elements"
               .format(len(plan), len(inconsistent), len(cached)))


##################################################################
#                          Track Command                         #
##################################################################
@cli.command(short_help="Track new source references")
@click.option('--needed', default=False, is_flag=True,
              help="Track only sources required to build missing artifacts")
@click.option('--list', '-l', default=False, is_flag=True,
              help='List the sources which were tracked')
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def track(target, arch, variant, needed, list):
    """Track new source references

    Updates the project with new source references from
    any sources which are configured to track a remote
    branch or tag.

    The project data will be rewritten inline.
    """
    pipeline = create_pipeline(target, arch, variant, rewritable=True)
    try:
        sources = pipeline.track(needed)
        click.echo("")
    except PipelineError:
        click.echo("")
        click.echo("Error tracking sources in pipeline")
        sys.exit(1)

    if list:
        # --list output
        for source in sources:
            click.echo("{}".format(source))

    elif len(sources) > 0:
        click.echo(("Successfully updated {n_sources} source references in pipeline " +
                    "with target '{target}' in directory: {directory}").format(
                        n_sources=len(sources), target=target, directory=main_options['directory']))
    else:
        click.echo(("Pipeline with target '{target}' already up to date in directory: {directory}").format(
            target=target, directory=main_options['directory']))


##################################################################
#                           Show Command                         #
##################################################################
@cli.command(short_help="Show elements in the pipeline")
@click.option('--deps', '-d', default=None,
              type=click.Choice(['all', 'build', 'run']),
              help='Optionally specify a dependency scope to show')
@click.option('--order', default="stage",
              type=click.Choice(['stage', 'alpha']),
              help='Staging or alphabetic ordering of dependencies')
@click.option('--format', '-f', metavar='FORMAT', default="%{state: >12} %{key} %{name}",
              type=click.STRING,
              help='Format string for each element')
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def show(target, arch, variant, deps, order, format):
    """Show elements in the pipeline

    By default this will only show the specified element, use
    the --deps option to show an entire pipeline.

    \b
    FORMAT
    ~~~~~~
    The --format option controls what should be printed for each element,
    the following symbols can be used in the format string:

    \b
        %{name}   The element name
        %{key}    The cache key (if all sources are consistent)
        %{state}  cached, buildable, waiting or inconsistent
        %{config} The element configuration
        %{vars}   Variable configuration
        %{env}    Environment settings

    The value of the %{symbol} without the leading '%' character is understood
    as a pythonic formatting string, so python formatting features apply,
    examle:

    \b
        build-stream show target.bst --format \\
            'Name: %{name: ^20} Key: %{key: ^8} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        build-stream show target.bst --format \\
            $'---------- %{name} ----------\\n%{vars}'
    """
    pipeline = create_pipeline(target, arch, variant)
    report = ''
    p = Profile()

    profile_start(Topics.SHOW, target.replace(os.sep, '-') + '-' + arch)

    if deps is not None:
        scope = deps
        if scope == "all":
            scope = Scope.ALL
        elif scope == "build":
            scope = Scope.BUILD
        else:
            scope = Scope.RUN

        if order == "alpha":
            dependencies = sorted(pipeline.dependencies(scope))
        else:
            dependencies = pipeline.dependencies(scope)
    else:
        dependencies = [pipeline.target]

    for element in dependencies:
        line = p.fmt_subst(format, 'name', element._get_display_name(), fg='blue', bold=True)
        cache_key = element._get_display_key()

        consistency = element._consistency()
        if consistency == Consistency.INCONSISTENT:
            line = p.fmt_subst(line, 'key', "")
            line = p.fmt_subst(line, 'state', "no reference", fg='red')
        else:
            line = p.fmt_subst(line, 'key', cache_key, fg='yellow')
            if element._cached():
                line = p.fmt_subst(line, 'state', "cached", fg='magenta')
            elif consistency == Consistency.RESOLVED:
                line = p.fmt_subst(line, 'state', "fetch needed", fg='red')
            elif element._buildable():
                line = p.fmt_subst(line, 'state', "buildable", fg='green')
            else:
                line = p.fmt_subst(line, 'state', "waiting", fg='blue')

        # Element configuration
        if "%{config" in format:
            config = utils._node_sanitize(element._Element__config)
            line = p.fmt_subst(
                line, 'config',
                yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

        # Variables
        if "%{vars" in format:
            variables = utils._node_sanitize(element._Element__variables.variables)
            line = p.fmt_subst(
                line, 'vars',
                yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

        # Environment
        if "%{env" in format:
            environment = utils._node_sanitize(element._Element__environment)
            line = p.fmt_subst(
                line, 'env',
                yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

        report += line + '\n'

    click.echo(report.rstrip('\n'))
    profile_end(Topics.SHOW, target.replace(os.sep, '-') + '-' + arch)


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
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def shell(target, arch, variant, builddir, scope):
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

    pipeline = create_pipeline(target, arch, variant)

    # Assert we have everything we need built.
    missing_deps = []
    if scope is not None:
        for dep in pipeline.dependencies(scope):
            if not dep._cached():
                missing_deps.append(dep)

    if missing_deps:
        click.echo("")
        click.echo("Missing elements for staging an environment for a shell:")
        for dep in missing_deps:
            click.echo("   {}".format(dep._get_display_name()))
        click.echo("")
        click.echo("Try building them first")
        sys.exit(1)

    try:
        pipeline.target._shell(scope, builddir)
    except _BstError as e:
        click.echo("")
        click.echo("Errors shelling into this pipeline: %s" % str(e))
        sys.exit(1)


##################################################################
#                        Helper Functions                        #
##################################################################

#
# Handle messages from the pipeline
#
def message_handler(message, context):

    # Drop messages by default in the beginning while
    # loading the pipeline, unless debug is specified.
    if not messaging_enabled:
        return

    # Drop status messages from the UI if not verbose, we'll still see
    # info messages and status messages will still go to the log files.
    if not context.log_verbose and message.message_type == MessageType.STATUS:
        return

    text = logger.render(message)

    click.echo(text, nl=False)

    # Additionally log to a file
    if main_options['log_file']:
        click.echo(text, file=main_options['log_file'], color=False, nl=False)


#
# Create a pipeline
#
def create_pipeline(target, arch, variant, rewritable=False):
    global messaging_enabled
    global logger

    profile_start(Topics.LOAD_PIPELINE, target.replace(os.sep, '-') + '-' + arch)

    directory = main_options['directory']
    config = main_options['config']

    #
    # Some local tickers and state to show the user what's going on
    # while loading
    #
    file_count = 0
    resolve_count = 0
    cache_count = 0

    def load_ticker(name):
        nonlocal file_count
        if name:
            file_count += 1
            click.echo("Loading:   {:0>3}\r".format(file_count), nl=False, err=True)
        else:
            click.echo('', err=True)

    def resolve_ticker(name):
        nonlocal resolve_count
        if name:
            resolve_count += 1
            click.echo("Resolving: {:0>3}/{:0>3}\r".format(file_count, resolve_count), nl=False, err=True)
        else:
            click.echo('', err=True)

    def cache_ticker(name):
        nonlocal cache_count
        if name:
            cache_count += 1
            click.echo("Checking:  {:0>3}/{:0>3}\r".format(file_count, cache_count), nl=False, err=True)
        else:
            click.echo('', err=True)

    try:
        context = Context(arch)
        context.load(config)
    except _BstError as e:
        click.echo("Error loading user configuration: %s" % str(e))
        sys.exit(1)

    # Override things in the context from our command line options,
    # the command line when used, trumps the config files.
    #
    if main_options.get('debug') is not None:
        context.log_debug = main_options['debug']
    if main_options.get('verbose') is not None:
        context.log_verbose = main_options['verbose']
    if main_options.get('on_error') is not None:
        context.sched_error_action = main_options['on_error']
    if main_options.get('error_lines') is not None:
        context.log_error_lines = main_options['error_lines']
    if main_options.get('fetchers') is not None:
        context.sched_fetchers = main_options['fetchers']
    if main_options.get('builders') is not None:
        context.sched_builders = main_options['builders']

    # Create the logger right before setting the message handler
    logger = LogLine(
        # Content
        Profile(fg='yellow'),
        # Formatting
        Profile(fg='cyan', dim=True),
        # Errors
        Profile(fg='red', dim=True),
        # Details (log lines and other detailed messages)
        Profile(dim=True),
        # Indentation for detailed messages
        indent=4,
        # Number of last lines in an element's log to print (when encountering errors)
        log_lines=context.log_error_lines,
        # Whether to print additional debugging information
        debug=context.log_debug)

    # Propagate pipeline feedback to the user
    context._set_message_handler(message_handler)

    try:
        project = Project(directory, arch)
    except _BstError as e:
        click.echo("Error loading project: %s" % str(e))
        sys.exit(1)

    try:
        pipeline = Pipeline(context, project, target, variant,
                            rewritable=rewritable,
                            load_ticker=load_ticker,
                            resolve_ticker=resolve_ticker,
                            cache_ticker=cache_ticker)
    except _BstError as e:
        click.echo("Error loading pipeline: %s" % str(e))
        sys.exit(1)

    # Pipeline is loaded, lets start displaying pipeline messages from tasks
    logger.size_request(pipeline)
    messaging_enabled = True

    profile_end(Topics.LOAD_PIPELINE, target.replace(os.sep, '-') + '-' + arch)

    return pipeline
