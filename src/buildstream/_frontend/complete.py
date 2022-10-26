#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  This module was forked from the python click library, Included
#  original copyright notice from the Click library and following disclaimer
#  as per their LICENSE requirements.
#
#  Copyright (c) 2014 by Armin Ronacher.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
import collections.abc
import copy
import os

import click
from click.core import MultiCommand, Option, Argument
from click.parser import split_arg_string

WORDBREAK = "="

COMPLETION_SCRIPT = """
%(complete_func)s() {
    local IFS=$'\n'
    COMPREPLY=( $( env COMP_WORDS="${COMP_WORDS[*]}" \\
                   COMP_CWORD=$COMP_CWORD \\
                   %(autocomplete_var)s=complete $1 ) )
    return 0
}

complete -F %(complete_func)s -o nospace %(script_names)s
"""


# An exception for our custom completion handler to
# indicate that it does not want to handle completion
# for this parameter
#
class CompleteUnhandled(Exception):
    pass


def complete_path(path_type, incomplete, base_directory="."):
    """Helper method for implementing the completions() method
    for File and Path parameter types.
    """

    # Try listing the files in the relative or absolute path
    # specified in `incomplete` minus the last path component,
    # otherwise list files starting from the current working directory.
    entries = []
    base_path = ""

    # This is getting a bit messy
    listed_base_directory = False

    if os.path.sep in incomplete:
        split = incomplete.rsplit(os.path.sep, 1)
        base_path = split[0]

        # If there was nothing on the left of the last separator,
        # we are completing files in the filesystem root
        base_path = os.path.join(base_directory, base_path)
    else:
        incomplete_base_path = os.path.join(base_directory, incomplete)
        if os.path.isdir(incomplete_base_path):
            base_path = incomplete_base_path

    try:
        if base_path:
            if os.path.isdir(base_path):
                entries = [os.path.join(base_path, e) for e in os.listdir(base_path)]
        else:
            entries = os.listdir(base_directory)
            listed_base_directory = True
    except OSError:
        # If for any reason the os reports an error from os.listdir(), just
        # ignore this and avoid a stack trace
        pass

    base_directory_slash = base_directory
    if not base_directory_slash.endswith(os.sep):
        base_directory_slash += os.sep
    base_directory_len = len(base_directory_slash)

    def entry_is_dir(entry):
        if listed_base_directory:
            entry = os.path.join(base_directory, entry)
        return os.path.isdir(entry)

    def fix_path(path):

        # Append slashes to any entries which are directories, or
        # spaces for other files since they cannot be further completed
        if entry_is_dir(path) and not path.endswith(os.sep):
            path = path + os.sep
        else:
            path = path + " "

        # Remove the artificial leading path portion which
        # may have been prepended for search purposes.
        if path.startswith(base_directory_slash):
            path = path[base_directory_len:]

        return path

    return [
        # Return an appropriate path for each entry
        fix_path(e)
        for e in sorted(entries)
        # Filter out non directory elements when searching for a directory,
        # the opposite is fine, however.
        if not (path_type == "Directory" and not entry_is_dir(e))
    ]


# Instead of delegating completions to the param type,
# hard code all of buildstream's completions here.
#
# This whole module should be removed in favor of more
# generic code in click once this issue is resolved:
#   https://github.com/pallets/click/issues/780
#
def get_param_type_completion(param_type, incomplete):

    if isinstance(param_type, click.Choice):
        return [c + " " for c in param_type.choices]
    elif isinstance(param_type, click.File):
        return complete_path("File", incomplete)
    elif isinstance(param_type, click.Path):

        # Workaround click 8.x API break:
        #
        #    https://github.com/pallets/click/issues/2037
        #
        if param_type.file_okay and not param_type.dir_okay:
            path_type = "File"
        elif param_type.dir_okay and not param_type.file_okay:
            path_type = "Directory"
        else:
            path_type = "Path"

        return complete_path(path_type, incomplete)

    return []


def resolve_ctx(cli, prog_name, args):
    """
    Parse into a hierarchy of contexts. Contexts are connected through the parent variable.
    :param cli: command definition
    :param prog_name: the program that is running
    :param args: full list of args typed before the incomplete arg
    :return: the final context/command parsed
    """
    ctx = cli.make_context(prog_name, args, resilient_parsing=True)
    args_remaining = ctx.protected_args + ctx.args
    while ctx is not None and args_remaining:
        if isinstance(ctx.command, MultiCommand):
            cmd = ctx.command.get_command(ctx, args_remaining[0])
            if cmd is None:
                return None
            ctx = cmd.make_context(args_remaining[0], args_remaining[1:], parent=ctx, resilient_parsing=True)
            args_remaining = ctx.protected_args + ctx.args
        else:
            ctx = ctx.parent

    return ctx


def start_of_option(param_str):
    """
    :param param_str: param_str to check
    :return: whether or not this is the start of an option declaration (i.e. starts "-" or "--")
    """
    return param_str and param_str[:1] == "-"


def is_incomplete_option(all_args, cmd_param):
    """
    :param all_args: the full original list of args supplied
    :param cmd_param: the current command paramter
    :return: whether or not the last option declaration (i.e. starts "-" or "--") is incomplete and
    corresponds to this cmd_param. In other words whether this cmd_param option can still accept
    values
    """
    if cmd_param.is_flag:
        return False
    last_option = None
    for index, arg_str in enumerate(reversed([arg for arg in all_args if arg != WORDBREAK])):
        if index + 1 > cmd_param.nargs:
            break
        if start_of_option(arg_str):
            last_option = arg_str

    return bool(last_option and last_option in cmd_param.opts)


def is_incomplete_argument(current_params, cmd_param):
    """
    :param current_params: the current params and values for this argument as already entered
    :param cmd_param: the current command parameter
    :return: whether or not the last argument is incomplete and corresponds to this cmd_param. In
    other words whether or not the this cmd_param argument can still accept values
    """
    current_param_values = current_params[cmd_param.name]
    if current_param_values is None:
        return True
    if cmd_param.nargs == -1:
        return True
    if (
        isinstance(current_param_values, collections.abc.Iterable)
        and cmd_param.nargs > 1
        and len(current_param_values) < cmd_param.nargs
    ):
        return True
    return False


def get_user_autocompletions(args, incomplete, cmd, cmd_param, override):
    """
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text of the arg to autocomplete
    :param cmd_param: command definition
    :param override: a callable (cmd_param, args, incomplete) that will be
    called to override default completion based on parameter type. Should raise
    'CompleteUnhandled' if it could not find a completion.
    :return: all the possible user-specified completions for the param
    """

    # Use the type specific default completions unless it was overridden
    try:
        return override(cmd=cmd, cmd_param=cmd_param, args=args, incomplete=incomplete)
    except CompleteUnhandled:
        return get_param_type_completion(cmd_param.type, incomplete) or []


def get_choices(cli, prog_name, args, incomplete, override):
    """
    :param cli: command definition
    :param prog_name: the program that is running
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text of the arg to autocomplete
    :param override: a callable (cmd_param, args, incomplete) that will be
    called to override default completion based on parameter type. Should raise
    'CompleteUnhandled' if it could not find a completion.
    :return: all the possible completions for the incomplete
    """
    all_args = copy.deepcopy(args)

    ctx = resolve_ctx(cli, prog_name, args)
    if ctx is None:
        return

    # In newer versions of bash long opts with '='s are partitioned, but it's easier to parse
    # without the '='
    if start_of_option(incomplete) and WORDBREAK in incomplete:
        partition_incomplete = incomplete.partition(WORDBREAK)
        all_args.append(partition_incomplete[0])
        incomplete = partition_incomplete[2]
    elif incomplete == WORDBREAK:
        incomplete = ""

    choices = []
    found_param = False
    if start_of_option(incomplete):
        # completions for options
        for param in ctx.command.params:
            if isinstance(param, Option):
                choices.extend(
                    [
                        param_opt + " "
                        for param_opt in param.opts + param.secondary_opts
                        if param_opt not in all_args or param.multiple
                    ]
                )
        found_param = True
    if not found_param:
        # completion for option values by choices
        for cmd_param in ctx.command.params:
            if isinstance(cmd_param, Option) and is_incomplete_option(all_args, cmd_param):
                choices.extend(get_user_autocompletions(all_args, incomplete, ctx.command, cmd_param, override))
                found_param = True
                break
    if not found_param:
        # completion for argument values by choices
        for cmd_param in ctx.command.params:
            if isinstance(cmd_param, Argument) and is_incomplete_argument(ctx.params, cmd_param):
                choices.extend(get_user_autocompletions(all_args, incomplete, ctx.command, cmd_param, override))
                found_param = True
                break

    if not found_param and isinstance(ctx.command, MultiCommand):
        # completion for any subcommands
        choices.extend(
            [cmd + " " for cmd in ctx.command.list_commands(ctx) if not ctx.command.get_command(ctx, cmd).hidden]
        )

    if (
        not start_of_option(incomplete)
        and ctx.parent is not None
        and isinstance(ctx.parent.command, MultiCommand)
        and ctx.parent.command.chain
    ):
        # completion for chained commands
        visible_commands = [
            cmd
            for cmd in ctx.parent.command.list_commands(ctx.parent)
            if not ctx.parent.command.get_command(ctx.parent, cmd).hidden
        ]
        remaining_commands = set(visible_commands) - set(ctx.parent.protected_args)
        choices.extend([cmd + " " for cmd in remaining_commands])

    for item in choices:
        if item.startswith(incomplete):
            yield item


def do_complete(cli, prog_name, override):
    cwords = split_arg_string(os.environ["COMP_WORDS"])
    cword = int(os.environ["COMP_CWORD"])
    args = cwords[1:cword]
    try:
        incomplete = cwords[cword]
    except IndexError:
        incomplete = ""

    for item in get_choices(cli, prog_name, args, incomplete, override):
        click.echo(item)


# Main function called from main.py at startup here
#
def main_bashcomplete(cmd, prog_name, override):
    """Internal handler for the bash completion support."""

    if "_BST_COMPLETION" in os.environ:
        do_complete(cmd, prog_name, override)
        return True

    return False
