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

import click
import re
import subprocess
import copy
import datetime
from blessings import Terminal

from .. import utils
from ..plugin import _plugin_lookup
from .._message import MessageType
from .. import ImplError
from .. import Element, Scope


# Profile()
#
# A class for formatting text with ansi color codes
#
# Kwargs:
#    The same keyword arguments which can be used with click.style()
#
class Profile():
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)

    # fmt()
    #
    # Format some text with ansi color codes
    #
    # Args:
    #    text (str): The text to format
    #
    # Kwargs:
    #    Keyword arguments to apply on top of the base click.style()
    #    arguments
    #
    def fmt(self, text, **kwargs):
        kwargs = dict(kwargs)
        fmtargs = copy.copy(self.kwargs)
        fmtargs.update(kwargs)
        return click.style(text, **fmtargs)

    # fmt_subst()
    #
    # Substitute a variable of the %{varname} form, formatting
    # only the substituted text with the given click.style() configurations
    #
    # Args:
    #    text (str): The text to format, with possible variables
    #    varname (str): The variable name to substitute
    #    value (str): The value to substitute the variable with
    #
    # Kwargs:
    #    Keyword arguments to apply on top of the base click.style()
    #    arguments
    #
    def fmt_subst(self, text, varname, value, **kwargs):

        def subst_callback(match):
            # Extract and format the "{(varname)...}" portion of the match
            inner_token = match.group(1)
            formatted = inner_token.format(**{varname: value})

            # Colorize after the pythonic format formatting, which may have padding
            return self.fmt(formatted, **kwargs)

        # Lazy regex, after our word, match anything that does not have '%'
        return re.sub(r"%(\{(" + varname + r")[^%]*\})", subst_callback, text)


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

        return self.format_profile.fmt('[') + \
            self.format_profile.fmt(':').join(fields) + \
            self.format_profile.fmt(']')


# A widget for rendering the action name
class ActionName(Widget):

    def render(self, message):
        action_name = message.action_name
        if not action_name:
            action_name = ""
        return self.format_profile.fmt('[') + \
            self.content_profile.fmt("{: ^5}".format(action_name)) + \
            self.format_profile.fmt(']')


# A widget for rendering the MessageType
class TypeName(Widget):

    action_colors = {
        MessageType.DEBUG: "cyan",
        MessageType.STATUS: "cyan",
        MessageType.INFO: "magenta",
        MessageType.WARN: "yellow",
        MessageType.ERROR: "red",
        MessageType.START: "blue",
        MessageType.SUCCESS: "green",
        MessageType.FAIL: "red",
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
        self.fmt_string = '{: <35}'

    def size_request(self, pipeline):
        longest_name = 0
        for plugin in pipeline.dependencies(Scope.ALL, include_sources=True):
            longest_name = max(len(plugin._get_display_name()), longest_name)

        # Put a cap at a specific width, usually some elements cause the line
        # to be too long, just live with the unaligned columns in that case
        longest_name = min(longest_name, 35)
        self.fmt_string = '{: <' + str(longest_name) + '}'

    def render(self, message):
        if message.unique_id is not None:
            plugin = _plugin_lookup(message.unique_id)
            name = plugin._get_display_name()
        else:
            name = ''

        return self.format_profile.fmt('[') + \
            self.content_profile.fmt(
                self.fmt_string.format(name)) + \
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

    def size_request(self, pipeline):
        self.key_length = pipeline.context.log_key_length

    def render(self, message):

        key = ' ' * self.key_length
        if message.unique_id is not None:
            plugin = _plugin_lookup(message.unique_id)
            if isinstance(plugin, Element):
                key = plugin._get_display_key()

        if message.message_type == MessageType.FAIL:
            text = self.err_profile.fmt(key)
        else:
            text = self.content_profile.fmt(key)

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

    def render(self, message):

        if message.logfile and message.scheduler:
            logfile = message.logfile
            if logfile.startswith(self.logdir):
                logfile = logfile[len(self.logdir) + 1:]

            if message.message_type == MessageType.FAIL:
                text = self.err_profile.fmt(logfile)
            else:
                text = self.content_profile.fmt(logfile, dim=True)
        else:
            text = ''

        return text


# A widget for formatting a log line
class LogLine(Widget):

    def __init__(self, content_profile, format_profile, err_profile, detail_profile,
                 indent=4,
                 log_lines=10,
                 debug=False):
        super(LogLine, self).__init__(content_profile, format_profile)

        self.columns = []
        self.err_profile = err_profile
        self.detail_profile = detail_profile
        self.indent = ' ' * indent
        self.log_lines = log_lines

        self.space_widget = Space(content_profile, format_profile)
        self.message_widget = MessageText(content_profile, format_profile)
        self.logfile_widget = LogFile(content_profile, format_profile, err_profile)

        if debug:
            self.columns.extend([
                Debug(content_profile, format_profile),
                ActionName(content_profile, format_profile)
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

        # Show the log file only in the main start/success/fail messages
        if message.logfile and message.scheduler:
            text += self.logfile_widget.render(message)
        else:
            text += self.message_widget.render(message)

        text += '\n'

        extra_nl = False

        # Now add some custom things
        if message.detail is not None:

            detail = message.detail.rstrip('\n')
            detail = self.indent + self.indent.join((detail.splitlines(True)))

            text += '\n'
            if message.message_type == MessageType.FAIL:
                text += self.err_profile.fmt(detail, bold=True)
            else:
                text += self.detail_profile.fmt(detail)
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
            log_content = self.read_last_lines(message.logfile)
            log_content = self.indent + self.indent.join(log_content.splitlines(True))

            text += '\n'
            text += self.detail_profile.fmt(log_content)
            text += '\n'
            extra_nl = True

        if extra_nl:
            text += '\n'

        return text

    def read_last_lines(self, logfile):
        tail_command = utils.get_host_tool('tail')

        # Lets just expect this to always pass for now...
        output = subprocess.check_output([tail_command, '-n', str(self.log_lines), logfile])
        output = output.decode('UTF-8')
        return output.rstrip()


# A widget for formatting a job in the status area
class StatusJob():

    def __init__(self, element, action_name, content_profile, format_profile):
        # Record start time at initialization
        self.starttime = datetime.datetime.now()
        self.element = element
        self.action_name = action_name
        self.content_profile = content_profile
        self.format_profile = format_profile
        self.time_code = TimeCode(content_profile, format_profile)

        # Calculate the size needed to display
        self.size = 10  # Size of time code
        self.size += len(action_name)
        self.size += len(element._get_display_name())
        self.size += 3  # '[' + ':' + ']'

    # render()
    #
    # Render the Job, return a rendered string
    #
    # Args:
    #    padding (int): Amount of padding to print in order to align with columns
    #
    def render(self, padding):
        elapsed = datetime.datetime.now() - self.starttime
        text = self.time_code.render_time(elapsed)

        # Add padding after the display name, before terminating ']'
        display_name = self.element._get_display_name() + (' ' * padding)
        text += self.format_profile.fmt('[') + \
            self.content_profile.fmt(self.action_name) + \
            self.format_profile.fmt(':') + \
            self.content_profile.fmt(display_name) + \
            self.format_profile.fmt(']')

        return text


# Status()
#
# A widget for formatting overall status.
#
# Note that the render() and clear() methods in this class are
# simply noops in the case that the application is not connected
# to a terminal, or if the terminal does not support ANSI escape codes.
#
# Args:
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#
class Status():

    def __init__(self, content_profile, format_profile):

        self.content_profile = content_profile
        self.format_profile = format_profile
        self.jobs = []
        self.last_lines = 0  # Number of status lines we last printed to console
        self.term = Terminal()
        self.spacing = 1

        self.term_width, _ = click.get_terminal_size()
        self.alloc_lines = 0
        self.alloc_columns = None
        self.line_length = 0
        self.need_alloc = True

    # add_job()
    #
    # Adds a job to track in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def add_job(self, element, action_name):
        job = StatusJob(element, action_name, self.content_profile, self.format_profile)
        self.jobs.append(job)
        self.need_alloc = True

    # remove_job()
    #
    # Removes a job currently being tracked in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def remove_job(self, element, action_name):
        self.jobs = [
            job for job in self.jobs
            if not (job.element is element and
                    job.action_name == action_name)
        ]
        self.need_alloc = True

    # clear()
    #
    # Clear the status area, it is necessary to call
    # this before printing anything to the console if
    # a status area is in use.
    #
    # To print some logging to the output and then restore
    # the status, use the following:
    #
    #   status.clear()
    #   ... print something to console ...
    #   status.render()
    #
    def clear(self):

        if not self.term.does_styling:
            return

        for i in range(self.last_lines):
            self.move_up()
            self.clear_line()
        self.last_lines = 0

    # render()
    #
    # Render the status area.
    #
    # If you are not printing a line in addition to rendering
    # the status area, for instance in a timeout, then it is
    # not necessary to call clear().
    def render(self):

        if not self.term.does_styling:
            return

        self.clear()
        self.check_term_width()
        self.allocate()

        # Nothing to render, early return
        if self.alloc_lines == 0:
            return

        # Before rendering the actual lines, we need to add some line
        # feeds for the amount of lines we intend to print first, and
        # move cursor position back to the first line
        for _ in range(self.alloc_lines + 1):
            click.echo('')
        for _ in range(self.alloc_lines + 1):
            self.move_up()

        # Print one separator line
        separator = self.format_profile.fmt('=' * self.line_length)
        click.echo(separator)

        # Now we have the number of columns, and an allocation for
        # alignment of each column
        n_columns = len(self.alloc_columns)
        for line in self.job_lines(n_columns):
            text = ''
            for job in line:
                column = line.index(job)
                text += job.render(self.alloc_columns[column] - job.size)

                # Add padding for columnization
                # text += ' ' * (self.alloc_columns[column] - job.size)

                # Add spacing between columns
                if column < (n_columns - 1):
                    text += ' ' * self.spacing

            # Print the line
            click.echo(text)

        # Track what we printed last, for the next clear
        self.last_lines = self.alloc_lines + 1

    ###########################################
    #         Status area internals           #
    ###########################################
    def check_term_width(self):
        term_width, _ = click.get_terminal_size()
        if self.term_width != term_width:
            self.term_width = term_width
            self.need_alloc = True

    def move_up(self):
        # Explicitly move to beginning of line, fixes things up
        # when there was a ^C or ^Z printed to the terminal.
        click.echo(self.term.move_x(0) + self.term.move_up, nl=False)

    def clear_line(self):
        click.echo(self.term.clear_eol, nl=False)

    def allocate(self):
        if not self.need_alloc:
            return

        # State when there is no jobs to display
        alloc_lines = 0
        alloc_columns = []
        line_length = 0

        # Test for the widest width which fits columnized jobs
        for columns in reversed(range(len(self.jobs))):
            alloc_lines, alloc_columns = self.allocate_columns(columns + 1)

            # If the sum of column widths with spacing in between
            # fits into the terminal width, this is a good allocation.
            line_length = sum(alloc_columns) + (columns * self.spacing)
            if line_length < self.term_width:
                break

        self.alloc_lines = alloc_lines
        self.alloc_columns = alloc_columns
        self.line_length = line_length
        self.need_alloc = False

    def job_lines(self, columns):
        for i in range(0, len(self.jobs), columns):
            yield self.jobs[i:i + columns]

    # Returns an array of integers representing the maximum
    # length in characters for each column, given the current
    # list of jobs to render.
    #
    def allocate_columns(self, columns):
        column_widths = [0 for _ in range(columns)]
        lines = 0
        for line in self.job_lines(columns):
            line_len = len(line)
            lines += 1
            for col in range(columns):
                if (col < line_len):
                    job = line[col]
                    column_widths[col] = max(column_widths[col], job.size)

        return lines, column_widths
