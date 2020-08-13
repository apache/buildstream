import os
import sys
from functools import partial

import shutil
import click
from .. import _yaml
from .._exceptions import BstError, LoadError, AppError
from .complete import main_bashcomplete, complete_path, CompleteUnhandled
from ..types import _CacheBuildTrees, _SchedulerErrorAction, _PipelineSelection
from ..utils import UtilError


##################################################################
#              Helper classes and methods for Click              #
##################################################################


class FastEnumType(click.Choice):
    def __init__(self, enum, options=None):
        self._enum = enum

        if options is None:
            options = enum.values()
        else:
            options = [option.value for option in options]

        super().__init__(options)

    def convert(self, value, param, ctx):
        # This allows specifying default values as instances of the
        # enum
        if isinstance(value, self._enum):
            value = value.value

        return self._enum(super().convert(value, param, ctx))


##################################################################
#            Override of click's main entry point                #
##################################################################

# search_command()
#
# Helper function to get a command and context object
# for a given command.
#
# Args:
#    commands (list): A list of command words following `bst` invocation
#    context (click.Context): An existing toplevel context, or None
#
# Returns:
#    context (click.Context): The context of the associated command, or None
#
def search_command(args, *, context=None):
    if context is None:
        context = cli.make_context("bst", args, resilient_parsing=True)

    # Loop into the deepest command
    command = cli
    command_ctx = context
    for cmd in args:
        command = command_ctx.command.get_command(command_ctx, cmd)
        if command is None:
            return None
        command_ctx = command.make_context(command.name, [command.name], parent=command_ctx, resilient_parsing=True)

    return command_ctx


# Completion for completing command names as help arguments
def complete_commands(cmd, args, incomplete):
    command_ctx = search_command(args[1:])
    if command_ctx and command_ctx.command and isinstance(command_ctx.command, click.MultiCommand):
        return [
            subcommand + " "
            for subcommand in command_ctx.command.list_commands(command_ctx)
            if not command_ctx.command.get_command(command_ctx, subcommand).hidden
        ]

    return []


# Special completion for completing the bst elements in a project dir
def complete_target(args, incomplete):
    """
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text to autocomplete
    :return: all the possible user-specified completions for the param
    """

    from .. import utils

    project_conf = "project.conf"

    # First resolve the directory, in case there is an
    # active --directory/-C option
    #
    base_directory = "."
    idx = -1
    try:
        idx = args.index("-C")
    except ValueError:
        try:
            idx = args.index("--directory")
        except ValueError:
            pass

    if idx >= 0 and len(args) > idx + 1:
        base_directory = args[idx + 1]
    else:
        # Check if this directory or any of its parent directories
        # contain a project config file
        base_directory, _ = utils._search_upward_for_files(base_directory, [project_conf])

    if base_directory is None:
        # No project_conf was found in base_directory or its parents, no need
        # to try loading any project conf and avoid os.path NoneType TypeError.
        return []
    else:
        project_file = os.path.join(base_directory, project_conf)
        try:
            project = _yaml.load(project_file, shortname=project_conf)
        except LoadError:
            # If there is no project conf in context, just dont
            # even bother trying to complete anything.
            return []

    # The project is not required to have an element-path
    element_directory = project.get_str("element-path", default="")

    # If a project was loaded, use its element-path to
    # adjust our completion's base directory
    if element_directory:
        base_directory = os.path.join(base_directory, element_directory)

    complete_list = []
    for p in complete_path("File", incomplete, base_directory=base_directory):
        if p.endswith(".bst ") or p.endswith("/"):
            complete_list.append(p)
    return complete_list


def complete_artifact(orig_args, args, incomplete):
    from .._context import Context

    with Context(use_casd=False) as ctx:

        config = None
        if orig_args:
            for i, arg in enumerate(orig_args):
                if arg in ("-c", "--config"):
                    try:
                        config = orig_args[i + 1]
                    except IndexError:
                        pass
        if args:
            for i, arg in enumerate(args):
                if arg in ("-c", "--config"):
                    try:
                        config = args[i + 1]
                    except IndexError:
                        pass
        ctx.load(config)

        # element targets are valid artifact names
        complete_list = complete_target(args, incomplete)
        complete_list.extend(ref for ref in ctx.artifactcache.list_artifacts() if ref.startswith(incomplete))

        return complete_list


def override_completions(orig_args, cmd, cmd_param, args, incomplete):
    """
    :param orig_args: original, non-completion args
    :param cmd_param: command definition
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text to autocomplete
    :return: all the possible user-specified completions for the param
    """

    if cmd.name == "help":
        return complete_commands(cmd, args, incomplete)

    # We can't easily extend click's data structures without
    # modifying click itself, so just do some weak special casing
    # right here and select which parameters we want to handle specially.
    if isinstance(cmd_param.type, click.Path):
        if cmd_param.name == "elements" or cmd_param.name == "element" or cmd_param.name == "except_":
            return complete_target(args, incomplete)
        if cmd_param.name == "artifacts" or cmd_param.name == "target":
            return complete_artifact(orig_args, args, incomplete)

    raise CompleteUnhandled()


def validate_output_streams():
    if sys.platform == "win32":
        # Windows does not support 'fcntl', the module is unavailable there as
        # of Python 3.7, therefore early-out here.
        return

    import fcntl

    for stream in (sys.stdout, sys.stderr):
        fileno = stream.fileno()
        flags = fcntl.fcntl(fileno, fcntl.F_GETFL)
        if flags & os.O_NONBLOCK:
            click.echo("{} is currently set to O_NONBLOCK, try opening a new shell".format(stream.name), err=True)
            sys.exit(-1)


def override_main(self, args=None, prog_name=None, complete_var=None, standalone_mode=True, **extra):

    # Hook for the Bash completion.  This only activates if the Bash
    # completion is actually enabled, otherwise this is quite a fast
    # noop.
    if main_bashcomplete(self, prog_name, partial(override_completions, args)):

        # If we're running tests we cant just go calling exit()
        # from the main process.
        #
        # The below is a quicker exit path for the sake
        # of making completions respond faster.
        if "BST_TEST_SUITE" not in os.environ:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)

        # Regular client return for test cases
        return

    # Check output file descriptor at earliest opportunity, to
    # provide a reasonable error message instead of a stack trace
    # in the case that it is non-blocking.
    validate_output_streams()

    original_main(self, args=args, prog_name=prog_name, complete_var=None, standalone_mode=standalone_mode, **extra)


original_main = click.BaseCommand.main
# Disable type checking since mypy doesn't support assigning to a method.
# See https://github.com/python/mypy/issues/2427.
click.BaseCommand.main = override_main  # type: ignore


##################################################################
#                          Main Options                          #
##################################################################
def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    from .. import __version__

    click.echo(__version__)
    ctx.exit()


@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--version", is_flag=True, callback=print_version, expose_value=False, is_eager=True)
@click.option(
    "--config", "-c", type=click.Path(exists=True, dir_okay=False, readable=True), help="Configuration file to use"
)
@click.option(
    "--directory",
    "-C",
    default=None,  # Set to os.getcwd() later.
    type=click.Path(file_okay=False, readable=True),
    help="Project directory (default: current directory)",
)
@click.option(
    "--on-error",
    default=None,
    type=FastEnumType(_SchedulerErrorAction),
    help="What to do when an error is encountered",
)
@click.option("--fetchers", type=click.INT, default=None, help="Maximum simultaneous download tasks")
@click.option("--builders", type=click.INT, default=None, help="Maximum simultaneous build tasks")
@click.option("--pushers", type=click.INT, default=None, help="Maximum simultaneous upload tasks")
@click.option(
    "--max-jobs", type=click.INT, default=None, help="Number of parallel jobs allowed for a given build task"
)
@click.option("--network-retries", type=click.INT, default=None, help="Maximum retries for network tasks")
@click.option(
    "--no-interactive", is_flag=True, help="Force non interactive mode, otherwise this is automatically decided"
)
@click.option("--verbose/--no-verbose", default=None, help="Be extra verbose")
@click.option("--debug/--no-debug", default=None, help="Print debugging output")
@click.option("--error-lines", type=click.INT, default=None, help="Maximum number of lines to show from a task log")
@click.option(
    "--message-lines", type=click.INT, default=None, help="Maximum number of lines to show in a detailed message"
)
@click.option(
    "--log-file",
    type=click.File(mode="w", encoding="UTF-8"),
    help="A file to store the main log (allows storing the main log while in interactive mode)",
)
@click.option("--colors/--no-colors", default=None, help="Force enable/disable ANSI color codes in output")
@click.option(
    "--strict/--no-strict",
    default=None,
    is_flag=True,
    help="Elements must be rebuilt when their dependencies have changed",
)
@click.option(
    "--option",
    "-o",
    type=click.Tuple([str, str]),
    multiple=True,
    metavar="OPTION VALUE",
    help="Specify a project option",
)
@click.option("--default-mirror", default=None, help="The mirror to fetch from first, before attempting other mirrors")
@click.option(
    "--pull-buildtrees",
    is_flag=True,
    default=None,
    help="Include an element's build tree when pulling remote element artifacts",
)
@click.option(
    "--cache-buildtrees",
    default=None,
    type=FastEnumType(_CacheBuildTrees),
    help="Cache artifact build tree content on creation",
)
@click.pass_context
def cli(context, **kwargs):
    """Build and manipulate BuildStream projects

    Most of the main options override options in the
    user preferences configuration file.
    """

    from .app import App

    # Create the App, giving it the main arguments
    context.obj = App.create(dict(kwargs))
    context.call_on_close(context.obj.cleanup)

    # Configure colors
    context.color = context.obj.colors


##################################################################
#                           Help Command                         #
##################################################################
@cli.command(name="help", short_help="Print usage information", context_settings={"help_option_names": []})
@click.argument("command", nargs=-1, metavar="COMMAND")
@click.pass_context
def help_command(ctx, command):
    """Print usage information about a given command
    """
    command_ctx = search_command(command, context=ctx.parent)
    if not command_ctx:
        click.echo("Not a valid command: '{} {}'".format(ctx.parent.info_name, " ".join(command)), err=True)
        sys.exit(-1)

    click.echo(command_ctx.command.get_help(command_ctx), err=True)

    # Hint about available sub commands
    if isinstance(command_ctx.command, click.MultiCommand):
        detail = " "
        if command:
            detail = " {} ".format(" ".join(command))
        click.echo(
            "\nFor usage on a specific command: {} help{}COMMAND".format(ctx.parent.info_name, detail), err=True
        )


##################################################################
#                           Init Command                         #
##################################################################
@cli.command(short_help="Initialize a new BuildStream project")
@click.option("--project-name", type=click.STRING, help="The project name to use")
@click.option(
    "--min-version", type=click.STRING, default="2.0", show_default=True, help="The required format version",
)
@click.option(
    "--element-path",
    type=click.Path(),
    default="elements",
    show_default=True,
    help="The subdirectory to store elements in",
)
@click.option("--force", "-f", is_flag=True, help="Allow overwriting an existing project.conf")
@click.argument("target-directory", nargs=1, required=False, type=click.Path(file_okay=False, writable=True))
@click.pass_obj
def init(app, project_name, min_version, element_path, force, target_directory):
    """Initialize a new BuildStream project

    Creates a new BuildStream project.conf in the project
    directory.

    Unless `--project-name` is specified, this will be an
    interactive session.
    """
    app.init_project(project_name, min_version, element_path, force, target_directory)


##################################################################
#                          Build Command                         #
##################################################################
@cli.command(short_help="Build elements in a pipeline")
@click.option(
    "--deps",
    "-d",
    default=None,
    type=FastEnumType(
        _PipelineSelection, [_PipelineSelection.BUILD, _PipelineSelection.PLAN, _PipelineSelection.ALL],
    ),
    help="The dependencies to build",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote cache (defaults to the first configured cache)"
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def build(app, elements, deps, remote):
    """Build elements in a pipeline

    Specifying no elements will result in building the default targets
    of the project. If no default targets are configured, all project
    elements will be built.

    When this command is executed from a workspace directory, the default
    is to build the workspace element.

    Specify `--deps` to control which dependencies to build:

    \b
        plan:  Only dependencies required for the build plan
        build: Build time dependencies, excluding the element itself
        all:   All dependencies
    """
    with app.initialized(session_name="Build"):
        ignore_junction_targets = False

        if deps is None:
            deps = app.context.build_dependencies

        if not elements:
            elements = app.project.get_default_targets()
            # Junction elements cannot be built, exclude them from default targets
            ignore_junction_targets = True

        app.stream.build(elements, selection=deps, ignore_junction_targets=ignore_junction_targets, remote=remote)


##################################################################
#                           Show Command                         #
##################################################################
@cli.command(short_help="Show elements in the pipeline")
@click.option(
    "--except", "except_", multiple=True, type=click.Path(readable=False), help="Except certain dependencies"
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.ALL,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [
            _PipelineSelection.NONE,
            _PipelineSelection.PLAN,
            _PipelineSelection.RUN,
            _PipelineSelection.BUILD,
            _PipelineSelection.ALL,
        ],
    ),
    help="The dependencies to show",
)
@click.option(
    "--order",
    default="stage",
    show_default=True,
    type=click.Choice(["stage", "alpha"]),
    help="Staging or alphabetic ordering of dependencies",
)
@click.option(
    "--format",
    "-f",
    "format_",
    metavar="FORMAT",
    default=None,
    type=click.STRING,
    help="Format string for each element",
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def show(app, elements, deps, except_, order, format_):
    """Show elements in the pipeline

    Specifying no elements will result in showing the default targets
    of the project. If no default targets are configured, all project
    elements will be shown.

    When this command is executed from a workspace directory, the default
    is to show the workspace element.

    By default this will show all of the dependencies of the
    specified target element.

    Specify ``--deps`` to control which elements to show:

    \b
        none:  No dependencies, just the element itself
        plan:  Dependencies required for a build plan
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies

    **FORMAT**

    The ``--format`` option controls what should be printed for each element,
    the following symbols can be used in the format string:

    \b
        %{name}           The element name
        %{key}            The abbreviated cache key (if all sources are consistent)
        %{full-key}       The full cache key (if all sources are consistent)
        %{state}          cached, buildable, waiting, inconsistent or junction
        %{config}         The element configuration
        %{vars}           Variable configuration
        %{env}            Environment settings
        %{public}         Public domain data
        %{workspaced}     If the element is workspaced
        %{workspace-dirs} A list of workspace directories
        %{deps}           A list of all dependencies
        %{build-deps}     A list of build dependencies
        %{runtime-deps}   A list of runtime dependencies

    The value of the %{symbol} without the leading '%' character is understood
    as a pythonic formatting string, so python formatting features apply,
    example:

    \b
        bst show target.bst --format \\
            'Name: %{name: ^20} Key: %{key: ^8} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        bst show target.bst --format \\
            $'---------- %{name} ----------\\n%{vars}'
    """
    with app.initialized():
        if not elements:
            elements = app.project.get_default_targets()

        dependencies = app.stream.load_selection(elements, selection=deps, except_targets=except_)

        if order == "alpha":
            dependencies = sorted(dependencies)

        if not format_:
            format_ = app.context.log_element_format

        report = app.logger.show_pipeline(dependencies, format_)
        click.echo(report)


##################################################################
#                          Shell Command                         #
##################################################################
@cli.command(short_help="Shell into an element's sandbox environment")
@click.option("--build", "-b", "build_", is_flag=True, help="Stage dependencies and sources to build")
@click.option(
    "--mount",
    type=click.Tuple([click.Path(exists=True), str]),
    multiple=True,
    metavar="HOSTPATH PATH",
    help="Mount a file or directory into the sandbox",
)
@click.option("--isolate", is_flag=True, help="Create an isolated build sandbox")
@click.option(
    "--use-buildtree",
    "-t",
    "cli_buildtree",
    type=click.Choice(["ask", "try", "always", "never"]),
    default="ask",
    show_default=True,
    help=(
        "Stage a buildtree. If `always` is set, will always fail to "
        "build if a buildtree is not available."
        " --pull and pull-buildtrees configuration is needed "
        "if trying to query for remotely cached buildtrees."
    ),
)
@click.option("--pull", "pull_", is_flag=True, help="Attempt to pull missing or incomplete artifacts")
@click.argument("element", required=False, type=click.Path(readable=False))
@click.argument("command", type=click.STRING, nargs=-1)
@click.pass_obj
def shell(app, element, mount, isolate, build_, cli_buildtree, pull_, command):
    """Run a command in the target element's sandbox environment

    When this command is executed from a workspace directory, the default
    is to shell into the workspace element.

    This will stage a temporary sysroot for running the target
    element, assuming it has already been built and all required
    artifacts are in the local cache.

    Use '--' to separate a command from the options to bst,
    otherwise bst may respond to them instead. e.g.

    \b
        bst shell example.bst -- df -h

    Use the --build option to create a temporary sysroot for
    building the element instead.

    If no COMMAND is specified, the default is to attempt
    to run an interactive shell.
    """
    from ..element import Scope
    from .._project import HostMount

    scope = Scope.BUILD if build_ else Scope.RUN

    # We may need to fetch dependency artifacts if we're pulling the artifact
    selection = _PipelineSelection.ALL if pull_ else _PipelineSelection.NONE
    use_buildtree = None

    with app.initialized():
        if not element:
            element = app.project.get_default_target()
            if not element:
                raise AppError('Missing argument "ELEMENT".')

        elements = app.stream.load_selection((element,), selection=selection, use_artifact_config=True)

        # last one will be the element we want to stage, previous ones are
        # elements to try and pull
        element = elements[-1]
        pull_dependencies = elements[:-1] if pull_ else None

        element_name = element._get_full_name()
        element_key = element._get_display_key()

        prompt = app.shell_prompt(element_name, element_key)
        mounts = [HostMount(path, host_path) for host_path, path in mount]

        artifact_is_cached = element._cached()
        buildtree_is_cached = element._cached_buildtree()
        buildtree_exists = element._buildtree_exists()
        can_attempt_pull = app.context.pull_buildtrees and pull_

        if cli_buildtree in ("always", "try"):
            if buildtree_is_cached:
                use_buildtree = cli_buildtree
            # If element is already cached, we can check the proto to see if the buildtree existed
            elif artifact_is_cached:
                if not buildtree_exists:
                    if cli_buildtree == "always":
                        # Exit early if it won't be possible to even fetch a buildtree with always option
                        raise AppError("Artifact was created without buildtree, unable to launch shell with it")
                    click.echo(
                        "WARNING: Artifact created without buildtree, shell will be loaded without it", err=True
                    )
                elif can_attempt_pull:
                    use_buildtree = cli_buildtree
                    click.echo(
                        "WARNING: buildtree is not cached locally but did exist, will attempt to pull from available remotes",
                        err=True,
                    )
                else:
                    if cli_buildtree == "always":
                        # Exit early if it won't be possible to perform a fetch as pull semantics aren't present
                        raise AppError(
                            "Artifact has a buildtree but it isn't cached. Can be retried with --pull and pull-buildtrees configured"
                        )
                    click.echo("WARNING: buildtree is not cached locally, shell will be loaded without it", err=True)
            # If element isn't cached at all, we can't check the proto to see if it existed so can't exit early
            elif can_attempt_pull:
                use_buildtree = cli_buildtree
                if use_buildtree == "always":
                    click.echo(
                        "WARNING: Element is not cached so buildtree status unknown, will attempt to pull from available remotes",
                        err=True,
                    )
            else:
                if cli_buildtree == "always":
                    # Exit early as there is no buildtree locally & can_attempt_pull is False
                    raise AppError(
                        "Artifact not cached locally. Can be retried with --pull and pull-buildtrees configured"
                    )
                click.echo("WARNING: buildtree is not cached locally, shell will be loaded without it", err=True)
        else:
            # If the value has defaulted to ask and in non interactive mode, don't consider the buildtree, this
            # being the default behaviour of the command
            if app.interactive and cli_buildtree == "ask":
                if buildtree_is_cached and bool(click.confirm("Do you want to use the cached buildtree?")):
                    use_buildtree = "always"
                elif can_attempt_pull:
                    # If buildtree not cached, check if it's worth presenting the user a dialogue
                    message = None
                    if artifact_is_cached:
                        if buildtree_exists:
                            message = "Buildtree not cached but can be pulled if in available remotes, do you want to use it?"
                    else:
                        message = "Element is not cached so buildtree status unknown, do you want to pull and use it?"
                    if message:
                        try:
                            choice = click.prompt(
                                message, type=click.Choice(["try", "always", "never"]), err=True, show_choices=True,
                            )
                        except click.Abort:
                            click.echo("Aborting", err=True)
                            sys.exit(-1)

                        if choice != "never":
                            use_buildtree = choice

        # Raise warning if the element is cached in a failed state
        if use_buildtree and element._cached_failure():
            click.echo("WARNING: using a buildtree from a failed build.", err=True)

        try:
            exitcode = app.stream.shell(
                element,
                scope,
                prompt,
                mounts=mounts,
                isolate=isolate,
                command=command,
                usebuildtree=use_buildtree,
                pull_dependencies=pull_dependencies,
            )
        except BstError as e:
            raise AppError("Error launching shell: {}".format(e), detail=e.detail) from e

    # If there were no errors, we return the shell's exit code here.
    sys.exit(exitcode)


##################################################################
#                        Source Command                          #
##################################################################
@cli.group(short_help="Manipulate sources for an element")
def source():
    """Manipulate sources for an element"""


##################################################################
#                     Source Fetch Command                       #
##################################################################
@source.command(name="fetch", short_help="Fetch sources in a pipeline")
@click.option(
    "--except",
    "except_",
    multiple=True,
    type=click.Path(readable=False),
    help="Except certain dependencies from fetching",
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.PLAN,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [
            _PipelineSelection.PLAN,
            _PipelineSelection.NONE,
            _PipelineSelection.BUILD,
            _PipelineSelection.RUN,
            _PipelineSelection.ALL,
        ],
    ),
    help="The dependencies to fetch",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote source cache (defaults to the first configured cache)"
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def source_fetch(app, elements, deps, except_, remote):
    """Fetch sources required to build the pipeline

    Specifying no elements will result in fetching the default targets
    of the project. If no default targets are configured, all project
    elements will be fetched.

    When this command is executed from a workspace directory, the default
    is to fetch the workspace element.

    By default this will only try to fetch sources which are
    required for the build plan of the specified target element,
    omitting sources for any elements which are already built
    and available in the artifact cache.

    Specify `--deps` to control which sources to fetch:

    \b
        none:  No dependencies, just the element itself
        plan:  Only dependencies required for the build plan
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies
    """
    with app.initialized(session_name="Fetch"):
        if not elements:
            elements = app.project.get_default_targets()

        app.stream.fetch(elements, selection=deps, except_targets=except_, remote=remote)


##################################################################
#                      Source Push Command                       #
##################################################################
@source.command(name="push", short_help="Push sources in a pipeline")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [
            _PipelineSelection.NONE,
            _PipelineSelection.PLAN,
            _PipelineSelection.BUILD,
            _PipelineSelection.RUN,
            _PipelineSelection.ALL,
        ],
    ),
    help="The dependencies to push",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote source cache (defaults to the first configured cache)"
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def source_push(app, elements, deps, remote):
    """Push sources required to build the pipeline

    Specifying no elements will result in pushing the sources of the default
    targets of the project. If no default targets are configured, sources of
    all project elements will be pushed.

    When this command is executed from a workspace directory, the default
    is to push the sources of the workspace element.

    Specify `--deps` to control which sources to fetch:

    \b
        none:  No dependencies, just the element itself
        plan:  Only dependencies required for the build plan
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies
    """
    with app.initialized(session_name="Push"):
        if not elements:
            elements = app.project.get_default_targets()

        app.stream.source_push(elements, selection=deps, remote=remote)


##################################################################
#                     Source Track Command                       #
##################################################################
@source.command(name="track", short_help="Track new source references")
@click.option(
    "--except",
    "except_",
    multiple=True,
    type=click.Path(readable=False),
    help="Except certain dependencies from tracking",
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.BUILD, _PipelineSelection.RUN, _PipelineSelection.ALL, _PipelineSelection.NONE],
    ),
    help="The dependencies to track",
)
@click.option("--cross-junctions", "-J", is_flag=True, help="Allow crossing junction boundaries")
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def source_track(app, elements, deps, except_, cross_junctions):
    """Consults the specified tracking branches for new versions available
    to build and updates the project with any newly available references.

    Specifying no elements will result in tracking the default targets
    of the project. If no default targets are configured, all project
    elements will be tracked.

    When this command is executed from a workspace directory, the default
    is to track the workspace element.

    If no default is declared, all elements in the project will be tracked

    By default this will track just the specified element, but you can also
    update a whole tree of dependencies in one go.

    Specify `--deps` to control which sources to track:

    \b
        none:  No dependencies, just the specified elements
        all:   All dependencies of all specified elements
    """
    with app.initialized(session_name="Track"):
        if not elements:
            elements = app.project.get_default_targets()

        # Substitute 'none' for 'redirect' so that element redirections
        # will be done
        if deps == _PipelineSelection.NONE:
            deps = _PipelineSelection.REDIRECT
        app.stream.track(elements, selection=deps, except_targets=except_, cross_junctions=cross_junctions)


##################################################################
#                  Source Checkout Command                      #
##################################################################
@source.command(name="checkout", short_help="Checkout sources of an element")
@click.option("--force", "-f", is_flag=True, help="Allow files to be overwritten")
@click.option(
    "--except", "except_", multiple=True, type=click.Path(readable=False), help="Except certain dependencies"
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.BUILD, _PipelineSelection.NONE, _PipelineSelection.RUN, _PipelineSelection.ALL],
    ),
    help="The dependencies whose sources to checkout",
)
@click.option(
    "--tar",
    default=None,
    metavar="LOCATION",
    type=click.Path(),
    help="Create a tarball containing the sources instead " "of a file tree.",
)
@click.option(
    "--compression",
    default=None,
    type=click.Choice(["gz", "xz", "bz2"]),
    help="The compression option of the tarball created.",
)
@click.option("--include-build-scripts", "build_scripts", is_flag=True)
@click.option(
    "--directory",
    default="source-checkout",
    type=click.Path(file_okay=False),
    help="The directory to checkout the sources to",
)
@click.argument("element", required=False, type=click.Path(readable=False))
@click.pass_obj
def source_checkout(app, element, directory, force, deps, except_, tar, compression, build_scripts):
    """Checkout sources of an element to the specified location

    When this command is executed from a workspace directory, the default
    is to checkout the sources of the workspace element.
    """

    if tar and directory != "source-checkout":
        click.echo("ERROR: options --directory and --tar conflict", err=True)
        sys.exit(-1)

    if compression and not tar:
        click.echo("ERROR: --compression specified without --tar", err=True)
        sys.exit(-1)

    # Set the location depending on whether --tar/--directory were specified
    # Note that if unset, --directory defaults to "source-checkout"
    location = tar if tar else directory

    with app.initialized():
        if not element:
            element = app.project.get_default_target()
            if not element:
                raise AppError('Missing argument "ELEMENT".')

        app.stream.source_checkout(
            element,
            location=location,
            force=force,
            deps=deps,
            except_targets=except_,
            tar=bool(tar),
            compression=compression,
            include_build_scripts=build_scripts,
        )


##################################################################
#                      Workspace Command                         #
##################################################################
@cli.group(short_help="Manipulate developer workspaces")
def workspace():
    """Manipulate developer workspaces"""


##################################################################
#                     Workspace Open Command                     #
##################################################################
@workspace.command(name="open", short_help="Open a new workspace")
@click.option("--no-checkout", is_flag=True, help="Do not checkout the source, only link to the given directory")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="The workspace will be created even if the directory in which it will be created is not empty "
    + "or if a workspace for that element already exists",
)
@click.option(
    "--directory",
    type=click.Path(file_okay=False),
    default=None,
    help="Only for use when a single Element is given: Set the directory to use to create the workspace",
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False), required=True)
@click.pass_obj
def workspace_open(app, no_checkout, force, directory, elements):
    """Open a workspace for manual source modification"""

    with app.initialized():
        app.stream.workspace_open(elements, no_checkout=no_checkout, force=force, custom_dir=directory)


##################################################################
#                     Workspace Close Command                    #
##################################################################
@workspace.command(name="close", short_help="Close workspaces")
@click.option("--remove-dir", is_flag=True, help="Remove the path that contains the closed workspace")
@click.option("--all", "-a", "all_", is_flag=True, help="Close all open workspaces")
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def workspace_close(app, remove_dir, all_, elements):
    """Close a workspace"""

    with app.initialized():
        if not (all_ or elements):
            # NOTE: I may need to revisit this when implementing multiple projects
            # opening one workspace.
            element = app.project.get_default_target()
            if element:
                elements = (element,)
            else:
                raise AppError("No elements specified")

        # Early exit if we specified `all` and there are no workspaces
        if all_ and not app.stream.workspace_exists():
            click.echo("No open workspaces to close", err=True)
            sys.exit(0)

        if all_:
            elements = [element_name for element_name, _ in app.context.get_workspaces().list()]

        elements = app.stream.redirect_element_names(elements)

        # Check that the workspaces in question exist, and that it's safe to
        # remove them.
        nonexisting = []
        for element_name in elements:
            if not app.stream.workspace_exists(element_name):
                nonexisting.append(element_name)
        if nonexisting:
            raise AppError("Workspace does not exist", detail="\n".join(nonexisting))

        for element_name in elements:
            app.stream.workspace_close(element_name, remove_dir=remove_dir)


##################################################################
#                     Workspace Reset Command                    #
##################################################################
@workspace.command(name="reset", short_help="Reset a workspace to its original state")
@click.option(
    "--soft",
    is_flag=True,
    help="Mark workspace to re-execute configuration steps (if any) on next build. Does not alter workspace contents.",
)
@click.option("--all", "-a", "all_", is_flag=True, help="Reset all open workspaces")
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def workspace_reset(app, soft, all_, elements):
    """Reset a workspace to its original state"""

    # Check that the workspaces in question exist
    with app.initialized():

        if not (all_ or elements):
            element = app.project.get_default_target()
            if element:
                elements = (element,)
            else:
                raise AppError("No elements specified to reset")

        if all_ and not app.stream.workspace_exists():
            raise AppError("No open workspaces to reset")

        if all_:
            elements = tuple(element_name for element_name, _ in app.context.get_workspaces().list())

        app.stream.workspace_reset(elements, soft=soft)


##################################################################
#                     Workspace List Command                     #
##################################################################
@workspace.command(name="list", short_help="List open workspaces")
@click.pass_obj
def workspace_list(app):
    """List open workspaces"""

    with app.initialized():
        app.stream.workspace_list()


#############################################################
#                     Artifact Commands                     #
#############################################################
@cli.group(short_help="Manipulate cached artifacts.")
def artifact():
    """Manipulate cached artifacts

    Some subcommands take artifact references as arguments. Artifacts
    can be specified in two ways:

    \b
    - artifact refs: triples of the form <project name>/<element name>/<cache key>
    - element paths

    When elements are given, the artifact corresponding to the element is used.

    The commands also support shell-style wildcard expansion: `?` matches a
    single character, and `*` matches zero or more. The patterns are matched
    against artifact refs by default. If the pattern ends with `.bst` then
    it matches element paths instead. Some example arguments are:

    \b
    - `myproject/hello/8276376b077eda104c812e6ec2f488c7c9eea211ce572c83d734c10bf241209f`
    - `myproject/he*/827637*`
    - `*.bst` (all elements)
    - `myproject/*` (all artifacts from myproject)
    """
    # Note that the backticks in the above docstring are important for the
    # generated docs. When sphinx is generating rst output from the help output
    # of this command, the asterisks will be interpreted as emphasis tokens if
    # they are not somehow escaped.


#############################################################
#                    Artifact show Command                  #
#############################################################
@artifact.command(name="show", short_help="Show the cached state of artifacts")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.BUILD, _PipelineSelection.RUN, _PipelineSelection.ALL, _PipelineSelection.NONE],
    ),
    help="The dependencies we also want to show",
)
@click.argument("artifacts", type=click.Path(), nargs=-1)
@click.pass_obj
def artifact_show(app, deps, artifacts):
    """show the cached state of artifacts"""
    with app.initialized():
        targets = app.stream.artifact_show(artifacts, selection=deps)
        click.echo(app.logger.show_state_of_artifacts(targets))
        sys.exit(0)


#####################################################################
#                     Artifact Checkout Command                     #
#####################################################################
@artifact.command(name="checkout", short_help="Checkout contents of an artifact")
@click.option("--force", "-f", is_flag=True, help="Allow files to be overwritten")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.RUN,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.RUN, _PipelineSelection.BUILD, _PipelineSelection.NONE, _PipelineSelection.ALL],
    ),
    help="The dependencies to checkout",
)
@click.option("--integrate/--no-integrate", default=None, is_flag=True, help="Whether to run integration commands")
@click.option("--hardlinks", is_flag=True, help="Checkout hardlinks instead of copying if possible")
@click.option(
    "--tar",
    default=None,
    metavar="LOCATION",
    type=click.Path(),
    help="Create a tarball from the artifact contents instead "
    "of a file tree. If LOCATION is '-', the tarball "
    "will be dumped to the standard output.",
)
@click.option(
    "--compression",
    default=None,
    type=click.Choice(["gz", "xz", "bz2"]),
    help="The compression option of the tarball created.",
)
@click.option("--pull", "pull_", is_flag=True, help="Pull the artifact if it's missing or incomplete.")
@click.option(
    "--directory", default=None, type=click.Path(file_okay=False), help="The directory to checkout the artifact to"
)
@click.argument("target", required=False, type=click.Path(readable=False))
@click.pass_obj
def artifact_checkout(app, force, deps, integrate, hardlinks, tar, compression, pull_, directory, target):
    """Checkout contents of an artifact

    When this command is executed from a workspace directory, the default
    is to checkout the artifact of the workspace element.
    """
    from .. import utils

    if hardlinks and tar:
        click.echo("ERROR: options --hardlinks and --tar conflict", err=True)
        sys.exit(-1)

    if tar and directory:
        click.echo("ERROR: options --directory and --tar conflict", err=True)
        sys.exit(-1)

    if not tar:
        if compression:
            click.echo("ERROR: --compression can only be provided if --tar is provided", err=True)
            sys.exit(-1)
    else:
        location = tar
        try:
            inferred_compression = utils._get_compression(tar)
        except UtilError as e:
            click.echo("ERROR: Invalid file extension given with '--tar': {}".format(e), err=True)
            sys.exit(-1)
        if compression and inferred_compression != "" and inferred_compression != compression:
            click.echo(
                "WARNING: File extension and compression differ."
                "File extension has been overridden by --compression",
                err=True,
            )
        if not compression:
            compression = inferred_compression

    with app.initialized():
        if not target:
            target = app.project.get_default_target()
            if not target:
                raise AppError('Missing argument "ELEMENT".')

        if not tar:
            if directory is None:
                location = os.path.abspath(os.path.join(os.getcwd(), target))
                if location[-4:] == ".bst":
                    location = location[:-4]
            else:
                location = directory

        app.stream.checkout(
            target,
            location=location,
            force=force,
            selection=deps,
            integrate=True if integrate is None else integrate,
            hardlinks=hardlinks,
            pull=pull_,
            compression=compression,
            tar=bool(tar),
        )


################################################################
#                     Artifact Pull Command                    #
################################################################
@artifact.command(name="pull", short_help="Pull a built artifact")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.BUILD, _PipelineSelection.NONE, _PipelineSelection.RUN, _PipelineSelection.ALL],
    ),
    help="The dependency artifacts to pull",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote cache (defaults to the first configured cache)"
)
@click.argument("artifacts", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def artifact_pull(app, artifacts, deps, remote):
    """Pull a built artifact from the configured remote artifact cache.

    Specifying no elements will result in pulling the default targets
    of the project. If no default targets are configured, all project
    elements will be pulled.

    When this command is executed from a workspace directory, the default
    is to pull the workspace element.

    By default the artifact will be pulled one of the configured caches
    if possible, following the usual priority order. If the `--remote` flag
    is given, only the specified cache will be queried.

    Specify `--deps` to control which artifacts to pull:

    \b
        none:  No dependencies, just the element itself
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies
    """

    with app.initialized(session_name="Pull"):
        ignore_junction_targets = False

        if not artifacts:
            artifacts = app.project.get_default_targets()
            # Junction elements cannot be pulled, exclude them from default targets
            ignore_junction_targets = True

        app.stream.pull(artifacts, selection=deps, remote=remote, ignore_junction_targets=ignore_junction_targets)


##################################################################
#                     Artifact Push Command                      #
##################################################################
@artifact.command(name="push", short_help="Push a built artifact")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.BUILD, _PipelineSelection.NONE, _PipelineSelection.RUN, _PipelineSelection.ALL],
    ),
    help="The dependencies to push",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote cache (defaults to the first configured cache)"
)
@click.argument("artifacts", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def artifact_push(app, artifacts, deps, remote):
    """Push a built artifact to a remote artifact cache.

    Specifying no elements will result in pushing the default targets
    of the project. If no default targets are configured, all project
    elements will be pushed.

    When this command is executed from a workspace directory, the default
    is to push the workspace element.

    The default destination is the highest priority configured cache. You can
    override this by passing a different cache URL with the `--remote` flag.

    If bst has been configured to include build trees on artifact pulls,
    an attempt will be made to pull any required build trees to avoid the
    skipping of partial artifacts being pushed.

    Specify `--deps` to control which artifacts to push:

    \b
        none:  No dependencies, just the element itself
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies
    """
    with app.initialized(session_name="Push"):
        ignore_junction_targets = False

        if not artifacts:
            artifacts = app.project.get_default_targets()
            # Junction elements cannot be pushed, exclude them from default targets
            ignore_junction_targets = True

        app.stream.push(artifacts, selection=deps, remote=remote, ignore_junction_targets=ignore_junction_targets)


################################################################
#                     Artifact Log Command                     #
################################################################
@artifact.command(name="log", short_help="Show logs of artifacts")
@click.option(
    "--out",
    type=click.Path(file_okay=True, writable=True),
    help="Output logs to individual files in the specified path. If absent, logs are written to stdout.",
)
@click.argument("artifacts", type=click.Path(), nargs=-1)
@click.pass_obj
def artifact_log(app, artifacts, out):
    """Show build logs of artifacts"""
    with app.initialized():
        artifact_logs = app.stream.artifact_log(artifacts)

        if not out:
            try:
                for log in list(artifact_logs.values()):
                    with open(log[0], "r") as f:
                        data = f.read()
                    click.echo_via_pager(data)
            except (OSError, FileNotFoundError):
                click.echo("Error: file cannot be opened", err=True)
                sys.exit(1)

        else:
            try:
                os.mkdir(out)
            except FileExistsError:
                click.echo("Error: {} already exists".format(out), err=True)
                sys.exit(1)

            for name, log_files in artifact_logs.items():
                if len(log_files) > 1:
                    os.mkdir(name)
                    for log in log_files:
                        dest = os.path.join(out, name, log)
                        shutil.copy(log, dest)
                    # make a dir and write in log files
                else:
                    log_name = os.path.splitext(name)[0] + ".log"
                    dest = os.path.join(out, log_name)
                    shutil.copy(log_files[0], dest)
                    # write a log file


################################################################
#                Artifact List-Contents Command                #
################################################################
@artifact.command(name="list-contents", short_help="List the contents of an artifact")
@click.option(
    "--long", "-l", "long_", is_flag=True, help="Provide more information about the contents of the artifact."
)
@click.argument("artifacts", type=click.Path(), nargs=-1)
@click.pass_obj
def artifact_list_contents(app, artifacts, long_):
    """List the contents of an artifact.

    Note that 'artifacts' can be element names, which must end in '.bst',
    or artifact references, which must be in the format `<project_name>/<element>/<key>`.

    """
    with app.initialized():
        elements_to_files = app.stream.artifact_list_contents(artifacts)
        if not elements_to_files:
            click.echo("None of the specified artifacts are cached.", err=True)
            sys.exit(1)
        else:
            click.echo(app.logger._pretty_print_dictionary(elements_to_files, long_))
            sys.exit(0)


###################################################################
#                     Artifact Delete Command                     #
###################################################################
@artifact.command(name="delete", short_help="Remove artifacts from the local cache")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(
        _PipelineSelection,
        [_PipelineSelection.NONE, _PipelineSelection.RUN, _PipelineSelection.BUILD, _PipelineSelection.ALL],
    ),
    help="The dependencies to delete",
)
@click.argument("artifacts", type=click.Path(), nargs=-1)
@click.pass_obj
def artifact_delete(app, artifacts, deps):
    """Remove artifacts from the local cache"""
    with app.initialized():
        app.stream.artifact_delete(artifacts, selection=deps)


##################################################################
#                      DEPRECATED Commands                       #
##################################################################

# XXX: The following commands are now obsolete, but they are kept
# here along with all the options so that we can provide nice error
# messages when they are called.
# Also, note that these commands are hidden from the top-level help.

##################################################################
#                          Fetch Command                         #
##################################################################
@cli.command(short_help="COMMAND OBSOLETE - Fetch sources in a pipeline", hidden=True)
@click.option(
    "--except",
    "except_",
    multiple=True,
    type=click.Path(readable=False),
    help="Except certain dependencies from fetching",
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.PLAN,
    show_default=True,
    type=FastEnumType(_PipelineSelection, [_PipelineSelection.NONE, _PipelineSelection.PLAN, _PipelineSelection.ALL]),
    help="The dependencies to fetch",
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def fetch(app, elements, deps, except_):
    click.echo("This command is now obsolete. Use `bst source fetch` instead.", err=True)
    sys.exit(1)


##################################################################
#                          Track Command                         #
##################################################################
@cli.command(short_help="COMMAND OBSOLETE - Track new source references", hidden=True)
@click.option(
    "--except",
    "except_",
    multiple=True,
    type=click.Path(readable=False),
    help="Except certain dependencies from tracking",
)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(_PipelineSelection, [_PipelineSelection.NONE, _PipelineSelection.ALL]),
    help="The dependencies to track",
)
@click.option("--cross-junctions", "-J", is_flag=True, help="Allow crossing junction boundaries")
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def track(app, elements, deps, except_, cross_junctions):
    click.echo("This command is now obsolete. Use `bst source track` instead.", err=True)
    sys.exit(1)


##################################################################
#                        Checkout Command                        #
##################################################################
@cli.command(short_help="COMMAND OBSOLETE - Checkout a built artifact", hidden=True)
@click.option("--force", "-f", is_flag=True, help="Allow files to be overwritten")
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.RUN,
    show_default=True,
    type=FastEnumType(_PipelineSelection, [_PipelineSelection.RUN, _PipelineSelection.BUILD, _PipelineSelection.NONE]),
    help="The dependencies to checkout",
)
@click.option("--integrate/--no-integrate", default=True, help="Run integration commands (default is to run commands)")
@click.option("--hardlinks", is_flag=True, help="Checkout hardlinks instead of copies (handle with care)")
@click.option(
    "--tar",
    is_flag=True,
    help="Create a tarball from the artifact contents instead "
    "of a file tree. If LOCATION is '-', the tarball "
    "will be dumped to the standard output.",
)
@click.argument("element", required=False, type=click.Path(readable=False))
@click.argument("location", type=click.Path(), required=False)
@click.pass_obj
def checkout(app, element, location, force, deps, integrate, hardlinks, tar):
    click.echo(
        "This command is now obsolete. Use `bst artifact checkout` instead "
        + "and use the --directory option to specify LOCATION",
        err=True,
    )
    sys.exit(1)


################################################################
#                          Pull Command                        #
################################################################
@cli.command(short_help="COMMAND OBSOLETE - Pull a built artifact", hidden=True)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(_PipelineSelection, [_PipelineSelection.NONE, _PipelineSelection.ALL]),
    help="The dependency artifacts to pull",
)
@click.option("--remote", "-r", help="The URL of the remote cache (defaults to the first configured cache)")
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def pull(app, elements, deps, remote):
    click.echo("This command is now obsolete. Use `bst artifact pull` instead.", err=True)
    sys.exit(1)


##################################################################
#                           Push Command                         #
##################################################################
@cli.command(short_help="COMMAND OBSOLETE - Push a built artifact", hidden=True)
@click.option(
    "--deps",
    "-d",
    default=_PipelineSelection.NONE,
    show_default=True,
    type=FastEnumType(_PipelineSelection, [_PipelineSelection.NONE, _PipelineSelection.ALL]),
    help="The dependencies to push",
)
@click.option(
    "--remote", "-r", default=None, help="The URL of the remote cache (defaults to the first configured cache)"
)
@click.argument("elements", nargs=-1, type=click.Path(readable=False))
@click.pass_obj
def push(app, elements, deps, remote):
    click.echo("This command is now obsolete. Use `bst artifact push` instead.", err=True)
    sys.exit(1)
