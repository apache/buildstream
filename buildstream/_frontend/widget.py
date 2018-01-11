#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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
import datetime
import os
from collections import OrderedDict
from contextlib import ExitStack
from mmap import mmap

import click
import pkg_resources
from ruamel import yaml

from . import Profile
from .. import Element, Scope, Consistency
from .. import _yaml
from .._exceptions import ImplError
from .._message import MessageType
from ..plugin import _plugin_lookup


# Widget()
#
# Args:
#    content_profile (Profile): The profile to use for rendering content
#    format_profile (Profile): The profile to use for rendering formatting
#
# An abstract class for printing output columns in our text UI.
#
class Widget():

    def __init__(self, content_profile, format_profile):

        # The content profile
        self.content_profile = content_profile

        # The formatting profile
        self.format_profile = format_profile

    # size_request()
    #
    # Gives the widget a chance to preflight the pipeline
    # and figure out what size it might need for alignment purposes
    #
    # Args:
    #    pipeline (Pipeline): The pipeline to process
    #
    def size_request(self, pipeline):
        pass

    # render()
    #
    # Renders a string to be printed in the UI
    #
    # Args:
    #    message (Message): A message to print
    #
    # Returns:
    #    (str): The string this widget prints for the given message
    #
    def render(self, message):
        raise ImplError("{} does not implement render()".format(type(self).__name__))


# Used to add spacing between columns
class Space(Widget):

    def render(self, message):
        return ' '


# A widget for rendering the debugging column
class Debug(Widget):

    def render(self, message):
        unique_id = 0 if message.unique_id is None else message.unique_id

        text = self.format_profile.fmt('[pid:')
        text += self.content_profile.fmt("{: <5}".format(message.pid))
        text += self.format_profile.fmt(" id:")
        text += self.content_profile.fmt("{:0>3}".format(unique_id))
        text += self.format_profile.fmt(']')

        return text


# A widget for rendering the time codes
class TimeCode(Widget):

    def __init__(self, content_profile, format_profile, brackets=True):
        self.brackets = brackets
        super(TimeCode, self).__init__(content_profile, format_profile)

    def render(self, message):
        return self.render_time(message.elapsed)

    def render_time(self, elapsed):
        if elapsed is None:
            fields = [
                self.content_profile.fmt('--')
                for i in range(3)
            ]
        else:
            hours, remainder = divmod(int(elapsed.total_seconds()), 60 * 60)
            minutes, seconds = divmod(remainder, 60)
            fields = [
                self.content_profile.fmt("{0:02d}".format(field))
                for field in [hours, minutes, seconds]
            ]

        text = ''
        if self.brackets:
            text += self.format_profile.fmt('[')

        text += self.format_profile.fmt(':').join(fields)
        if self.brackets:
            text += self.format_profile.fmt(']')

        return text


# A widget for rendering the MessageType
class TypeName(Widget):

    action_colors = {
        MessageType.DEBUG: "cyan",
        MessageType.STATUS: "cyan",
        MessageType.INFO: "magenta",
        MessageType.WARN: "yellow",
        MessageType.START: "blue",
        MessageType.SUCCESS: "green",
        MessageType.FAIL: "red",
        MessageType.BUG: "red",
    }

    def render(self, message):
        return self.content_profile.fmt("{: <7}"
                                        .format(message.message_type.upper()),
                                        bold=True, dim=True,
                                        fg=self.action_colors[message.message_type])


# A widget for displaying the Element name
class ElementName(Widget):

    def __init__(self, content_profile, format_profile):
        super(ElementName, self).__init__(content_profile, format_profile)

        # Pre initialization format string, before we know the length of
        # element names in the pipeline
        self.fmt_string = '{: <30}'

    def size_request(self, pipeline):
        longest_name = 0
        for plugin in pipeline.dependencies(Scope.ALL, include_sources=True):
            longest_name = max(len(plugin.name), longest_name)

        # Put a cap at a specific width, usually some elements cause the line
        # to be too long, just live with the unaligned columns in that case
        longest_name = min(longest_name, 30)
        self.fmt_string = '{: <' + str(longest_name) + '}'

    def render(self, message):
        element_id = message.task_id or message.unique_id
        if element_id is None:
            return ""

        plugin = _plugin_lookup(element_id)
        name = plugin.name

        # Sneak the action name in with the element name
        action_name = message.action_name
        if not action_name:
            action_name = "Main"

        return self.format_profile.fmt('[') + \
            self.content_profile.fmt("{: >5}".format(action_name.lower())) + \
            self.format_profile.fmt(':') + \
            self.content_profile.fmt(self.fmt_string.format(name)) + \
            self.format_profile.fmt(']')


# A widget for displaying the primary message text
class MessageText(Widget):

    def render(self, message):

        return message.message


# A widget for formatting the element cache key
class CacheKey(Widget):

    def __init__(self, content_profile, format_profile, err_profile):
        super(CacheKey, self).__init__(content_profile, format_profile)

        self.err_profile = err_profile
        self.key_length = 0

    def size_request(self, pipeline):
        self.key_length = pipeline.context.log_key_length

    def render(self, message):

        element_id = message.task_id or message.unique_id
        if element_id is None or not self.key_length:
            return ""

        missing = False
        key = ' ' * self.key_length
        plugin = _plugin_lookup(element_id)
        if isinstance(plugin, Element):
            _, key, missing = plugin._get_full_display_key()

        if message.message_type in [MessageType.FAIL, MessageType.BUG]:
            text = self.err_profile.fmt(key)
        else:
            text = self.content_profile.fmt(key, dim=missing)

        return self.format_profile.fmt('[') + text + self.format_profile.fmt(']')


# A widget for formatting the log file
class LogFile(Widget):

    def __init__(self, content_profile, format_profile, err_profile):
        super(LogFile, self).__init__(content_profile, format_profile)

        self.err_profile = err_profile
        self.logdir = ''

    def size_request(self, pipeline):

        # Hold on to the logging directory so we can abbreviate
        self.logdir = pipeline.context.logdir

    def render(self, message, abbrev=True):

        if message.logfile and message.scheduler:
            logfile = message.logfile

            if logfile.startswith(self.logdir) and abbrev:
                logfile = logfile[len(self.logdir) + 1:]

            if message.message_type in [MessageType.FAIL, MessageType.BUG]:
                text = self.err_profile.fmt(logfile)
            else:
                text = self.content_profile.fmt(logfile, dim=True)
        else:
            text = ''

        return text


# A widget for formatting a log line
class LogLine(Widget):

    def __init__(self, content_profile, format_profile, success_profile, err_profile, detail_profile,
                 indent=4,
                 log_lines=10,
                 message_lines=10,
                 debug=False):
        super(LogLine, self).__init__(content_profile, format_profile)

        self.columns = []
        self.success_profile = success_profile
        self.err_profile = err_profile
        self.detail_profile = detail_profile
        self.indent = ' ' * indent
        self.log_lines = log_lines
        self.message_lines = message_lines

        self.space_widget = Space(content_profile, format_profile)
        self.message_widget = MessageText(content_profile, format_profile)
        self.logfile_widget = LogFile(content_profile, format_profile, err_profile)

        if debug:
            self.columns.extend([
                Debug(content_profile, format_profile)
            ])

        self.columns.extend([
            TimeCode(content_profile, format_profile),
            CacheKey(content_profile, format_profile, err_profile),
            ElementName(content_profile, format_profile),
            self.space_widget,
            TypeName(content_profile, format_profile),
            self.space_widget
        ])

    def size_request(self, pipeline):
        for widget in self.columns:
            widget.size_request(pipeline)

        self.space_widget.size_request(pipeline)
        self.message_widget.size_request(pipeline)
        self.logfile_widget.size_request(pipeline)

    def render(self, message):

        # Render the column widgets first
        text = ''
        for widget in self.columns:
            text += widget.render(message)

        # Show the log file only in the main start/success messages
        if message.logfile and message.scheduler and \
           message.message_type in [MessageType.START, MessageType.SUCCESS]:
            text += self.logfile_widget.render(message)
        else:
            text += self.message_widget.render(message)

        text += '\n'

        extra_nl = False

        # Now add some custom things
        if message.detail is not None:

            # Split and truncate message detail down to message_lines lines
            lines = message.detail.splitlines(True)

            n_lines = len(lines)
            abbrev = False
            if message.message_type not in [MessageType.FAIL, MessageType.BUG] \
               and n_lines > self.message_lines:
                abbrev = True
                lines = lines[0:self.message_lines]
            else:
                lines[n_lines - 1] = lines[n_lines - 1].rstrip('\n')

            detail = self.indent + self.indent.join(lines)

            text += '\n'
            if message.message_type in [MessageType.FAIL, MessageType.BUG]:
                text += self.err_profile.fmt(detail, bold=True)
            else:
                text += self.detail_profile.fmt(detail)

            if abbrev:
                text += self.indent + \
                    self.content_profile.fmt('Message contains {} additional lines'
                                             .format(n_lines - self.message_lines), dim=True)
            text += '\n'

            extra_nl = True

        if message.sandbox is not None:
            sandbox = self.indent + 'Sandbox directory: ' + message.sandbox

            text += '\n'
            if message.message_type == MessageType.FAIL:
                text += self.err_profile.fmt(sandbox, bold=True)
            else:
                text += self.detail_profile.fmt(sandbox)
            text += '\n'
            extra_nl = True

        if message.scheduler and message.message_type == MessageType.FAIL:
            text += '\n'
            text += self.indent + self.err_profile.fmt("Printing the last {} lines from log file:"
                                                       .format(self.log_lines)) + '\n'
            text += self.indent + self.logfile_widget.render(message, abbrev=False) + '\n'
            text += self.indent + self.err_profile.fmt("=" * 70) + '\n'

            log_content = self.read_last_lines(message.logfile)
            log_content = self.indent + self.indent.join(log_content.splitlines(True))
            text += self.detail_profile.fmt(log_content)
            text += '\n'
            text += self.indent + self.err_profile.fmt("=" * 70) + '\n'
            extra_nl = True

        if extra_nl:
            text += '\n'

        return text

    def read_last_lines(self, logfile):
        with ExitStack() as stack:
            # mmap handles low-level memory details, allowing for
            # faster searches
            f = stack.enter_context(open(logfile, 'r+'))
            log = stack.enter_context(mmap(f.fileno(), os.path.getsize(f.name)))

            count = 0
            end = log.size() - 1

            while count < self.log_lines and end >= 0:
                location = log.rfind(b'\n', 0, end)
                count += 1

                # If location is -1 (none found), this will print the
                # first character because of the later +1
                end = location

            # end+1 is correct whether or not a newline was found at
            # that location. If end is -1 (seek before beginning of file)
            # then we get the first characther. If end is a newline position,
            # we discard it and only want to print the beginning of the next
            # line.
            lines = log[(end + 1):].splitlines()
            return '\n'.join([line.decode('utf-8') for line in lines]).rstrip()

    #
    # A message to be printed at program startup, indicating
    # some things about user configuration and BuildStream version
    # and so on.
    #
    # Args:
    #    pipeline (Pipeline): The pipeline to print the heading of
    #    log_file (file): An optional file handle for additional logging
    #    deps (list): Optional list of elements, default is to use the whole pipeline
    #    styling (bool): Whether to enable ansi escape codes in the output
    #
    def print_heading(self, pipeline, log_file, deps=None, styling=False):
        context = pipeline.context
        project = pipeline.project
        starttime = datetime.datetime.now()
        bst = pkg_resources.require("buildstream")[0]
        text = ''

        # Main invocation context
        text += '\n'
        text += self.content_profile.fmt("BuildStream Version {}\n".format(bst.version), bold=True)
        values = OrderedDict()
        values["Session Start"] = starttime.strftime('%A, %d-%m-%Y at %H:%M:%S')
        values["Project"] = "{} ({})".format(project.name, project.directory)
        values["Targets"] = ", ".join([t.name for t in pipeline.targets])
        text += self.format_values(values)

        # User configurations
        text += '\n'
        text += self.content_profile.fmt("User Configuration\n", bold=True)
        values = OrderedDict()
        values["Configuration File"] = \
            "Default Configuration" if not context.config_origin else context.config_origin
        values["Log Files"] = context.logdir
        values["Source Mirrors"] = context.sourcedir
        values["Build Area"] = context.builddir
        values["Artifact Cache"] = context.artifactdir
        values["Maximum Fetch Tasks"] = context.sched_fetchers
        values["Maximum Build Tasks"] = context.sched_builders
        values["Maximum Push Tasks"] = context.sched_pushers
        values["Maximum Network Retries"] = context.sched_network_retries
        text += self.format_values(values)
        text += '\n'

        # Project Options
        if len(project._options.variables) > 0:
            text += self.content_profile.fmt("Project Options\n", bold=True)
            values = OrderedDict()
            for key in sorted(project._options.variables):
                values[key] = project._options.variables[key]
            text += self.format_values(values)
            text += '\n'

        # Plugins
        text += self.format_plugins(pipeline.element_factory.loaded_dependencies,
                                    pipeline.source_factory.loaded_dependencies)

        # Pipeline state
        text += self.content_profile.fmt("Pipeline\n", bold=True)
        if deps is None:
            deps = pipeline.dependencies(Scope.ALL)
        text += self.show_pipeline(deps, context.log_element_format)
        text += '\n'

        # Separator line before following output
        text += self.format_profile.fmt("~" * 79 + '\n')

        click.echo(text, color=styling, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    # Print queue summaries at the end of a scheduler run
    #
    def print_summary(self, pipeline, scheduler, log_file, styling=False):

        # Early silent return if there are no queues, can happen
        # only in the case that the pipeline early returned due to
        # an inconsistent pipeline state.
        if scheduler.queues is None:
            return

        text = self.content_profile.fmt("Pipeline Summary\n", bold=True)
        values = OrderedDict()
        values['Total'] = self.content_profile.fmt(str(pipeline.total_elements))
        values['Session'] = self.content_profile.fmt(str(pipeline.session_elements))

        processed_maxlen = 1
        skipped_maxlen = 1
        failed_maxlen = 1
        for queue in scheduler.queues:
            processed_maxlen = max(len(str(len(queue.processed_elements))), processed_maxlen)
            skipped_maxlen = max(len(str(len(queue.skipped_elements))), skipped_maxlen)
            failed_maxlen = max(len(str(len(queue.failed_elements))), failed_maxlen)

        for queue in scheduler.queues:
            processed = str(len(queue.processed_elements))
            skipped = str(len(queue.skipped_elements))
            failed = str(len(queue.failed_elements))

            processed_align = ' ' * (processed_maxlen - len(processed))
            skipped_align = ' ' * (skipped_maxlen - len(skipped))
            failed_align = ' ' * (failed_maxlen - len(failed))

            status_text = self.content_profile.fmt("processed ") + \
                self.success_profile.fmt(processed) + \
                self.format_profile.fmt(', ') + processed_align

            status_text += self.content_profile.fmt("skipped ") + \
                self.content_profile.fmt(skipped) + \
                self.format_profile.fmt(', ') + skipped_align

            status_text += self.content_profile.fmt("failed ") + \
                self.err_profile.fmt(failed) + ' ' + failed_align
            values["{} Queue".format(queue.action_name)] = status_text

        text += self.format_values(values, style_value=False)

        click.echo(text, color=styling, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    def format_plugins(self, element_plugins, source_plugins):
        text = ""

        if not (element_plugins or source_plugins):
            return text

        text += self.content_profile.fmt("Loaded Plugins\n", bold=True)

        if element_plugins:
            text += self.format_profile.fmt("  Element Plugins\n")
            for plugin in element_plugins:
                text += self.content_profile.fmt("    - {}\n".format(plugin))

        if source_plugins:
            text += self.format_profile.fmt("  Source Plugins\n")
            for plugin in source_plugins:
                text += self.content_profile.fmt("    - {}\n".format(plugin))

        text += '\n'

        return text

    def format_values(self, values, style_value=True):
        text = ''
        max_key_len = 0
        for key, value in values.items():
            max_key_len = max(len(key), max_key_len)

        for key, value in values.items():
            text += self.format_profile.fmt("  {}: {}".format(key, ' ' * (max_key_len - len(key))))
            if style_value:
                text += self.content_profile.fmt(str(value))
            else:
                text += str(value)
            text += '\n'

        return text

    def show_pipeline(self, dependencies, format):
        report = ''
        p = Profile()

        for element in dependencies:
            line = format

            full_key, cache_key, dim_keys = element._get_full_display_key()

            line = p.fmt_subst(line, 'name', element.name, fg='blue', bold=True)
            line = p.fmt_subst(line, 'key', cache_key, fg='yellow', dim=dim_keys)
            line = p.fmt_subst(line, 'full-key', full_key, fg='yellow', dim=dim_keys)

            consistency = element._consistency()
            if consistency == Consistency.INCONSISTENT:
                line = p.fmt_subst(line, 'state', "no reference", fg='red')
            else:
                if element._cached():
                    line = p.fmt_subst(line, 'state', "cached", fg='magenta')
                elif element._remotely_cached():
                    line = p.fmt_subst(line, 'state', "downloadable", fg='cyan')
                elif consistency == Consistency.RESOLVED:
                    line = p.fmt_subst(line, 'state', "fetch needed", fg='red')
                elif element._buildable():
                    line = p.fmt_subst(line, 'state', "buildable", fg='green')
                else:
                    line = p.fmt_subst(line, 'state', "waiting", fg='blue')

            # Element configuration
            if "%{config" in format:
                config = _yaml.node_sanitize(element._Element__config)
                line = p.fmt_subst(
                    line, 'config',
                    yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

            # Variables
            if "%{vars" in format:
                variables = _yaml.node_sanitize(element._Element__variables.variables)
                line = p.fmt_subst(
                    line, 'vars',
                    yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

            # Environment
            if "%{env" in format:
                environment = _yaml.node_sanitize(element._Element__environment)
                line = p.fmt_subst(
                    line, 'env',
                    yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

            # Public
            if "%{public" in format:
                environment = _yaml.node_sanitize(element._Element__public)
                line = p.fmt_subst(
                    line, 'public',
                    yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

            # Workspaced
            if "%{workspaced" in format:
                line = p.fmt_subst(
                    line, 'workspaced',
                    '(workspaced)' if element._workspaced() else '', fg='yellow')

            # Workspace-dirs
            if "%{workspace-dirs" in format:
                dirs = [path.replace(os.getenv('HOME', '/root'), '~')
                        for path in element._workspace_dirs()]
                if len(dirs) > 0:
                    line = p.fmt_subst(
                        line, 'workspace-dirs', "Workspaces: " + ", ".join(dirs))
                else:
                    line = p.fmt_subst(
                        line, 'workspace-dirs', '')

            report += line + '\n'

        return report.rstrip('\n')
