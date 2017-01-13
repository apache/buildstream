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
import subprocess
from ruamel import yaml

from . import Context, Project, Scope
from .exceptions import _ALL_EXCEPTIONS
from .plugin import _plugin_lookup
from ._message import MessageType
from . import _pipeline
from ._pipeline import Pipeline, PipelineError
from . import utils
from . import _term
from ._term import Color, Attr

# Some nasty globals
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()

main_options = {}
main_options_set = {}
main_context = None


def record_options(ctx, param, value):
    main_options_set[param.name] = True
    return value


##################################################################
#                          Main Options                          #
##################################################################
@click.group()
@click.version_option(version=build_stream_version)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--verbose/--no-verbose', callback=record_options,
              help="Whether to be extra verbose")
@click.option('--debug/--no-debug', callback=record_options,
              help="Print debugging output")
@click.option('--error-lines', default=20, is_eager=True,
              type=click.INT, callback=record_options,
              help="Print debugging output")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="Project directory (default: %s)" % os.getcwd())
def cli(config, verbose, debug, error_lines, directory):
    """Build and manipulate BuildStream projects"""
    main_options['config'] = config
    main_options['verbose'] = verbose
    main_options['directory'] = directory
    main_options['error_lines'] = error_lines
    main_options['debug'] = debug


##################################################################
#                          Fetch Command                         #
##################################################################
@cli.command(short_help="Fetch sources in a pipeline")
@click.option('--all', default=False, is_flag=True,
              help="Fetch all sources, even if the build can complete without some of them")
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def fetch(target, arch, variant, all):
    """Fetch sources in a pipeline"""
    pipeline = create_pipeline(main_options['directory'], target, arch, variant, main_options['config'])
    try:
        inconsistent = pipeline.fetch(all)
        click.echo("")
    except PipelineError:
        click.echo("")
        click.echo("Error fetching sources for this pipeline")
        sys.exit(1)

    if inconsistent:
        report = "Inconsistent sources on the following elements could not be fetched:\n"
        for element in inconsistent:
            report += "  {}".format(element)
        click.echo(report)
    else:
        click.echo(("Successfully fetched sources in pipeline " +
                    "with target '{target}' in directory: {directory}").format(
                        target=target, directory=main_options['directory']))


##################################################################
#                         Refresh Command                        #
##################################################################
@cli.command(short_help="Refresh sources in a pipeline")
@click.option('--all', default=False, is_flag=True,
              help="Refresh all sources, even if the build can complete without some of them")
@click.option('--list', '-l', default=False, is_flag=True,
              help='List the sources which were refreshed')
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def refresh(target, arch, variant, all, list):
    """Refresh sources in a pipeline

    Updates the project with new source references from
    any sources which are configured to track a remote
    branch or tag.
    """
    pipeline = create_pipeline(main_options['directory'], target, arch, variant, main_options['config'])

    try:
        sources = pipeline.refresh(all)
        click.echo("")
    except PipelineError:
        click.echo("")
        click.echo("Error refreshing pipeline")
        sys.exit(1)

    if list:
        # --list output
        for source in sources:
            click.echo("{}".format(source))

    elif len(sources) > 0:
        click.echo(("Successfully refreshed {n_sources} sources in pipeline " +
                    "with target '{target}' in directory: {directory}").format(
                        n_sources=len(sources), target=target, directory=main_options['directory']))
    else:
        click.echo(("Pipeline with target '{target}' already up to date in directory: {directory}").format(
            target=target, directory=main_options['directory']))


##################################################################
#                           Show Command                         #
##################################################################
@cli.command(short_help="Show elements in the pipeline")
@click.option('--scope', '-s', default="all",
              type=click.Choice(['all', 'build', 'run']))
@click.option('--order', default="stage",
              type=click.Choice(['stage', 'alpha']))
@click.option('--format', '-f', metavar='FORMAT', default="%{name: >20}: %{key: <64} (%{state})",
              type=click.STRING,
              help='Format string for each element')
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def show(target, arch, variant, scope, order, format):
    """Show elements in the pipeline

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
            'Name: %{name: ^20} Key: %{key: ^64} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        build-stream show target.bst --format \\
            $'---------- %{name} ----------\\n%{variables}'
    """
    pipeline = create_pipeline(main_options['directory'], target, arch, variant, main_options['config'])
    report = ''

    if scope == "all":
        scope = Scope.ALL
    elif scope == "build":
        scope = Scope.BUILD
    else:
        scope = Scope.RUN

    dependencies = pipeline.dependencies(scope)
    if order == "alpha":
        dependencies = sorted(pipeline.dependencies(scope))

    for element in dependencies:
        line = _term.fmt_subst(format, 'name', element.name, color=Color.BLUE, attrs=[Attr.BOLD])
        cache_key = element._get_cache_key()
        if cache_key is None:
            cache_key = ''

        if element._inconsistent():
            line = _term.fmt_subst(line, 'key', "")
            line = _term.fmt_subst(line, 'state', "inconsistent", color=Color.RED)
        else:
            line = _term.fmt_subst(line, 'key', cache_key, color=Color.YELLOW)
            if element._cached():
                line = _term.fmt_subst(line, 'state', "cached", color=Color.MAGENTA)
            elif element._buildable():
                line = _term.fmt_subst(line, 'state', "buildable", color=Color.GREEN)
            else:
                line = _term.fmt_subst(line, 'state', "waiting", color=Color.BLUE)

        # Element configuration
        config = utils._node_sanitize(element._Element__config)
        line = _term.fmt_subst(
            line, 'config',
            yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

        # Variables
        variables = utils._node_sanitize(element._Element__variables.variables)
        line = _term.fmt_subst(
            line, 'vars',
            yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

        # Environment
        environment = utils._node_sanitize(element._Element__environment)
        line = _term.fmt_subst(
            line, 'env',
            yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

        report += line + '\n'

    click.echo(report.rstrip('\n'))


##################################################################
#                        Helper Functions                        #
##################################################################


# Colors we use for labels of various message types
message_colors = {}
message_colors[MessageType.DEBUG] = Color.MAGENTA
message_colors[MessageType.STATUS] = Color.BLUE
message_colors[MessageType.WARN] = Color.YELLOW
message_colors[MessageType.ERROR] = Color.RED
message_colors[MessageType.START] = Color.CYAN
message_colors[MessageType.SUCCESS] = Color.GREEN
message_colors[MessageType.FAIL] = Color.RED


# This would be better as native python code, rather than requiring
# tail specifically.
def read_last_lines(logfile, n_lines):
    tail_command = utils.get_host_tool('tail')

    # Lets just expect this to always pass for now...
    output = subprocess.check_output([tail_command, '-n', str(n_lines), logfile])
    output = output.decode('UTF-8')
    return output.rstrip()


#
# Handle messages from the pipeline
#
def message_handler(message, context):

    # The detail indentation
    INDENT = "    "
    EMPTYTIME = "[--:--:--]"

    # Silently ignore debugging messages
    enable_debug = main_options['debug']
    if not enable_debug and message.message_type == MessageType.DEBUG:
        return

    plugin = _plugin_lookup(message.unique_id)
    name = plugin._get_display_name()
    color = message_colors[message.message_type]

    # Compose string...
    text = ''
    if enable_debug:
        text += "[%{tagpid} %{pid: <5} %{tagid} %{id:0>3}] "
    text += "%{timespec: <10} %{type: <7} %{name: <15}"

    if message.logfile and message.scheduler:
        # Longest task name is 'refresh'
        text += " [%{message: ^7}] %{logfile}"
    else:
        text += " %{message}"

    if message.detail is not None:
        text += "\n\n%{detail}\n"

    # Are we going to print some log file ?
    if message.scheduler and message.message_type == MessageType.FAIL:
        text = text.rstrip('\n')
        text += "\n\n%{logcontent}\n"

    # Format string...
    if message.message_type in (MessageType.SUCCESS, MessageType.FAIL):
        text = _term.fmt_subst(text, 'timespec',
                               "[{}]".format(utils._format_duration(message.elapsed)),
                               color=Color.CYAN, attrs=[Attr.DARK])
    else:
        text = _term.fmt_subst(text, 'timespec', EMPTYTIME,
                               color=Color.CYAN, attrs=[Attr.DARK])

    # Handle scheduler messages differently
    if message.scheduler:
        text = _term.fmt_subst(text, 'logfile', message.logfile, color=Color.YELLOW, attrs=[Attr.DARK])
        text = _term.fmt_subst(text, 'message', message.message, color=Color.YELLOW, attrs=[Attr.DARK])

        # Dump some log content
        if message.message_type == MessageType.FAIL:
            log_content = read_last_lines(message.logfile, context.log_error_lines)
            text = _term.fmt_subst(text, 'logcontent',
                                   INDENT + INDENT.join(log_content.splitlines(True)),
                                   attrs=[Attr.ITALIC, Attr.DARK])
    else:
        text = _term.fmt_subst(text, 'message', message.message)

    if enable_debug:
        text = _term.fmt_subst(text, 'pid', message.pid, color=Color.YELLOW, attrs=[Attr.DARK])
        text = _term.fmt_subst(text, 'tagpid', 'PID:', color=Color.CYAN, attrs=[Attr.DARK])
        text = _term.fmt_subst(text, 'id', message.unique_id, color=Color.YELLOW, attrs=[Attr.DARK])
        text = _term.fmt_subst(text, 'tagid', 'ID:', color=Color.CYAN, attrs=[Attr.DARK])

    text = _term.fmt_subst(text, 'type', message.message_type.upper(), color=color, attrs=[Attr.BOLD, Attr.DARK])
    text = _term.fmt_subst(text, 'name', '[' + name + ']', color=Color.BLUE, attrs=[Attr.DARK])
    if message.detail is not None:
        detail = message.detail.rstrip('\n')

        color = Color.WHITE
        if message.message_type == MessageType.FAIL:
            color = Color.RED
        text = _term.fmt_subst(text, 'detail',
                               INDENT + INDENT.join((detail.splitlines(True))),
                               color=color, attrs=[Attr.ITALIC, Attr.BOLD, Attr.DARK])
    click.echo(text)


#
# Create a pipeline
#
def create_pipeline(directory, target, arch, variant, config):

    try:
        context = Context(arch)
        context.load(config)
    except _ALL_EXCEPTIONS as e:
        click.echo("Error loading user configuration: %s" % str(e))
        sys.exit(1)

    # Override things in the context from our command line options,
    # the command line when used, trumps the config files.
    #
    if main_options_set.get('debug'):
        context.log_debug = main_options['debug']
    if main_options_set.get('verbose'):
        context.log_verbose = main_options['verbose']
    if main_options_set.get('error_lines'):
        context.log_error_lines = main_options['error_lines']

    # Propagate pipeline feedback to the user
    context._set_message_handler(message_handler)

    try:
        project = Project(directory)
    except _ALL_EXCEPTIONS as e:
        click.echo("Error loading project: %s" % str(e))
        sys.exit(1)

    try:
        pipeline = Pipeline(context, project, target, variant)
    except _ALL_EXCEPTIONS as e:
        click.echo("Error loading pipeline: %s" % str(e))
        sys.exit(1)

    return pipeline
