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
import re
import click
import pkg_resources  # From setuptools
from ruamel import yaml

from . import Context, Project, Scope
from . import LoadError, SourceError, ElementError, PluginError, ProgramNotFoundError
from ._pipeline import Pipeline
from . import _pipeline
from . import utils

# Some nasty globals
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()

main_options = {}


##################################################################
#                          Main Options                          #
##################################################################
@click.group()
@click.version_option(version=build_stream_version)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--verbose', '-v', default=False, is_flag=True,
              help="Whether to be extra verbose")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="Project directory (default: %s)" % os.getcwd())
def cli(config, verbose, directory):
    """Build and manipulate BuildStream projects"""
    main_options['config'] = config
    main_options['verbose'] = verbose
    main_options['directory'] = directory


##################################################################
#                         Refresh Command                        #
##################################################################
@cli.command(short_help="Refresh sources in a pipeline")
@click.option('--list', '-l', default=False, is_flag=True,
              help='List the sources which were refreshed')
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.argument('target')
def refresh(target, arch, variant, list):
    """Refresh sources in a pipeline

    Updates the project with new source references from
    any sources which are configured to track a remote
    branch or tag.
    """
    pipeline = create_pipeline(main_options['directory'], target, arch, variant, main_options['config'])

    try:
        sources = pipeline.refresh()
    except (SourceError, ElementError) as e:
        click.echo("Error refreshing pipeline: %s" % str(e))
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
        line = format_symbol(format, 'name', element.name, color=Color.BLUE, attrs=[Attr.BOLD])
        if element._inconsistent():
            line = format_symbol(line, 'key', "")
            line = format_symbol(line, 'state', "inconsistent", color=Color.RED)
        else:
            line = format_symbol(line, 'key', element._get_cache_key(), color=Color.YELLOW)
            if element._cached():
                line = format_symbol(line, 'state', "cached", color=Color.MAGENTA)
            elif element._buildable():
                line = format_symbol(line, 'state', "buildable", color=Color.GREEN)
            else:
                line = format_symbol(line, 'state', "waiting", color=Color.BLUE)

        # Element configuration
        config = utils._node_sanitize(element._Element__config, ordered=True)
        line = format_symbol(
            line, 'config',
            yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

        # Variables
        variables = utils._node_sanitize(element._Element__variables.variables, ordered=True)
        line = format_symbol(
            line, 'vars',
            yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

        # Environment
        environment = utils._node_sanitize(element._Element__environment, ordered=True)
        line = format_symbol(
            line, 'env',
            yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

        report += line + '\n'

    click.echo(report.rstrip('\n'))


##################################################################
#                        Helper Functions                        #
##################################################################

#
# Create a pipeline
#
def create_pipeline(directory, target, arch, variant, config):

    try:
        context = Context(arch)
        context.load(config)
    except LoadError as e:
        click.echo("Error loading user configuration: %s" % str(e))
        sys.exit(1)

    try:
        project = Project(directory)
    except LoadError as e:
        click.echo("Error loading project: %s" % str(e))
        sys.exit(1)

    try:
        pipeline = Pipeline(context, project, target, variant)
    except (LoadError, PluginError, SourceError, ElementError, ProgramNotFoundError) as e:
        click.echo("Error loading pipeline: %s" % str(e))
        sys.exit(1)

    return pipeline


#
# Text formatting for the console
#
# Note that because we use click, the output we send to the terminal
# with click.echo() will be stripped of ansi control unless displayed
# on the console to the user (there are also some compatibility features
# for text formatting on windows)
#
class Color():
    BLACK = "30"
    RED = "31"
    GREEN = "32"
    YELLOW = "33"
    BLUE = "34"
    MAGENTA = "35"
    CYAN = "36"
    WHITE = "37"


class Attr():
    CLEAR = "0"
    BOLD = "1"
    DARK = "2"
    ITALIC = "3"
    UNDERLINE = "4"
    BLINK = "5"
    REVERSE_VIDEO = "7"
    CONCEALED = "8"


def console_format(text, color=None, attrs=[]):

    if color is None and not attrs:
        return text

    CNTL_START = "\033["
    CNTL_END = "m"
    CNTL_SEPARATOR = ";"

    attr_count = 0

    # Set graphics mode
    new_text = CNTL_START
    for attr in attrs:
        if attr_count > 0:
            new_text += CNTL_SEPARATOR
        new_text += attr
        attr_count += 1

    if color is not None:
        if attr_count > 0:
            new_text += CNTL_SEPARATOR
        new_text += color
        attr_count += 1

    new_text += CNTL_END

    # Add text
    new_text += text

    # Clear graphics mode settings
    new_text += (CNTL_START + Attr.CLEAR + CNTL_END)

    return new_text


# Can be used to format python strings with % prefixed.
#
# This will first center the %{name} in a 20 char width
# and format the %{name} in blue.
#
#    formatted = format_symbol("This is your %{name: ^20}", "name", "Bob", color=Color.BLUE)
#
# We use this because python formatting methods which use
# padding will consider the ansi escape sequences we use.
#
def format_symbol(text, varname, value, color=None, attrs=[]):

    def subst_callback(match):
        # Extract and format the "{(varname)...}" portion of the match
        inner_token = match.group(1)
        formatted = inner_token.format(**{varname: value})

        # Colorize after the pythonic format formatting, which may have padding
        return console_format(formatted, color, attrs)

    # Lazy regex, after our word, match anything that does not have '%'
    return re.sub(r"%(\{(" + varname + r")[^%]*\})", subst_callback, text)
