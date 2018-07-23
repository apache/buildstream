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
from collections import defaultdict, OrderedDict
from contextlib import ExitStack
from mmap import mmap
import re
import textwrap
import click
from ruamel import yaml

from . import Profile
from .. import Element, Consistency
from .. import _yaml
from .. import __version__ as bst_version
from .._exceptions import ImplError
from .._message import MessageType
from ..plugin import _plugin_lookup


# These messages are printed a bit differently
ERROR_MESSAGES = [MessageType.FAIL, MessageType.ERROR, MessageType.BUG]


# Widget()
#
# Args:
#    content_profile (Profile): The profile to use for rendering content
#    format_profile (Profile): The profile to use for rendering formatting
#
# An abstract class for printing output columns in our text UI.
#
class Widget():

    def __init__(self, context, content_profile, format_profile):

        # The context
        self.context = context

        # The content profile
        self.content_profile = content_profile

        # The formatting profile
        self.format_profile = format_profile

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


# Used to add fixed text between columns
class FixedText(Widget):

    def __init__(self, context, text, content_profile, format_profile):
        super(FixedText, self).__init__(context, content_profile, format_profile)
        self.text = text

    def render(self, message):
        return self.format_profile.fmt(self.text)


# Used to add the wallclock time this message was created at
class WallclockTime(Widget):
    def render(self, message):
        fields = [self.content_profile.fmt("{:02d}".format(x)) for x in
                  [message.creation_time.hour,
                   message.creation_time.minute,
                   message.creation_time.second]]
        return self.format_profile.fmt(":").join(fields)


# A widget for rendering the debugging column
class Debug(Widget):

    def render(self, message):
        unique_id = 0 if message.unique_id is None else message.unique_id

        text = self.format_profile.fmt('pid:')
        text += self.content_profile.fmt("{: <5}".format(message.pid))
        text += self.format_profile.fmt(" id:")
        text += self.content_profile.fmt("{:0>3}".format(unique_id))

        return text


# A widget for rendering the time codes
class TimeCode(Widget):
    def __init__(self, context, content_profile, format_profile, microseconds=False):
        self._microseconds = microseconds
        super(TimeCode, self).__init__(context, content_profile, format_profile)

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

        text = self.format_profile.fmt(':').join(fields)

        if self._microseconds:
            if elapsed is not None:
                text += self.content_profile.fmt(".{0:06d}".format(elapsed.microseconds))
            else:
                text += self.content_profile.fmt(".------")
        return text


# A widget for rendering the MessageType
class TypeName(Widget):

    _action_colors = {
        MessageType.DEBUG: "cyan",
        MessageType.STATUS: "cyan",
        MessageType.INFO: "magenta",
        MessageType.WARN: "yellow",
        MessageType.START: "blue",
        MessageType.SUCCESS: "green",
        MessageType.FAIL: "red",
        MessageType.SKIPPED: "yellow",
        MessageType.ERROR: "red",
        MessageType.BUG: "red",
    }

    def render(self, message):
        return self.content_profile.fmt("{: <7}"
                                        .format(message.message_type.upper()),
                                        bold=True, dim=True,
                                        fg=self._action_colors[message.message_type])


# A widget for displaying the Element name
class ElementName(Widget):

    def __init__(self, context, content_profile, format_profile):
        super(ElementName, self).__init__(context, content_profile, format_profile)

        # Pre initialization format string, before we know the length of
        # element names in the pipeline
        self._fmt_string = '{: <30}'

    def render(self, message):
        element_id = message.task_id or message.unique_id
        if element_id is None:
            return ""

        plugin = _plugin_lookup(element_id)
        name = plugin._get_full_name()

        # Sneak the action name in with the element name
        action_name = message.action_name
        if not action_name:
            action_name = "Main"

        return self.content_profile.fmt("{: >5}".format(action_name.lower())) + \
            self.format_profile.fmt(':') + \
            self.content_profile.fmt(self._fmt_string.format(name))


# A widget for displaying the primary message text
class MessageText(Widget):

    def render(self, message):
        return message.message


# A widget for formatting the element cache key
class CacheKey(Widget):

    def __init__(self, context, content_profile, format_profile, err_profile):
        super(CacheKey, self).__init__(context, content_profile, format_profile)

        self._err_profile = err_profile
        self._key_length = context.log_key_length

    def render(self, message):

        element_id = message.task_id or message.unique_id
        if element_id is None or not self._key_length:
            return ""

        missing = False
        key = ' ' * self._key_length
        plugin = _plugin_lookup(element_id)
        if isinstance(plugin, Element):
            _, key, missing = plugin._get_display_key()

        if message.message_type in ERROR_MESSAGES:
            text = self._err_profile.fmt(key)
        else:
            text = self.content_profile.fmt(key, dim=missing)

        return text


# A widget for formatting the log file
class LogFile(Widget):

    def __init__(self, context, content_profile, format_profile, err_profile):
        super(LogFile, self).__init__(context, content_profile, format_profile)

        self._err_profile = err_profile
        self._logdir = context.logdir

    def render(self, message, abbrev=True):

        if message.logfile and message.scheduler:
            logfile = message.logfile

            if abbrev and self._logdir != "" and logfile.startswith(self._logdir):
                logfile = logfile[len(self._logdir):]
                logfile = logfile.lstrip(os.sep)

            if message.message_type in ERROR_MESSAGES:
                text = self._err_profile.fmt(logfile)
            else:
                text = self.content_profile.fmt(logfile, dim=True)
        else:
            text = ''

        return text


# START and SUCCESS messages are expected to have no useful
# information in the message text, so we display the logfile name for
# these messages, and the message text for other types.
#
class MessageOrLogFile(Widget):
    def __init__(self, context, content_profile, format_profile, err_profile):
        super(MessageOrLogFile, self).__init__(context, content_profile, format_profile)
        self._message_widget = MessageText(context, content_profile, format_profile)
        self._logfile_widget = LogFile(context, content_profile, format_profile, err_profile)

    def render(self, message):
        # Show the log file only in the main start/success messages
        if message.logfile and message.scheduler and \
           message.message_type in [MessageType.START, MessageType.SUCCESS]:
            text = self._logfile_widget.render(message)
        else:
            text = self._message_widget.render(message)
        return text


# LogLine
#
# A widget for formatting a log line
#
# Args:
#    context (Context): The Context
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#    success_profile (Profile): Formatting profile for success text
#    error_profile (Profile): Formatting profile for error text
#    detail_profile (Profile): Formatting profile for detail text
#    indent (int): Number of spaces to use for general indentation
#
class LogLine(Widget):

    def __init__(self, context,
                 content_profile,
                 format_profile,
                 success_profile,
                 err_profile,
                 detail_profile,
                 indent=4):
        super(LogLine, self).__init__(context, content_profile, format_profile)

        self._columns = []
        self._failure_messages = defaultdict(list)
        self._success_profile = success_profile
        self._err_profile = err_profile
        self._detail_profile = detail_profile
        self._indent = ' ' * indent
        self._log_lines = context.log_error_lines
        self._message_lines = context.log_message_lines
        self._resolved_keys = None

        self._space_widget = Space(context, content_profile, format_profile)
        self._logfile_widget = LogFile(context, content_profile, format_profile, err_profile)

        if context.log_debug:
            self._columns.extend([
                Debug(context, content_profile, format_profile)
            ])

        self.logfile_variable_names = {
            "elapsed": TimeCode(context, content_profile, format_profile, microseconds=False),
            "elapsed-us": TimeCode(context, content_profile, format_profile, microseconds=True),
            "wallclock": WallclockTime(context, content_profile, format_profile),
            "key": CacheKey(context, content_profile, format_profile, err_profile),
            "element": ElementName(context, content_profile, format_profile),
            "action": TypeName(context, content_profile, format_profile),
            "message": MessageOrLogFile(context, content_profile, format_profile, err_profile)
        }
        logfile_tokens = self._parse_logfile_format(context.log_message_format, content_profile, format_profile)
        self._columns.extend(logfile_tokens)

    # show_pipeline()
    #
    # Display a list of elements in the specified format.
    #
    # The formatting string is the one currently documented in `bst show`, this
    # is used in pipeline session headings and also to implement `bst show`.
    #
    # Args:
    #    dependencies (list of Element): A list of Element objects
    #    format_: A formatting string, as specified by `bst show`
    #
    # Returns:
    #    (str): The formatted list of elements
    #
    def show_pipeline(self, dependencies, format_):
        report = ''
        p = Profile()

        for element in dependencies:
            line = format_

            full_key, cache_key, dim_keys = element._get_display_key()

            line = p.fmt_subst(line, 'name', element._get_full_name(), fg='blue', bold=True)
            line = p.fmt_subst(line, 'key', cache_key, fg='yellow', dim=dim_keys)
            line = p.fmt_subst(line, 'full-key', full_key, fg='yellow', dim=dim_keys)

            consistency = element._get_consistency()
            if consistency == Consistency.INCONSISTENT:
                line = p.fmt_subst(line, 'state', "no reference", fg='red')
            else:
                if element._cached():
                    line = p.fmt_subst(line, 'state', "cached", fg='magenta')
                elif consistency == Consistency.RESOLVED:
                    line = p.fmt_subst(line, 'state', "fetch needed", fg='red')
                elif element._buildable():
                    line = p.fmt_subst(line, 'state', "buildable", fg='green')
                else:
                    line = p.fmt_subst(line, 'state', "waiting", fg='blue')

            # Element configuration
            if "%{config" in format_:
                config = _yaml.node_sanitize(element._Element__config)
                line = p.fmt_subst(
                    line, 'config',
                    yaml.round_trip_dump(config, default_flow_style=False, allow_unicode=True))

            # Variables
            if "%{vars" in format_:
                variables = _yaml.node_sanitize(element._Element__variables.variables)
                line = p.fmt_subst(
                    line, 'vars',
                    yaml.round_trip_dump(variables, default_flow_style=False, allow_unicode=True))

            # Environment
            if "%{env" in format_:
                environment = _yaml.node_sanitize(element._Element__environment)
                line = p.fmt_subst(
                    line, 'env',
                    yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

            # Public
            if "%{public" in format_:
                environment = _yaml.node_sanitize(element._Element__public)
                line = p.fmt_subst(
                    line, 'public',
                    yaml.round_trip_dump(environment, default_flow_style=False, allow_unicode=True))

            # Workspaced
            if "%{workspaced" in format_:
                line = p.fmt_subst(
                    line, 'workspaced',
                    '(workspaced)' if element._get_workspace() else '', fg='yellow')

            # Workspace-dirs
            if "%{workspace-dirs" in format_:
                workspace = element._get_workspace()
                if workspace is not None:
                    path = workspace.path.replace(os.getenv('HOME', '/root'), '~')
                    line = p.fmt_subst(line, 'workspace-dirs', "Workspace: {}".format(path))
                else:
                    line = p.fmt_subst(
                        line, 'workspace-dirs', '')

            report += line + '\n'

        return report.rstrip('\n')

    # print_heading()
    #
    # A message to be printed at program startup, indicating
    # some things about user configuration and BuildStream version
    # and so on.
    #
    # Args:
    #    project (Project): The toplevel project we were invoked from
    #    stream (Stream): The stream
    #    log_file (file): An optional file handle for additional logging
    #    styling (bool): Whether to enable ansi escape codes in the output
    #
    def print_heading(self, project, stream, *, log_file, styling=False):
        context = self.context
        starttime = datetime.datetime.now()
        text = ''

        self._resolved_keys = {element: element._get_cache_key() for element in stream.session_elements}

        # Main invocation context
        text += '\n'
        text += self.content_profile.fmt("BuildStream Version {}\n".format(bst_version), bold=True)
        values = OrderedDict()
        values["Session Start"] = starttime.strftime('%A, %d-%m-%Y at %H:%M:%S')
        values["Project"] = "{} ({})".format(project.name, project.directory)
        values["Targets"] = ", ".join([t.name for t in stream.targets])
        text += self._format_values(values)

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
        values["Strict Build Plan"] = "Yes" if context.get_strict() else "No"
        values["Maximum Fetch Tasks"] = context.sched_fetchers
        values["Maximum Build Tasks"] = context.sched_builders
        values["Maximum Push Tasks"] = context.sched_pushers
        values["Maximum Network Retries"] = context.sched_network_retries
        text += self._format_values(values)
        text += '\n'

        # Project Options
        values = OrderedDict()
        project.options.printable_variables(values)
        if values:
            text += self.content_profile.fmt("Project Options\n", bold=True)
            text += self._format_values(values)
            text += '\n'

        # Plugins
        text += self._format_plugins(project.first_pass_config.element_factory.loaded_dependencies,
                                     project.first_pass_config.source_factory.loaded_dependencies)
        if project.config.element_factory and project.config.source_factory:
            text += self._format_plugins(project.config.element_factory.loaded_dependencies,
                                         project.config.source_factory.loaded_dependencies)

        # Pipeline state
        text += self.content_profile.fmt("Pipeline\n", bold=True)
        text += self.show_pipeline(stream.total_elements, context.log_element_format)
        text += '\n'

        # Separator line before following output
        text += self.format_profile.fmt("=" * 79 + '\n')

        click.echo(text, color=styling, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    # print_summary()
    #
    # Print a summary of activities at the end of a session
    #
    # Args:
    #    stream (Stream): The Stream
    #    log_file (file): An optional file handle for additional logging
    #    styling (bool): Whether to enable ansi escape codes in the output
    #
    def print_summary(self, stream, log_file, styling=False):

        # Early silent return if there are no queues, can happen
        # only in the case that the stream early returned due to
        # an inconsistent pipeline state.
        if not stream.queues:
            return

        text = ''

        assert self._resolved_keys is not None
        elements = sorted(e for (e, k) in self._resolved_keys.items() if k != e._get_cache_key())
        if elements:
            text += self.content_profile.fmt("Resolved key Summary\n", bold=True)
            text += self.show_pipeline(elements, self.context.log_element_format)
            text += "\n\n"

        if self._failure_messages:
            values = OrderedDict()

            for element, messages in sorted(self._failure_messages.items(), key=lambda x: x[0].name):
                for queue in stream.queues:
                    if any(el.name == element.name for el in queue.failed_elements):
                        values[element.name] = ''.join(self._render(v) for v in messages)
            if values:
                text += self.content_profile.fmt("Failure Summary\n", bold=True)
                text += self._format_values(values, style_value=False)

        text += self.content_profile.fmt("Pipeline Summary\n", bold=True)
        values = OrderedDict()

        values['Total'] = self.content_profile.fmt(str(len(stream.total_elements)))
        values['Session'] = self.content_profile.fmt(str(len(stream.session_elements)))

        processed_maxlen = 1
        skipped_maxlen = 1
        failed_maxlen = 1
        for queue in stream.queues:
            processed_maxlen = max(len(str(len(queue.processed_elements))), processed_maxlen)
            skipped_maxlen = max(len(str(len(queue.skipped_elements))), skipped_maxlen)
            failed_maxlen = max(len(str(len(queue.failed_elements))), failed_maxlen)

        for queue in stream.queues:
            processed = str(len(queue.processed_elements))
            skipped = str(len(queue.skipped_elements))
            failed = str(len(queue.failed_elements))

            processed_align = ' ' * (processed_maxlen - len(processed))
            skipped_align = ' ' * (skipped_maxlen - len(skipped))
            failed_align = ' ' * (failed_maxlen - len(failed))

            status_text = self.content_profile.fmt("processed ") + \
                self._success_profile.fmt(processed) + \
                self.format_profile.fmt(', ') + processed_align

            status_text += self.content_profile.fmt("skipped ") + \
                self.content_profile.fmt(skipped) + \
                self.format_profile.fmt(', ') + skipped_align

            status_text += self.content_profile.fmt("failed ") + \
                self._err_profile.fmt(failed) + ' ' + failed_align
            values["{} Queue".format(queue.action_name)] = status_text

        text += self._format_values(values, style_value=False)

        click.echo(text, color=styling, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    ###################################################
    #             Widget Abstract Methods             #
    ###################################################

    def render(self, message):

        # Track logfiles for later use
        element_id = message.task_id or message.unique_id
        if message.message_type in ERROR_MESSAGES and element_id is not None:
            plugin = _plugin_lookup(element_id)
            self._failure_messages[plugin].append(message)

        return self._render(message)

    ###################################################
    #                 Private Methods                 #
    ###################################################
    def _parse_logfile_format(self, format_string, content_profile, format_profile):
        logfile_tokens = []
        while format_string:
            if format_string.startswith("%%"):
                logfile_tokens.append(FixedText(self.context, "%", content_profile, format_profile))
                format_string = format_string[2:]
                continue
            m = re.search(r"^%\{([^\}]+)\}", format_string)
            if m is not None:
                variable = m.group(1)
                format_string = format_string[m.end(0):]
                if variable not in self.logfile_variable_names:
                    raise Exception("'{0}' is not a valid log variable name.".format(variable))
                logfile_tokens.append(self.logfile_variable_names[variable])
            else:
                m = re.search("^[^%]+", format_string)
                if m is not None:
                    text = FixedText(self.context, m.group(0), content_profile, format_profile)
                    format_string = format_string[m.end(0):]
                    logfile_tokens.append(text)
                else:
                    # No idea what to do now
                    raise Exception("'{0}' could not be parsed into a valid logging format.".format(format_string))
        return logfile_tokens

    def _render(self, message):

        # Render the column widgets first
        text = ''
        for widget in self._columns:
            text += widget.render(message)

        text += '\n'

        extra_nl = False

        # Now add some custom things
        if message.detail:

            # Identify frontend messages, we never abbreviate these
            frontend_message = not (message.task_id or message.unique_id)

            # Split and truncate message detail down to message_lines lines
            lines = message.detail.splitlines(True)

            n_lines = len(lines)
            abbrev = False
            if message.message_type not in ERROR_MESSAGES \
               and not frontend_message and n_lines > self._message_lines:
                abbrev = True
                lines = lines[0:self._message_lines]
            else:
                lines[n_lines - 1] = lines[n_lines - 1].rstrip('\n')

            detail = self._indent + self._indent.join(lines)

            text += '\n'
            if message.message_type in ERROR_MESSAGES:
                text += self._err_profile.fmt(detail, bold=True)
            else:
                text += self._detail_profile.fmt(detail)

            if abbrev:
                text += self._indent + \
                    self.content_profile.fmt('Message contains {} additional lines'
                                             .format(n_lines - self._message_lines), dim=True)
            text += '\n'

            extra_nl = True

        if message.sandbox is not None:
            sandbox = self._indent + 'Sandbox directory: ' + message.sandbox

            text += '\n'
            if message.message_type == MessageType.FAIL:
                text += self._err_profile.fmt(sandbox, bold=True)
            else:
                text += self._detail_profile.fmt(sandbox)
            text += '\n'
            extra_nl = True

        if message.scheduler and message.message_type == MessageType.FAIL:
            text += '\n'

            if self.context is not None and not self.context.log_verbose:
                text += self._indent + self._err_profile.fmt("Log file: ")
                text += self._indent + self._logfile_widget.render(message) + '\n'
            else:
                text += self._indent + self._err_profile.fmt("Printing the last {} lines from log file:"
                                                             .format(self._log_lines)) + '\n'
                text += self._indent + self._logfile_widget.render(message, abbrev=False) + '\n'
                text += self._indent + self._err_profile.fmt("=" * 70) + '\n'

                log_content = self._read_last_lines(message.logfile)
                log_content = textwrap.indent(log_content, self._indent)
                text += self._detail_profile.fmt(log_content)
                text += '\n'
                text += self._indent + self._err_profile.fmt("=" * 70) + '\n'
            extra_nl = True

        if extra_nl:
            text += '\n'

        return text

    def _read_last_lines(self, logfile):
        with ExitStack() as stack:
            # mmap handles low-level memory details, allowing for
            # faster searches
            f = stack.enter_context(open(logfile, 'r+'))
            log = stack.enter_context(mmap(f.fileno(), os.path.getsize(f.name)))

            count = 0
            end = log.size() - 1

            while count < self._log_lines and end >= 0:
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

    def _format_plugins(self, element_plugins, source_plugins):
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

    # _format_values()
    #
    # Formats an indented dictionary of titles / values, ensuring
    # the values are aligned.
    #
    # Args:
    #    values: A dictionary, usually an OrderedDict()
    #    style_value: Whether to use the content profile for the values
    #
    # Returns:
    #    (str): The formatted values
    #
    def _format_values(self, values, style_value=True):
        text = ''
        max_key_len = 0
        for key, value in values.items():
            max_key_len = max(len(key), max_key_len)

        for key, value in values.items():
            if isinstance(value, str) and '\n' in value:
                text += self.format_profile.fmt("  {}:\n".format(key))
                text += textwrap.indent(value, self._indent)
                continue

            text += self.format_profile.fmt("  {}: {}".format(key, ' ' * (max_key_len - len(key))))
            if style_value:
                text += self.content_profile.fmt(str(value))
            else:
                text += str(value)
            text += '\n'

        return text
