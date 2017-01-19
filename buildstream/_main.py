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
import subprocess
import copy
from ruamel import yaml

from . import Context, Project, Scope, Consistency
from .exceptions import _ALL_EXCEPTIONS
from .plugin import _plugin_lookup
from ._message import MessageType
from . import _pipeline
from ._pipeline import Pipeline, PipelineError
from . import utils

# Some nasty globals
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()

main_options = {}
main_options_set = {}
main_context = None

longest_plugin_name = 0
longest_plugin_kind = 0
messaging_enabled = False


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
    pipeline = create_pipeline(target, arch, variant)
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
@click.option('--format', '-f', metavar='FORMAT', default="%{name: >20}: %{key: <64} (%{state})",
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
            'Name: %{name: ^20} Key: %{key: ^64} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        build-stream show target.bst --format \\
            $'---------- %{name} ----------\\n%{variables}'
    """
    pipeline = create_pipeline(target, arch, variant)
    report = ''

    if deps is not None:
        scope = deps
        if scope == "all":
            scope = Scope.ALL
        elif scope == "build":
            scope = Scope.BUILD
        else:
            scope = Scope.RUN

        dependencies = pipeline.dependencies(scope)
        if order == "alpha":
            dependencies = sorted(pipeline.dependencies(scope))
    else:
        dependencies = [pipeline.target]

    for element in dependencies:
        line = fmt_subst(format, 'name', element.name, fg='blue', bold=True)
        cache_key = element._get_cache_key()
        if cache_key is None:
            cache_key = ''

        consistency = element._consistency()
        if consistency == Consistency.INCONSISTENT:
            line = fmt_subst(line, 'key', "")
            line = fmt_subst(line, 'state', "no reference", fg='red')
        else:
            line = fmt_subst(line, 'key', cache_key, fg='yellow')
            if element._cached():
                line = fmt_subst(line, 'state', "cached", fg='magenta')
            elif consistency == Consistency.RESOLVED:
                line = fmt_subst(line, 'state', "fetch needed", fg='red')
            elif element._buildable():
                line = fmt_subst(line, 'state', "buildable", fg='green')
            else:
                line = fmt_subst(line, 'state', "waiting", fg='blue')

        # Element configuration
        config = utils._node_sanitize(element._Element__config)
        line = fmt_subst(
            line, 'config',
            yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

        # Variables
        variables = utils._node_sanitize(element._Element__variables.variables)
        line = fmt_subst(
            line, 'vars',
            yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

        # Environment
        environment = utils._node_sanitize(element._Element__environment)
        line = fmt_subst(
            line, 'env',
            yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

        report += line + '\n'

    click.echo(report.rstrip('\n'))


##################################################################
#                          Shell Command                         #
##################################################################
@cli.command(short_help="Shell into a build environment")
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
    """Shell into an environment environment

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
    except PipelineError:
        click.echo("")
        click.echo("Errors shelling into this pipeline")
        sys.exit(1)


##################################################################
#                        Helper Functions                        #
##################################################################


# Basic profiles
class Profile():
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)

    def fmt(self, text, **kwargs):
        kwargs = dict(kwargs)
        fmtargs = copy.copy(self.kwargs)
        fmtargs.update(kwargs)
        return click.style(text, **fmtargs)

    def fmt_subst(self, text, varname, value, **kwargs):

        def subst_callback(match):
            # Extract and format the "{(varname)...}" portion of the match
            inner_token = match.group(1)
            formatted = inner_token.format(**{varname: value})

            # Colorize after the pythonic format formatting, which may have padding
            return self.fmt(formatted, **kwargs)

        # Lazy regex, after our word, match anything that does not have '%'
        return re.sub(r"%(\{(" + varname + r")[^%]*\})", subst_callback, text)


def fmt_subst(text, varname, value, **kwargs):
    return Style.NONE.fmt_subst(text, varname, value, **kwargs)


# Palette of text styles
#
class Style():
    NONE = Profile()

    DEBUG_FG = Profile(fg='yellow')
    DEBUG_BG = Profile(fg='cyan', dim=True)
    TC_FG = Profile(fg='yellow')
    TC_BG = Profile(fg='cyan', dim=True)
    NAME_FG = Profile(fg='yellow')
    NAME_BG = Profile(fg='cyan', dim=True)
    TASK_FG = Profile(fg='yellow')
    TASK_BG = Profile(fg='cyan', dim=True)
    KIND_FG = Profile(fg='yellow')
    KIND_BG = Profile(fg='cyan', dim=True)
    DEPTH = Profile(fg='cyan', dim=True)

    ACTION = Profile(bold=True, dim=True)
    LOG = Profile(fg='yellow', dim=True)
    LOG_ERROR = Profile(fg='red', dim=True)
    DETAIL = Profile(dim=True)
    ERR_HEAD = Profile(fg='red', bold=True, dim=True)
    ERR_BODY = Profile(dim=True)


action_colors = {}
action_colors[MessageType.DEBUG] = "cyan"
action_colors[MessageType.STATUS] = "cyan"
action_colors[MessageType.INFO] = "magenta"
action_colors[MessageType.WARN] = "yellow"
action_colors[MessageType.ERROR] = "red"
action_colors[MessageType.START] = "blue"
action_colors[MessageType.SUCCESS] = "green"
action_colors[MessageType.FAIL] = "red"


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

    # Drop messages by default in the beginning while
    # loading the pipeline, unless debug is specified.
    if not messaging_enabled:
        return

    # The detail indentation
    INDENT = "    "
    EMPTYTIME = "[--:--:--]"

    plugin = None
    if message.unique_id is not None:
        plugin = _plugin_lookup(message.unique_id)
        name = plugin._get_display_name()
    else:
        name = ''

    # Drop status messages from the UI if not verbose, we'll still see
    # info messages and status messages will still go to the log files.
    if not context.log_verbose and message.message_type == MessageType.STATUS:
        return

    # Debug output
    enable_debug = main_options['debug']
    if enable_debug:
        text = "%{debugopen}%{tagpid}%{pid: <5} %{tagid}%{id:0>3}%{debugclose}"
    else:
        text = ''

    # Time code
    text += "%{timespec: <10}"

    # Action name (like track, fetch, build, etc)
    if message.action_name:
        text += "%{openaction}%{actionname: ^5}%{closeaction}"
    else:
        text += "       "

    # The plugin display name, allow for 2 indentations (4 chars) in 'taskdepth'
    kindchars = max(longest_plugin_kind, 8)
    namechars = max(longest_plugin_name, 8) + 4
    namechars = namechars - (message.depth * 2)
    text += "%{openname} %{kindname: >" + str(kindchars) + "}" + \
            "%{kindsep}%{taskdepth}%{name: <" + str(namechars) + "}%{closename}"

    # The message type
    text += " %{type: <7}"

    if message.logfile and message.scheduler:
        text += " %{logfile}"
    else:
        text += " %{message}"

    if message.detail is not None:
        text += "\n\n%{detail}\n"

    # Are we going to print some log file ?
    if message.scheduler and message.message_type == MessageType.FAIL:
        text = text.rstrip('\n')
        text += "\n\n%{logcontent}\n"

    # Format string...
    text = fmt_subst(text, 'timespec', format_duration(message.elapsed))

    # Handle scheduler messages differently
    if message.scheduler:
        text = fmt_subst(
            text, 'message',
            Style.TASK_BG.fmt('[') + Style.TASK_FG.fmt(message.message) + Style.TASK_BG.fmt(']'))
    else:
        text = fmt_subst(text, 'message', message.message)

    if message.action_name:
        text = Style.TASK_BG.fmt_subst(text, 'openaction', '[')
        text = Style.TASK_FG.fmt_subst(text, 'actionname', message.action_name)
        text = Style.TASK_BG.fmt_subst(text, 'closeaction', ']')

    kindname = ''
    if plugin is not None:
        kindname = plugin.get_kind()
    text = Style.KIND_BG.fmt_subst(text, 'kindsep', ':')
    text = Style.TASK_FG.fmt_subst(text, 'kindname', kindname)

    if enable_debug:
        unique_id = 0 if message.unique_id is None else message.unique_id
        text = Style.DEBUG_BG.fmt_subst(text, 'debugopen', '[')
        text = Style.DEBUG_BG.fmt_subst(text, 'tagpid', 'pid:')
        text = Style.DEBUG_FG.fmt_subst(text, 'pid', message.pid)
        text = Style.DEBUG_BG.fmt_subst(text, 'tagid', 'id:')
        text = Style.DEBUG_FG.fmt_subst(text, 'id', unique_id)
        text = Style.DEBUG_BG.fmt_subst(text, 'debugclose', ']')

    text = Style.ACTION.fmt_subst(
        text, 'type', message.message_type.upper(),
        fg=action_colors[message.message_type])

    text = Style.NAME_BG.fmt_subst(text, 'openname', '[')
    text = Style.DEPTH.fmt_subst(text, 'taskdepth', '> ' * message.depth)
    text = Style.NAME_FG.fmt_subst(text, 'name', name)
    text = Style.NAME_BG.fmt_subst(text, 'closename', ']')

    if message.detail is not None:
        detail = message.detail.rstrip('\n')
        detail = INDENT + INDENT.join((detail.splitlines(True)))
        if message.message_type == MessageType.FAIL:
            text = Style.ERR_HEAD.fmt_subst(text, 'detail', detail)
        else:
            text = Style.DETAIL.fmt_subst(text, 'detail', detail)

    # Log content needs to be formatted last, as it may introduce symbols
    # which match our regex
    if message.scheduler:
        if message.message_type == MessageType.FAIL:
            text = Style.LOG_ERROR.fmt_subst(text, 'logfile', message.logfile)
            log_content = read_last_lines(message.logfile, context.log_error_lines)
            text = Style.ERR_BODY.fmt_subst(
                text, 'logcontent',
                INDENT + INDENT.join(log_content.splitlines(True)))
        else:
            text = Style.LOG.fmt_subst(text, 'logfile', message.logfile)

    click.echo(text)


# Formats a pretty [00:00:00] duration
#
def format_duration(elapsed):

    if elapsed is None:
        fields = [Style.TC_BG.fmt('--') for i in range(3)]
    else:
        hours, remainder = divmod(int(elapsed.total_seconds()), 60 * 60)
        minutes, seconds = divmod(remainder, 60)
        fields = [
            Style.TC_FG.fmt("{0:02d}".format(field))
            for field in [hours, minutes, seconds]
        ]

    return Style.TC_BG.fmt('[') + \
        Style.TC_BG.fmt(':').join(fields) + \
        Style.TC_BG.fmt(']')


#
# Create a pipeline
#
def create_pipeline(target, arch, variant):
    global longest_plugin_name
    global longest_plugin_kind
    global messaging_enabled

    directory = main_options['directory']
    config = main_options['config']

    try:
        context = Context(arch)
        context.load(config)
    except _ALL_EXCEPTIONS as e:
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

    # Get the longest element name for logging purposes
    longest_plugin_name = 0
    longest_plugin_kind = 0
    for plugin in pipeline.dependencies(Scope.ALL, include_sources=True):
        longest_plugin_name = max(len(plugin._get_display_name()), longest_plugin_name)
        longest_plugin_kind = max(len(plugin.get_kind()), longest_plugin_kind)

    # Pipeline is loaded, lets start displaying pipeline messages from tasks
    messaging_enabled = True

    return pipeline
