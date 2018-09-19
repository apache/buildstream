#
#  Copyright (C) 2018 Codethink Limited
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
import curses

# Import a widget internal for formatting time codes
from .widget import TimeCode
from .._scheduler import ElementJob


# Status()
#
# A widget for formatting overall status.
#
# Note that the render() and clear() methods in this class are
# simply noops in the case that the application is not connected
# to a terminal, or if the terminal does not support ANSI escape codes.
#
# Args:
#    context (Context): The Context
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#    success_profile (Profile): Formatting profile for success text
#    error_profile (Profile): Formatting profile for error text
#    stream (Stream): The Stream
#    colors (bool): Whether to print the ANSI color codes in the output
#
class Status():

    # Table of the terminal capabilities we require and use
    _TERM_CAPABILITIES = {
        'move_up': 'cuu1',
        'move_x': 'hpa',
        'clear_eol': 'el'
    }

    def __init__(self, context,
                 content_profile, format_profile,
                 success_profile, error_profile,
                 stream, colors=False):

        self._context = context
        self._content_profile = content_profile
        self._format_profile = format_profile
        self._success_profile = success_profile
        self._error_profile = error_profile
        self._stream = stream
        self._jobs = []
        self._last_lines = 0  # Number of status lines we last printed to console
        self._spacing = 1
        self._colors = colors
        self._header = _StatusHeader(context,
                                     content_profile, format_profile,
                                     success_profile, error_profile,
                                     stream)

        self._term_width, _ = click.get_terminal_size()
        self._alloc_lines = 0
        self._alloc_columns = None
        self._line_length = 0
        self._need_alloc = True
        self._term_caps = self._init_terminal()

    # add_job()
    #
    # Adds a job to track in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def add_job(self, job):
        elapsed = self._stream.elapsed_time
        job = _StatusJob(self._context, job, self._content_profile, self._format_profile, elapsed)
        self._jobs.append(job)
        self._need_alloc = True

    # remove_job()
    #
    # Removes a job currently being tracked in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def remove_job(self, job):
        action_name = job.action_name
        if not isinstance(job, ElementJob):
            element = None
        else:
            element = job.element

        self._jobs = [
            job for job in self._jobs
            if not (job.element is element and
                    job.action_name == action_name)
        ]
        self._need_alloc = True

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

        if not self._term_caps:
            return

        for _ in range(self._last_lines):
            self._move_up()
            self._clear_line()
        self._last_lines = 0

    # render()
    #
    # Render the status area.
    #
    # If you are not printing a line in addition to rendering
    # the status area, for instance in a timeout, then it is
    # not necessary to call clear().
    def render(self):

        if not self._term_caps:
            return

        elapsed = self._stream.elapsed_time

        self.clear()
        self._check_term_width()
        self._allocate()

        # Nothing to render, early return
        if self._alloc_lines == 0:
            return

        # Before rendering the actual lines, we need to add some line
        # feeds for the amount of lines we intend to print first, and
        # move cursor position back to the first line
        for _ in range(self._alloc_lines + self._header.lines):
            click.echo('', err=True)
        for _ in range(self._alloc_lines + self._header.lines):
            self._move_up()

        # Render the one line header
        text = self._header.render(self._term_width, elapsed)
        click.echo(text, color=self._colors, err=True)

        # Now we have the number of columns, and an allocation for
        # alignment of each column
        n_columns = len(self._alloc_columns)
        for line in self._job_lines(n_columns):
            text = ''
            for job in line:
                column = line.index(job)
                text += job.render(self._alloc_columns[column] - job.size, elapsed)

                # Add spacing between columns
                if column < (n_columns - 1):
                    text += ' ' * self._spacing

            # Print the line
            click.echo(text, color=self._colors, err=True)

        # Track what we printed last, for the next clear
        self._last_lines = self._alloc_lines + self._header.lines

    ###################################################
    #                 Private Methods                 #
    ###################################################

    # _init_terminal()
    #
    # Initialize the terminal and return the resolved terminal
    # capabilities dictionary.
    #
    # Returns:
    #    (dict|None): The resolved terminal capabilities dictionary,
    #                 or None if the terminal does not support all
    #                 of the required capabilities.
    #
    def _init_terminal(self):

        # We need both output streams to be connected to a terminal
        if not (sys.stdout.isatty() and sys.stderr.isatty()):
            return None

        # Initialized terminal, curses might decide it doesnt
        # support this terminal
        try:
            curses.setupterm(os.environ.get('TERM', 'dumb'))
        except curses.error:
            return None

        term_caps = {}

        # Resolve the string capabilities we need for the capability
        # names we need.
        #
        for capname, capval in self._TERM_CAPABILITIES.items():
            code = curses.tigetstr(capval)

            # If any of the required capabilities resolve empty strings or None,
            # then we don't have the capabilities we need for a status bar on
            # this terminal.
            if not code:
                return None

            # Decode sequences as latin1, as they are always 8-bit bytes,
            # so when b'\xff' is returned, this must be decoded to u'\xff'.
            #
            # This technique is employed by the python blessings library
            # as well, and should provide better compatibility with most
            # terminals.
            #
            term_caps[capname] = code.decode('latin1')

        return term_caps

    def _check_term_width(self):
        term_width, _ = click.get_terminal_size()
        if self._term_width != term_width:
            self._term_width = term_width
            self._need_alloc = True

    def _move_up(self):
        assert self._term_caps is not None

        # Explicitly move to beginning of line, fixes things up
        # when there was a ^C or ^Z printed to the terminal.
        move_x = curses.tparm(self._term_caps['move_x'].encode('latin1'), 0)
        move_x = move_x.decode('latin1')

        move_up = curses.tparm(self._term_caps['move_up'].encode('latin1'))
        move_up = move_up.decode('latin1')

        click.echo(move_x + move_up, nl=False, err=True)

    def _clear_line(self):
        assert self._term_caps is not None

        clear_eol = curses.tparm(self._term_caps['clear_eol'].encode('latin1'))
        clear_eol = clear_eol.decode('latin1')
        click.echo(clear_eol, nl=False, err=True)

    def _allocate(self):
        if not self._need_alloc:
            return

        # State when there is no jobs to display
        alloc_lines = 0
        alloc_columns = []
        line_length = 0

        # Test for the widest width which fits columnized jobs
        for columns in reversed(range(len(self._jobs))):
            alloc_lines, alloc_columns = self._allocate_columns(columns + 1)

            # If the sum of column widths with spacing in between
            # fits into the terminal width, this is a good allocation.
            line_length = sum(alloc_columns) + (columns * self._spacing)
            if line_length < self._term_width:
                break

        self._alloc_lines = alloc_lines
        self._alloc_columns = alloc_columns
        self._line_length = line_length
        self._need_alloc = False

    def _job_lines(self, columns):
        for i in range(0, len(self._jobs), columns):
            yield self._jobs[i:i + columns]

    # Returns an array of integers representing the maximum
    # length in characters for each column, given the current
    # list of jobs to render.
    #
    def _allocate_columns(self, columns):
        column_widths = [0 for _ in range(columns)]
        lines = 0
        for line in self._job_lines(columns):
            line_len = len(line)
            lines += 1
            for col in range(columns):
                if col < line_len:
                    job = line[col]
                    column_widths[col] = max(column_widths[col], job.size)

        return lines, column_widths


# _StatusHeader()
#
# A delegate object for rendering the header part of the Status() widget
#
# Args:
#    context (Context): The Context
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#    success_profile (Profile): Formatting profile for success text
#    error_profile (Profile): Formatting profile for error text
#    stream (Stream): The Stream
#
class _StatusHeader():

    def __init__(self, context,
                 content_profile, format_profile,
                 success_profile, error_profile,
                 stream):

        #
        # Public members
        #
        self.lines = 3

        #
        # Private members
        #
        self._content_profile = content_profile
        self._format_profile = format_profile
        self._success_profile = success_profile
        self._error_profile = error_profile
        self._stream = stream
        self._time_code = TimeCode(context, content_profile, format_profile)
        self._context = context

    def render(self, line_length, elapsed):
        project = self._context.get_toplevel_project()
        line_length = max(line_length, 80)
        size = 0
        text = ''

        session = str(len(self._stream.session_elements))
        total = str(len(self._stream.total_elements))

        # Format and calculate size for target and overall time code
        size += len(total) + len(session) + 4  # Size for (N/N) with a leading space
        size += 8  # Size of time code
        size += len(project.name) + 1
        text += self._time_code.render_time(elapsed)
        text += ' ' + self._content_profile.fmt(project.name)
        text += ' ' + self._format_profile.fmt('(') + \
                self._content_profile.fmt(session) + \
                self._format_profile.fmt('/') + \
                self._content_profile.fmt(total) + \
                self._format_profile.fmt(')')

        line1 = self._centered(text, size, line_length, '=')
        size = 0
        text = ''

        # Format and calculate size for each queue progress
        for queue in self._stream.queues:

            # Add spacing
            if self._stream.queues.index(queue) > 0:
                size += 2
                text += self._format_profile.fmt('→ ')

            queue_text, queue_size = self._render_queue(queue)
            size += queue_size
            text += queue_text

        line2 = self._centered(text, size, line_length, ' ')

        size = 24
        text = self._format_profile.fmt("~~~~~ ") + \
            self._content_profile.fmt('Active Tasks') + \
            self._format_profile.fmt(" ~~~~~")
        line3 = self._centered(text, size, line_length, ' ')

        return line1 + '\n' + line2 + '\n' + line3

    ###################################################
    #                 Private Methods                 #
    ###################################################
    def _render_queue(self, queue):
        processed = str(len(queue.processed_elements))
        skipped = str(len(queue.skipped_elements))
        failed = str(len(queue.failed_elements))

        size = 5  # Space for the formatting '[', ':', ' ', ' ' and ']'
        size += len(queue.complete_name)
        size += len(processed) + len(skipped) + len(failed)
        text = self._format_profile.fmt("(") + \
            self._content_profile.fmt(queue.complete_name) + \
            self._format_profile.fmt(":") + \
            self._success_profile.fmt(processed) + ' ' + \
            self._content_profile.fmt(skipped) + ' ' + \
            self._error_profile.fmt(failed) + \
            self._format_profile.fmt(")")

        return (text, size)

    def _centered(self, text, size, line_length, fill):
        remaining = line_length - size
        remaining -= 2

        final_text = self._format_profile.fmt(fill * (remaining // 2)) + ' '
        final_text += text
        final_text += ' ' + self._format_profile.fmt(fill * (remaining // 2))

        return final_text


# _StatusJob()
#
# A delegate object for rendering a job in the status area
#
# Args:
#    context (Context): The Context
#    job (Job): The job being processed
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#    elapsed (datetime): The offset into the session when this job is created
#
class _StatusJob():

    def __init__(self, context, job, content_profile, format_profile, elapsed):
        action_name = job.action_name
        if not isinstance(job, ElementJob):
            element = None
        else:
            element = job.element

        #
        # Public members
        #
        self.element = element            # The Element
        self.action_name = action_name    # The action name
        self.size = None                  # The number of characters required to render
        self.full_name = element._get_full_name() if element else action_name

        #
        # Private members
        #
        self._offset = elapsed
        self._content_profile = content_profile
        self._format_profile = format_profile
        self._time_code = TimeCode(context, content_profile, format_profile)

        # Calculate the size needed to display
        self.size = 10  # Size of time code with brackets
        self.size += len(action_name)
        self.size += len(self.full_name)
        self.size += 3  # '[' + ':' + ']'

    # render()
    #
    # Render the Job, return a rendered string
    #
    # Args:
    #    padding (int): Amount of padding to print in order to align with columns
    #    elapsed (datetime): The session elapsed time offset
    #
    def render(self, padding, elapsed):
        text = self._format_profile.fmt('[') + \
            self._time_code.render_time(elapsed - self._offset) + \
            self._format_profile.fmt(']')

        # Add padding after the display name, before terminating ']'
        name = self.full_name + (' ' * padding)
        text += self._format_profile.fmt('[') + \
            self._content_profile.fmt(self.action_name) + \
            self._format_profile.fmt(':') + \
            self._content_profile.fmt(name) + \
            self._format_profile.fmt(']')

        return text
