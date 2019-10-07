#!/usr/bin/env python3
#
# Copyright (c) 2013 German M. Bravo (Kronuz)
# Copyright (c) 2018 Codethink Limited
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# This file is substantially based on German's work, obtained at:
#     https://github.com/Kronuz/ansi2html.git
#
import os
import sys
import re
import shlex
import subprocess
from contextlib import contextmanager
from tempfile import TemporaryDirectory

import click

from buildstream import _yaml
from buildstream import utils
from buildstream._exceptions import BstError


_ANSI2HTML_STYLES = {}
ANSI2HTML_CODES_RE = re.compile('(?:\033\\[(\d+(?:;\d+)*)?([cnRhlABCDfsurgKJipm]))')
ANSI2HTML_PALETTE = {
    # See http://ethanschoonover.com/solarized
    'solarized': ['#073642', '#D30102', '#859900', '#B58900', '#268BD2', '#D33682', '#2AA198', '#EEE8D5',
                  '#002B36', '#CB4B16', '#586E75', '#657B83', '#839496', '#6C71C4', '#93A1A1', '#FDF6E3'],
    # Above mapped onto the xterm 256 color palette
    'solarized-xterm': ['#262626', '#AF0000', '#5F8700', '#AF8700', '#0087FF', '#AF005F', '#00AFAF', '#E4E4E4',
                        '#1C1C1C', '#D75F00', '#585858', '#626262', '#808080', '#5F5FAF', '#8A8A8A', '#FFFFD7'],
    # Gnome default:
    'tango': ['#000000', '#CC0000', '#4E9A06', '#C4A000', '#3465A4', '#75507B', '#06989A', '#D3D7CF',
              '#555753', '#EF2929', '#8AE234', '#FCE94F', '#729FCF', '#AD7FA8', '#34E2E2', '#EEEEEC'],
    # xterm:
    'xterm': ['#000000', '#CD0000', '#00CD00', '#CDCD00', '#0000EE', '#CD00CD', '#00CDCD', '#E5E5E5',
              '#7F7F7F', '#FF0000', '#00FF00', '#FFFF00', '#5C5CFF', '#FF00FF', '#00FFFF', '#FFFFFF'],
    'console': ['#000000', '#AA0000', '#00AA00', '#AA5500', '#0000AA', '#AA00AA', '#00AAAA', '#AAAAAA',
                '#555555', '#FF5555', '#55FF55', '#FFFF55', '#5555FF', '#FF55FF', '#55FFFF', '#FFFFFF'],
}


def _ansi2html_get_styles(palette):
    if palette not in _ANSI2HTML_STYLES:
        p = ANSI2HTML_PALETTE.get(palette, ANSI2HTML_PALETTE['console'])

        regular_style = {
            '1': '',  # bold
            '2': 'opacity:0.5',
            '4': 'text-decoration:underline',
            '5': 'font-weight:bold',
            '7': '',
            '8': 'display:none',
        }
        bold_style = regular_style.copy()
        for i in range(8):
            regular_style['3%s' % i] = 'color:%s' % p[i]
            regular_style['4%s' % i] = 'background-color:%s' % p[i]

            bold_style['3%s' % i] = 'color:%s' % p[i + 8]
            bold_style['4%s' % i] = 'background-color:%s' % p[i + 8]

        # The default xterm 256 colour p:
        indexed_style = {}
        for i in range(16):
            indexed_style['%s' % i] = p[i]

        for rr in range(6):
            for gg in range(6):
                for bb in range(6):
                    i = 16 + rr * 36 + gg * 6 + bb
                    r = (rr * 40 + 55) if rr else 0
                    g = (gg * 40 + 55) if gg else 0
                    b = (bb * 40 + 55) if bb else 0
                    indexed_style['%s' % i] = ''.join('%02X' % c if 0 <= c <= 255 else None for c in (r, g, b))

        for g in range(24):
            i = g + 232
            L = g * 10 + 8
            indexed_style['%s' % i] = ''.join('%02X' % c if 0 <= c <= 255 else None for c in (L, L, L))

        _ANSI2HTML_STYLES[palette] = (regular_style, bold_style, indexed_style)
    return _ANSI2HTML_STYLES[palette]


def ansi2html(text, palette='solarized'):
    def _ansi2html(m):
        if m.group(2) != 'm':
            return ''
        import sys
        state = None
        sub = ''
        cs = m.group(1)
        cs = cs.strip() if cs else ''
        for c in cs.split(';'):
            c = c.strip().lstrip('0') or '0'
            if c == '0':
                while stack:
                    sub += '</span>'
                    stack.pop()
            elif c in ('38', '48'):
                extra = [c]
                state = 'extra'
            elif state == 'extra':
                if c == '5':
                    state = 'idx'
                elif c == '2':
                    state = 'r'
            elif state:
                if state == 'idx':
                    extra.append(c)
                    state = None
                    # 256 colors
                    color = indexed_style.get(c)  # TODO: convert index to RGB!
                    if color is not None:
                        sub += '<span style="%s:%s">' % ('color' if extra[0] == '38' else 'background-color', color)
                        stack.append(extra)
                elif state in ('r', 'g', 'b'):
                    extra.append(c)
                    if state == 'r':
                        state = 'g'
                    elif state == 'g':
                        state = 'b'
                    else:
                        state = None
                        try:
                            color = '#' + ''.join(
                                '%02X' % c if 0 <= c <= 255 else None
                                for x in extra for c in [int(x)]
                            )
                        except (ValueError, TypeError):
                            pass
                        else:
                            sub += '<span style="{}:{}">'.format(
                                'color' if extra[0] == '38' else 'background-color',
                                color)
                            stack.append(extra)
            else:
                if '1' in stack:
                    style = bold_style.get(c)
                else:
                    style = regular_style.get(c)
                if style is not None:
                    sub += '<span style="%s">' % style
                    # Still needs to be added to the stack even if style is empty
                    # (so it can check '1' in stack above, for example)
                    stack.append(c)
        return sub
    stack = []
    regular_style, bold_style, indexed_style = _ansi2html_get_styles(palette)
    sub = ANSI2HTML_CODES_RE.sub(_ansi2html, text)
    while stack:
        sub += '</span>'
        stack.pop()
    return sub


# workdir()
#
# Sets up a new temp directory with a config file
#
# Args:
#    work_directory (str): The directory where to create a tempdir first
#    source_cache (str): The directory of a source cache to share with, or None
#
# Yields:
#    The buildstream.conf full path
#
@contextmanager
def workdir(source_cache=None):
    with TemporaryDirectory(prefix='run-bst-', dir=os.getcwd()) as tempdir:
        if not source_cache:
            source_cache = os.path.join(tempdir, 'sources')

        bst_config_file = os.path.join(tempdir, 'buildstream.conf')
        config = {
            'cachedir': tempdir,
            'sourcedir': source_cache,
            'logdir': os.path.join(tempdir, 'logs'),
        }
        _yaml.roundtrip_dump(config, bst_config_file)

        yield (tempdir, bst_config_file, source_cache)


# run_bst_command()
#
# Runs a command
#
# Args:
#    config_file (str): The path to the config file to use
#    directory (str): The project directory
#    command (str): A command string
#
# Returns:
#    (str): The colorized combined stdout/stderr of BuildStream
#
def run_bst_command(config_file, directory, command):
    click.echo("Running bst command in directory '{}': bst {}".format(directory, command), err=True)

    argv = ['python3', '-m', 'buildstream', '--colors', '--config', config_file] + shlex.split(command)
    try:
        out = subprocess.check_output(argv, cwd=directory, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        click.echo("Command failed:\n{}".format(e.output.decode('utf-8').strip()))
        sys.exit(1)
    return out.decode('utf-8').strip()


# run_shell_command()
#
# Runs a command
#
# Args:
#    directory (str): The project directory
#    command (str): A shell command
#
# Returns:
#    (str): The combined stdout/stderr of the shell command
#
def run_shell_command(directory, command):
    click.echo("Running shell command in directory '{}': {}".format(directory, command), err=True)

    argv = shlex.split(command)
    p = subprocess.Popen(argv, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = p.communicate()
    return out.decode('utf-8').strip()


# generate_html
#
# Generate html based on the output
#
# Args:
#    output (str): The output of the BuildStream command
#    directory (str): The project directory
#    config_file (str): The config file
#    source_cache (str): The source cache
#    tempdir (str): The base work directory
#    palette (str): The rendering color style
#    command (str): The command
#    fake_output (bool): Whether the provided output is faked or not
#
# Returns:
#    (str): The html formatted output
#
def generate_html(output, directory, config_file, source_cache, tempdir, palette, command, fake_output):

    test_base_name = os.path.basename(directory)
    if fake_output:
        show_command = command
    else:
        show_command = 'bst ' + command

    # Substitute some things we want normalized for the docs
    output = re.sub(os.environ.get('HOME'), '/home/user', output)
    output = re.sub(config_file, '/home/user/.config/buildstream.conf', output)
    output = re.sub(source_cache, '/home/user/.cache/buildstream/sources', output)
    output = re.sub(tempdir, '/home/user/.cache/buildstream', output)
    output = re.sub(directory, '/home/user/{}'.format(test_base_name), output)

    # Now convert to HTML and add some surrounding sugar
    output = ansi2html(output, palette=palette)

    # Finally format it nicely into a <div>
    final_output = '<!--\n' + \
                   '    WARNING: This file was generated with bst2html.py\n' + \
                   '-->\n' + \
                   '<div class="highlight" style="font-size:x-small">' + \
                   '<pre>\n' + \
                   '<span style="color:#C4A000;font-weight:bold">user@host</span>:' + \
                   '<span style="color:#3456A4;font-weight:bold">~/{}</span>$ '.format(test_base_name) + \
                   show_command + '\n'

    if output:
        final_output += '\n' + output + '\n'

    final_output += '</pre></div>\n'

    return final_output


# check_needs_build()
#
# Checks whether filename, specified relative to basedir,
# needs to be built (based on whether it exists).
#
# Args:
#    basedir (str): The base directory to check relative of, or None for CWD
#    filename (str): The basedir relative path to the file
#    force (bool): Whether force rebuilding of existing things is enabled
#
# Returns:
#    (bool): Whether the file needs to be built
#
def check_needs_build(basedir, filename, force=False):
    if force:
        return True

    if basedir is None:
        basedir = os.getcwd()

    filename = os.path.join(basedir, filename)
    filename = os.path.realpath(filename)
    if not os.path.exists(filename):
        return True

    return False


def run_session(description, tempdir, source_cache, palette, config_file, force):
    desc = _yaml.load(description, shortname=os.path.basename(description))
    desc_dir = os.path.dirname(description)

    # Preflight commands and check if we can skip this session
    #
    if not force:
        needs_build = False
        commands = desc.get_sequence('commands')
        for command in commands:
            output = command.get_str('output', default=None)
            if output is not None and check_needs_build(desc_dir, output, force=False):
                needs_build = True
                break
        if not needs_build:
            click.echo("Skipping '{}' as no files need to be built".format(description), err=True)
            return

    # FIXME: Workaround a setuptools bug where the symlinks
    #        we store in git dont get carried into a release
    #        tarball. This workaround lets us build docs from
    #        a source distribution tarball.
    #
    symlinks = desc.get_mapping('workaround-symlinks', default={})
    for symlink, target in symlinks.items():
        target = target.as_str()

        # Resolve real path to where symlink should be
        symlink = os.path.join(desc_dir, symlink)

        # Ensure dir exists
        symlink_dir = os.path.dirname(symlink)
        os.makedirs(symlink_dir, exist_ok=True)

        click.echo("Generating symlink at: {} (target: {})".format(symlink, target), err=True)

        # Generate a symlink
        try:
            os.symlink(target, symlink)
        except FileExistsError:
            # If the files exist, we're running from a git checkout and
            # not a source distribution, no need to complain
            pass

    remove_files = desc.get_str_list('remove-files', default=[])
    for remove_file in remove_files:
        remove_file = os.path.join(desc_dir, remove_file)
        remove_file = os.path.realpath(remove_file)

        if os.path.isdir(remove_file):
            utils._force_rmtree(remove_file)
        else:
            utils.safe_remove(remove_file)

    # Run commands
    #
    commands = desc.get_sequence('commands')
    for command in commands:
        # Get the directory where this command should be run
        directory = command.get_str('directory')
        directory = os.path.join(desc_dir, directory)
        directory = os.path.realpath(directory)

        # Get the command string
        command_str = command.get_str('command')

        # Check whether this is a shell command and not a bst command
        is_shell = command.get_bool('shell', default=False)

        # Check if there is fake output
        command_fake_output = command.get_str('fake-output', default=None)

        # Run the command, or just use the fake output
        if command_fake_output is None:
            if is_shell:
                command_out = run_shell_command(directory, command_str)
            else:
                command_out = run_bst_command(config_file, directory, command_str)
        else:
            command_out = command_fake_output

        # Encode and save the output if that was asked for
        output = command.get_str('output', default=None)
        if output is not None:
            # Convert / Generate a nice <div>
            converted = generate_html(command_out, directory, config_file,
                                      source_cache, tempdir, palette,
                                      command_str, command_fake_output is not None)
            # Save it
            filename = os.path.join(desc_dir, output)
            filename = os.path.realpath(filename)
            output_dir = os.path.dirname(filename)
            os.makedirs(output_dir, exist_ok=True)
            with open(filename, 'wb') as f:
                f.write(converted.encode('utf-8'))

            click.echo("Saved session at '{}'".format(filename), err=True)


@click.command(short_help="Run a bst command and capture stdout/stderr in html")
@click.option('--directory', '-C',
              type=click.Path(file_okay=False, dir_okay=True),
              help="The project directory where to run the command")
@click.option('--force', is_flag=True, default=False,
              help="Force rebuild, even if the file exists")
@click.option('--source-cache',
              type=click.Path(file_okay=False, dir_okay=True),
              help="A shared source cache")
@click.option('--palette', '-p', default='tango',
              type=click.Choice(['solarized', 'solarized-xterm', 'tango', 'xterm', 'console']),
              help="Selects a palette for the output style")
@click.argument('description', type=click.Path(file_okay=True, dir_okay=False, readable=True))
def run_bst(directory, force, source_cache, description, palette):
    """Run a bst command and capture stdout/stderr in html

    This command normally takes a description yaml file, see the CONTRIBUTING
    file for information on its format.
    """
    if not source_cache and os.environ.get('BST_SOURCE_CACHE'):
        source_cache = os.environ['BST_SOURCE_CACHE']

    with workdir(source_cache=source_cache) as (tempdir, config_file, source_cache):
        run_session(description, tempdir, source_cache, palette, config_file, force)

    return 0


if __name__ == '__main__':
    try:
        run_bst()
    except BstError as e:
        click.echo("Error: {}".format(e), err=True)
        sys.exit(-1)
