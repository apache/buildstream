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
import re
import subprocess
from tempfile import TemporaryDirectory

import click

from buildstream import _yaml


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
            l = g * 10 + 8
            indexed_style['%s' % i] = ''.join('%02X' % c if 0 <= c <= 255 else None for c in (l, l, l))

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


# FIXME: Workaround a setuptools bug which fails to include symbolic
#        links in the source distribution.
#
#        Remove this hack once setuptools is fixed
def workaround_setuptools_bug(project):
    os.makedirs(os.path.join(project, "files", "links"), exist_ok=True)
    try:
        os.symlink(os.path.join("usr", "lib"), os.path.join(project, "files", "links", "lib"))
        os.symlink(os.path.join("usr", "bin"), os.path.join(project, "files", "links", "bin"))
        os.symlink(os.path.join("usr", "etc"), os.path.join(project, "files", "links", "etc"))
    except FileExistsError:
        # If the files exist, we're running from a git checkout and
        # not a source distribution, no need to complain
        pass


@click.command(short_help="Run a bst command and capture stdout/stderr in html")
@click.option('--directory', '-C',
              type=click.Path(file_okay=False, dir_okay=True),
              help="The project directory where to run the command")
@click.option('--source-cache',
              type=click.Path(file_okay=False, dir_okay=True),
              help="A shared source cache")
@click.option('--palette', '-p', default='tango',
              type=click.Choice(['solarized', 'solarized-xterm', 'tango', 'xterm', 'console']),
              help="Selects a palette for the output style")
@click.option('--output', '-o',
              type=click.Path(file_okay=True, dir_okay=False, writable=True),
              help="A file to store the output")
@click.option('--description', '-d',
              type=click.Path(file_okay=True, dir_okay=False, readable=True),
              help="A file describing what to do")
@click.argument('command', type=click.STRING, nargs=-1)
def run_bst(directory, source_cache, description, palette, output, command):
    """Run a bst command and capture stdout/stderr in html

    This command normally takes a description yaml file, the format
    of that file is as follows:

    \b
       # A relative path to the project, from the description file itself
       directory: path/to/project

    \b
       # A list of commands to run in preparation
       prepare-commands:
       - fetch hello.bst

    \b
       # The command to generate html output for
       command: build hello.bst
    """
    prepare_commands = []

    if description:
        desc = _yaml.load(description, shortname=os.path.basename(description))
        desc_dir = os.path.dirname(description)

        command_str = _yaml.node_get(desc, str, 'command')
        command = command_str.split()

        # The directory should be relative to where the description file was
        # stored
        directory_str = _yaml.node_get(desc, str, 'directory')
        directory = os.path.join(desc_dir, directory_str)
        directory = os.path.realpath(directory)

        prepare = _yaml.node_get(desc, list, 'prepare-commands', default_value=[])
        for prepare_command in prepare:
            prepare_commands.append(prepare_command)

    else:
        if not command:
            command = []

        if not directory:
            directory = os.getcwd()
        else:
            directory = os.path.abspath(directory)
            directory = os.path.realpath(directory)

    # FIXME: Here we just setup a files/links subdir with
    #        the symlinks we want for usrmerge, ideally
    #        we dont need this anymore once setuptools gets
    #        fixed.
    #
    workaround_setuptools_bug(directory)

    test_base_name = os.path.basename(directory)

    if not source_cache and os.environ.get('BST_SOURCE_CACHE'):
        source_cache = os.environ['BST_SOURCE_CACHE']

    with TemporaryDirectory(prefix='run-bst-', dir=directory) as tempdir:
        bst_config_file = os.path.join(tempdir, 'buildstream.conf')
        final_command = ['bst', '--colors', '--config', bst_config_file]
        final_command += command

        show_command = ['bst']
        show_command += command
        show_command_string = ' '.join(show_command)

        if not source_cache:
            source_cache = os.path.join(tempdir, 'sources')

        config = {
            'sourcedir': source_cache,
            'artifactdir': os.path.join(tempdir, 'artifacts'),
            'logdir': os.path.join(tempdir, 'logs'),
            'builddir': os.path.join(tempdir, 'build'),
        }
        _yaml.dump(config, bst_config_file)

        # Run some prepare commands if they were specified
        #
        for prepare_command_str in prepare_commands:
            prepare_command = ['bst', '--config', bst_config_file] + prepare_command_str.split()
            p = subprocess.Popen(prepare_command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            _, _ = p.communicate()

        # Run BuildStream and collect the output in a single string,
        # with the ANSI escape sequences forced enabled.
        #
        p = subprocess.Popen(final_command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()
        decoded = out.decode('utf-8').strip()

        # Substitute some things we want normalized for the docs
        decoded = re.sub(os.environ.get('HOME'), '/home/user', decoded)
        decoded = re.sub(bst_config_file, '/home/user/.config/buildstream.conf', decoded)
        decoded = re.sub(source_cache, '/home/user/.cache/buildstream/sources', decoded)
        decoded = re.sub(tempdir, '/home/user/.cache/buildstream', decoded)
        decoded = re.sub(directory, '/home/user/{}'.format(test_base_name), decoded)

    # Now convert to HTML and add some surrounding sugar
    div_style = 'font-size:x-small'
    converted = ansi2html(decoded, palette=palette)
    converted = '<div class="highlight" style="{}">'.format(div_style) + \
                '<pre>\n' + \
                '<span style="color:#C4A000;font-weight:bold">user@host</span>:' + \
                '<span style="color:#3456A4;font-weight:bold">~/{}</span>$ '.format(test_base_name) + \
                show_command_string + '\n\n' + \
                converted + '\n' + \
                '</pre></div>\n'

    # Prepend a warning
    #
    converted = '<!--\n' + \
                '    WARNING: This file was generated with bst2html.py\n' + \
                '-->\n' + \
                converted

    if output is None:
        click.echo(converted)
    else:
        outdir = os.path.dirname(output)
        os.makedirs(outdir, exist_ok=True)
        with open(output, 'wb') as f:
            f.write(converted.encode('utf-8'))

    return p.returncode

if __name__ == '__main__':
    run_bst()
