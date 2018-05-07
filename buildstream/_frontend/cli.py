import os
import sys

import click
from .. import _yaml
from .._exceptions import BstError, LoadError
from .._versions import BST_FORMAT_VERSION
from .complete import main_bashcomplete, complete_path, CompleteUnhandled


##################################################################
#            Override of click's main entry point                #
##################################################################

# Special completion for completing the bst elements in a project dir
def complete_target(args, incomplete):
    """
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text to autocomplete
    :return: all the possible user-specified completions for the param
    """

    # First resolve the directory, in case there is an
    # active --directory/-C option
    #
    base_directory = '.'
    idx = -1
    try:
        idx = args.index('-C')
    except ValueError:
        try:
            idx = args.index('--directory')
        except ValueError:
            pass

    if idx >= 0 and len(args) > idx + 1:
        base_directory = args[idx + 1]

    # Now parse the project.conf just to find the element path,
    # this is unfortunately a bit heavy.
    project_file = os.path.join(base_directory, 'project.conf')
    try:
        project = _yaml.load(project_file)
    except LoadError:
        # If there is no project directory in context, just dont
        # even bother trying to complete anything.
        return []

    # The project is not required to have an element-path
    element_directory = project.get('element-path')

    # If a project was loaded, use it's element-path to
    # adjust our completion's base directory
    if element_directory:
        base_directory = os.path.join(base_directory, element_directory)

    return complete_path("File", incomplete, base_directory=base_directory)


def override_completions(cmd_param, args, incomplete):
    """
    :param cmd_param: command definition
    :param args: full list of args typed before the incomplete arg
    :param incomplete: the incomplete text to autocomplete
    :return: all the possible user-specified completions for the param
    """

    # We can't easily extend click's data structures without
    # modifying click itself, so just do some weak special casing
    # right here and select which parameters we want to handle specially.
    if isinstance(cmd_param.type, click.Path) and \
       (cmd_param.name == 'elements' or
        cmd_param.name == 'element' or
        cmd_param.name == 'except_' or
        cmd_param.opts == ['--track'] or
        cmd_param.opts == ['--track-except']):
        return complete_target(args, incomplete)

    raise CompleteUnhandled()


def override_main(self, args=None, prog_name=None, complete_var=None,
                  standalone_mode=True, **extra):

    # Hook for the Bash completion.  This only activates if the Bash
    # completion is actually enabled, otherwise this is quite a fast
    # noop.
    if main_bashcomplete(self, prog_name, override_completions):

        # If we're running tests we cant just go calling exit()
        # from the main process.
        #
        # The below is a quicker exit path for the sake
        # of making completions respond faster.
        if 'BST_TEST_SUITE' not in os.environ:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)

        # Regular client return for test cases
        return

    original_main(self, args=args, prog_name=prog_name, complete_var=None,
                  standalone_mode=standalone_mode, **extra)


original_main = click.BaseCommand.main
click.BaseCommand.main = override_main


##################################################################
#                          Main Options                          #
##################################################################
def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    from .. import __version__
    click.echo(__version__)
    ctx.exit()


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--version', is_flag=True, callback=print_version,
              expose_value=False, is_eager=True)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(file_okay=False, readable=True),
              help="Project directory (default: current directory)")
@click.option('--on-error', default=None,
              type=click.Choice(['continue', 'quit', 'terminate']),
              help="What to do when an error is encountered")
@click.option('--fetchers', type=click.INT, default=None,
              help="Maximum simultaneous download tasks")
@click.option('--builders', type=click.INT, default=None,
              help="Maximum simultaneous build tasks")
@click.option('--pushers', type=click.INT, default=None,
              help="Maximum simultaneous upload tasks")
@click.option('--network-retries', type=click.INT, default=None,
              help="Maximum retries for network tasks")
@click.option('--no-interactive', is_flag=True, default=False,
              help="Force non interactive mode, otherwise this is automatically decided")
@click.option('--verbose/--no-verbose', default=None,
              help="Be extra verbose")
@click.option('--debug/--no-debug', default=None,
              help="Print debugging output")
@click.option('--error-lines', type=click.INT, default=None,
              help="Maximum number of lines to show from a task log")
@click.option('--message-lines', type=click.INT, default=None,
              help="Maximum number of lines to show in a detailed message")
@click.option('--log-file',
              type=click.File(mode='w', encoding='UTF-8'),
              help="A file to store the main log (allows storing the main log while in interactive mode)")
@click.option('--colors/--no-colors', default=None,
              help="Force enable/disable ANSI color codes in output")
@click.option('--strict/--no-strict', default=None, is_flag=True,
              help="Elements must be rebuilt when their dependencies have changed")
@click.option('--option', '-o', type=click.Tuple([str, str]), multiple=True, metavar='OPTION VALUE',
              help="Specify a project option")
@click.pass_context
def cli(context, **kwargs):
    """Build and manipulate BuildStream projects

    Most of the main options override options in the
    user preferences configuration file.
    """

    from .app import App

    # Create the App, giving it the main arguments
    context.obj = App(dict(kwargs))
    context.call_on_close(context.obj.cleanup)


##################################################################
#                           Init Command                         #
##################################################################
@cli.command(short_help="Initialize a new BuildStream project")
@click.option('--project-name', type=click.STRING,
              help="The project name to use")
@click.option('--format-version', type=click.INT, default=BST_FORMAT_VERSION,
              help="The required format version (default: {})".format(BST_FORMAT_VERSION))
@click.option('--element-path', type=click.Path(), default="elements",
              help="The subdirectory to store elements in (default: elements)")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Allow overwriting an existing project.conf")
@click.pass_obj
def init(app, project_name, format_version, element_path, force):
    """Initialize a new BuildStream project

    Creates a new BuildStream project.conf in the project
    directory.

    Unless `--project-name` is specified, this will be an
    interactive session.
    """
    app.init_project(project_name, format_version, element_path, force)


##################################################################
#                          Build Command                         #
##################################################################
@cli.command(short_help="Build elements in a pipeline")
@click.option('--all', 'all_', default=False, is_flag=True,
              help="Build elements that would not be needed for the current build plan")
@click.option('--track', 'track_', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Specify elements to track during the build. Can be used "
                   "repeatedly to specify multiple elements")
@click.option('--track-all', default=False, is_flag=True,
              help="Track all elements in the pipeline")
@click.option('--track-except', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Except certain dependencies from tracking")
@click.option('--track-cross-junctions', '-J', default=False, is_flag=True,
              help="Allow tracking to cross junction boundaries")
@click.option('--track-save', default=False, is_flag=True,
              help="Deprecated: This is ignored")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def build(app, elements, all_, track_, track_save, track_all, track_except, track_cross_junctions):
    """Build elements in a pipeline"""

    if (track_except or track_cross_junctions) and not (track_ or track_all):
        click.echo("ERROR: The --track-except and --track-cross-junctions options "
                   "can only be used with --track or --track-all", err=True)
        sys.exit(-1)

    if track_save:
        click.echo("WARNING: --track-save is deprecated, saving is now unconditional", err=True)

    if track_all:
        track_ = elements

    rewritable = False
    if track_:
        rewritable = True

    with app.initialized(elements, session_name="Build", except_=track_except, rewritable=rewritable,
                         use_configured_remote_caches=True, track_elements=track_,
                         track_cross_junctions=track_cross_junctions,
                         fetch_subprojects=True):
        app.pipeline.build(app.scheduler, build_all=all_)


##################################################################
#                          Fetch Command                         #
##################################################################
@cli.command(short_help="Fetch sources in a pipeline")
@click.option('--except', 'except_', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Except certain dependencies from fetching")
@click.option('--deps', '-d', default='plan',
              type=click.Choice(['none', 'plan', 'all']),
              help='The dependencies to fetch (default: plan)')
@click.option('--track', 'track_', default=False, is_flag=True,
              help="Track new source references before fetching")
@click.option('--track-cross-junctions', '-J', default=False, is_flag=True,
              help="Allow tracking to cross junction boundaries")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def fetch(app, elements, deps, track_, except_, track_cross_junctions):
    """Fetch sources required to build the pipeline

    By default this will only try to fetch sources which are
    required for the build plan of the specified target element,
    omitting sources for any elements which are already built
    and available in the artifact cache.

    Specify `--deps` to control which sources to fetch:

    \b
        none:  No dependencies, just the element itself
        plan:  Only dependencies required for the build plan
        all:   All dependencies
    """
    if track_cross_junctions and not track_:
        click.echo("ERROR: The --track-cross-junctions option can only be used with --track", err=True)
        sys.exit(-1)

    with app.initialized(elements, session_name="Fetch", except_=except_, rewritable=track_,
                         track_elements=elements if track_ else None,
                         track_cross_junctions=track_cross_junctions,
                         fetch_subprojects=True):
        dependencies = app.pipeline.get_selection(deps)
        app.pipeline.fetch(app.scheduler, dependencies)


##################################################################
#                          Track Command                         #
##################################################################
@cli.command(short_help="Track new source references")
@click.option('--except', 'except_', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Except certain dependencies from tracking")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependencies to track (default: none)')
@click.option('--cross-junctions', '-J', default=False, is_flag=True,
              help="Allow crossing junction boundaries")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def track(app, elements, deps, except_, cross_junctions):
    """Consults the specified tracking branches for new versions available
    to build and updates the project with any newly available references.

    By default this will track just the specified element, but you can also
    update a whole tree of dependencies in one go.

    Specify `--deps` to control which sources to track:

    \b
        none:  No dependencies, just the specified elements
        all:   All dependencies of all specified elements
    """
    with app.initialized(elements, session_name="Track", except_=except_, rewritable=True,
                         track_elements=elements,
                         track_cross_junctions=cross_junctions,
                         track_selection=deps,
                         fetch_subprojects=True):
        app.pipeline.track(app.scheduler)


##################################################################
#                           Pull Command                         #
##################################################################
@cli.command(short_help="Pull a built artifact")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependency artifacts to pull (default: none)')
@click.option('--remote', '-r',
              help="The URL of the remote cache (defaults to the first configured cache)")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def pull(app, elements, deps, remote):
    """Pull a built artifact from the configured remote artifact cache.

    By default the artifact will be pulled one of the configured caches
    if possible, following the usual priority order. If the `--remote` flag
    is given, only the specified cache will be queried.

    Specify `--deps` to control which artifacts to pull:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    with app.initialized(elements, session_name="Pull", use_configured_remote_caches=(remote is None),
                         add_remote_cache=remote, fetch_subprojects=True):
        to_pull = app.pipeline.get_selection(deps)
        app.pipeline.pull(app.scheduler, to_pull)


##################################################################
#                           Push Command                         #
##################################################################
@cli.command(short_help="Push a built artifact")
@click.option('--deps', '-d', default='none',
              type=click.Choice(['none', 'all']),
              help='The dependencies to push (default: none)')
@click.option('--remote', '-r', default=None,
              help="The URL of the remote cache (defaults to the first configured cache)")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def push(app, elements, deps, remote):
    """Push a built artifact to a remote artifact cache.

    The default destination is the highest priority configured cache. You can
    override this by passing a different cache URL with the `--remote` flag.

    Specify `--deps` to control which artifacts to push:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    with app.initialized(elements, session_name="Push",
                         use_configured_remote_caches=(remote is None),
                         add_remote_cache=remote, fetch_subprojects=True):
        to_push = app.pipeline.get_selection(deps)
        app.pipeline.push(app.scheduler, to_push)


##################################################################
#                           Show Command                         #
##################################################################
@cli.command(short_help="Show elements in the pipeline")
@click.option('--except', 'except_', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Except certain dependencies")
@click.option('--deps', '-d', default='all',
              type=click.Choice(['none', 'plan', 'run', 'build', 'all']),
              help='The dependencies to show (default: all)')
@click.option('--order', default="stage",
              type=click.Choice(['stage', 'alpha']),
              help='Staging or alphabetic ordering of dependencies')
@click.option('--format', '-f', 'format_', metavar='FORMAT', default=None,
              type=click.STRING,
              help='Format string for each element')
@click.option('--downloadable', default=False, is_flag=True,
              help="Refresh downloadable state")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def show(app, elements, deps, except_, order, format_, downloadable):
    """Show elements in the pipeline

    By default this will show all of the dependencies of the
    specified target element.

    Specify `--deps` to control which elements to show:

    \b
        none:  No dependencies, just the element itself
        plan:  Dependencies required for a build plan
        run:   Runtime dependencies, including the element itself
        build: Build time dependencies, excluding the element itself
        all:   All dependencies

    \b
    FORMAT
    ~~~~~~
    The --format option controls what should be printed for each element,
    the following symbols can be used in the format string:

    \b
        %{name}           The element name
        %{key}            The abbreviated cache key (if all sources are consistent)
        %{full-key}       The full cache key (if all sources are consistent)
        %{state}          cached, buildable, waiting or inconsistent
        %{config}         The element configuration
        %{vars}           Variable configuration
        %{env}            Environment settings
        %{public}         Public domain data
        %{workspaced}     If the element is workspaced
        %{workspace-dirs} A list of workspace directories

    The value of the %{symbol} without the leading '%' character is understood
    as a pythonic formatting string, so python formatting features apply,
    examle:

    \b
        bst show target.bst --format \\
            'Name: %{name: ^20} Key: %{key: ^8} State: %{state}'

    If you want to use a newline in a format string in bash, use the '$' modifier:

    \b
        bst show target.bst --format \\
            $'---------- %{name} ----------\\n%{vars}'
    """
    with app.initialized(elements, except_=except_, use_configured_remote_caches=downloadable):

        dependencies = app.pipeline.get_selection(deps)
        if order == "alpha":
            dependencies = sorted(dependencies)

        if not format_:
            format_ = app.context.log_element_format

        report = app.logger.show_pipeline(dependencies, format_)

    click.echo(report, color=app.colors)


##################################################################
#                          Shell Command                         #
##################################################################
@cli.command(short_help="Shell into an element's sandbox environment")
@click.option('--build', '-b', 'build_', is_flag=True, default=False,
              help='Stage dependencies and sources to build')
@click.option('--sysroot', '-s', default=None,
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="An existing sysroot")
@click.option('--mount', type=click.Tuple([click.Path(exists=True), str]), multiple=True,
              metavar='HOSTPATH PATH',
              help="Mount a file or directory into the sandbox")
@click.option('--isolate', is_flag=True, default=False,
              help='Create an isolated build sandbox')
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('command', type=click.STRING, nargs=-1)
@click.pass_obj
def shell(app, element, sysroot, mount, isolate, build_, command):
    """Run a command in the target element's sandbox environment

    This will stage a temporary sysroot for running the target
    element, assuming it has already been built and all required
    artifacts are in the local cache.

    Use the --build option to create a temporary sysroot for
    building the element instead.

    Use the --sysroot option with an existing failed build
    directory or with a checkout of the given target, in order
    to use a specific sysroot.

    If no COMMAND is specified, the default is to attempt
    to run an interactive shell.
    """
    from ..element import Scope
    from .._project import HostMount
    if build_:
        scope = Scope.BUILD
    else:
        scope = Scope.RUN

    with app.initialized((element,)):
        pass

    # Assert we have everything we need built.
    missing_deps = []
    if scope is not None:
        for dep in app.pipeline.dependencies(scope):
            if not dep._cached():
                missing_deps.append(dep)

    if missing_deps:
        click.echo("", err=True)
        click.echo("Missing elements for staging an environment for a shell:", err=True)
        for dep in missing_deps:
            click.echo("   {}".format(dep.name), err=True)
        click.echo("", err=True)
        click.echo("Try building them first", err=True)
        sys.exit(-1)

    mounts = [
        HostMount(path, host_path)
        for host_path, path in mount
    ]

    try:
        element = app.pipeline.targets[0]
        exitcode = app.shell(element, scope, sysroot, mounts=mounts, isolate=isolate, command=command)
        sys.exit(exitcode)
    except BstError as e:
        click.echo("", err=True)
        click.echo("Errors shelling into this pipeline: {}".format(e), err=True)
        sys.exit(-1)


##################################################################
#                        Checkout Command                        #
##################################################################
@cli.command(short_help="Checkout a built artifact")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--integrate/--no-integrate', default=True, is_flag=True,
              help="Whether to run integration commands")
@click.option('--hardlinks', default=False, is_flag=True,
              help="Checkout hardlinks instead of copies (handle with care)")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('directory', type=click.Path(file_okay=False))
@click.pass_obj
def checkout(app, element, directory, force, integrate, hardlinks):
    """Checkout a built artifact to the specified directory
    """
    with app.initialized((element,)):
        app.pipeline.checkout(directory, force, integrate, hardlinks)


##################################################################
#                     Source Bundle Command                      #
##################################################################
@cli.command(name="source-bundle", short_help="Produce a build bundle to be manually executed")
@click.option('--except', 'except_', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Elements to except from the tarball")
@click.option('--compression', default='gz',
              type=click.Choice(['none', 'gz', 'bz2', 'xz']),
              help="Compress the tar file using the given algorithm.")
@click.option('--track', 'track_', default=False, is_flag=True,
              help="Track new source references before building")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--directory', default=os.getcwd(),
              help="The directory to write the tarball to")
@click.argument('target',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def source_bundle(app, target, force, directory,
                  track_, compression, except_):
    """Produce a source bundle to be manually executed
    """
    with app.initialized((target,), rewritable=track_, track_elements=[target] if track_ else None):
        dependencies = app.pipeline.get_selection('all')
        app.pipeline.source_bundle(app.scheduler, dependencies, force, track_,
                                   compression, directory)


##################################################################
#                      Workspace Command                         #
##################################################################
@cli.group(short_help="Manipulate developer workspaces")
def workspace():
    """Manipulate developer workspaces"""
    pass


##################################################################
#                     Workspace Open Command                     #
##################################################################
@workspace.command(name='open', short_help="Open a new workspace")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--track', 'track_', default=False, is_flag=True,
              help="Track and fetch new source references before checking out the workspace")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('directory', type=click.Path(file_okay=False))
@click.pass_obj
def workspace_open(app, no_checkout, force, track_, element, directory):
    """Open a workspace for manual source modification"""

    if os.path.exists(directory):

        if not os.path.isdir(directory):
            click.echo("Checkout directory is not a directory: {}".format(directory), err=True)
            sys.exit(-1)

        if not (no_checkout or force) and os.listdir(directory):
            click.echo("Checkout directory is not empty: {}".format(directory), err=True)
            sys.exit(-1)

    with app.initialized((element,), rewritable=track_, track_elements=[element] if track_ else None):
        # This command supports only one target
        target = app.pipeline.targets[0]
        app.open_workspace(target, directory, no_checkout, track_, force)


##################################################################
#                     Workspace Close Command                    #
##################################################################
@workspace.command(name='close', short_help="Close workspaces")
@click.option('--remove-dir', default=False, is_flag=True,
              help="Remove the path that contains the closed workspace")
@click.option('--all', '-a', 'all_', default=False, is_flag=True,
              help="Close all open workspaces")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_close(app, remove_dir, all_, elements):
    """Close a workspace"""

    if not (all_ or elements):
        click.echo('ERROR: no elements specified', err=True)
        sys.exit(-1)

    with app.partially_initialized():
        if all_:
            elements = [element_name for element_name, _ in app.project.workspaces.list()]
        for element in elements:
            app.close_workspace(element, remove_dir)


##################################################################
#                     Workspace Reset Command                    #
##################################################################
@workspace.command(name='reset', short_help="Reset a workspace to its original state")
@click.option('--soft', default=False, is_flag=True,
              help="Reset workspace state without affecting its contents")
@click.option('--track', 'track_', default=False, is_flag=True,
              help="Track and fetch the latest source before resetting")
@click.option('--all', '-a', 'all_', default=False, is_flag=True,
              help="Reset all open workspaces")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_reset(app, soft, track_, all_, elements):
    """Reset a workspace to its original state"""

    if not (all_ or elements):
        click.echo('ERROR: no elements specified', err=True)
        sys.exit(-1)

    if app.interactive and not soft:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting', err=True)
            sys.exit(-1)

    with app.partially_initialized():
        if all_:
            elements = tuple(element_name for element_name, _ in app.project.workspaces.list())

    with app.initialized(elements):
        for target in app.pipeline.targets:
            app.reset_workspace(target, soft, track_)


##################################################################
#                     Workspace List Command                     #
##################################################################
@workspace.command(name='list', short_help="List open workspaces")
@click.pass_obj
def workspace_list(app):
    """List open workspaces"""

    with app.partially_initialized():
        workspaces = []
        for element_name, workspace_ in app.project.workspaces.list():
            workspace_detail = {
                'element': element_name,
                'directory': workspace_.path,
            }
            workspaces.append(workspace_detail)

        _yaml.dump({
            'workspaces': workspaces
        })
