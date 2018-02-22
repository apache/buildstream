import os
import sys

import click
from .. import _yaml
from .._exceptions import BstError, PipelineError, LoadError
from ..__version__ import __version__ as build_stream_version
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
@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(version=build_stream_version)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, readable=True),
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
@click.option('--option', '-o', type=click.Tuple([str, str]), multiple=True,
              help="Specify a project option")
@click.pass_context
def cli(context, **kwargs):
    """Build and manipulate BuildStream projects

    Most of the main options override options in the
    user preferences configuration file.
    """

    from .main import App

    # Create the App, giving it the main arguments
    context.obj = App(dict(kwargs))
    context.call_on_close(context.obj.cleanup)


##################################################################
#                          Build Command                         #
##################################################################
@cli.command(short_help="Build elements in a pipeline")
@click.option('--all', default=False, is_flag=True,
              help="Build elements that would not be needed for the current build plan")
@click.option('--track', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Specify elements to track during the build. Can be used "
                   "repeatedly to specify multiple elements")
@click.option('--track-all', default=False, is_flag=True,
              help="Track all elements in the pipeline")
@click.option('--track-except', multiple=True,
              type=click.Path(dir_okay=False, readable=True),
              help="Except certain dependencies from tracking")
@click.option('--track-save', default=False, is_flag=True,
              help="Write out the tracked references to their element files")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def build(app, elements, all, track, track_save, track_all, track_except):
    """Build elements in a pipeline"""

    if track_except and not (track or track_all):
        click.echo("ERROR: --track-except cannot be used without --track or --track-all")
        sys.exit(-1)

    if track_save and not (track or track_all):
        click.echo("ERROR: --track-save cannot be used without --track or --track-all")
        sys.exit(-1)

    if track_all:
        track = elements

    app.initialize(elements, except_=track_except, rewritable=track_save,
                   use_configured_remote_caches=True, track_elements=track,
                   fetch_subprojects=True)
    app.print_heading()
    try:
        app.pipeline.build(app.scheduler, all, track, track_save)
        app.print_summary()
    except PipelineError as e:
        app.print_error(e)
        app.print_summary()
        sys.exit(-1)


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
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before fetching")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def fetch(app, elements, deps, track, except_):
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

    app.initialize(elements, except_=except_, rewritable=track,
                   track_elements=elements if track else None,
                   fetch_subprojects=True)
    try:
        dependencies = app.pipeline.deps_elements(deps)
        app.print_heading(deps=dependencies)
        app.pipeline.fetch(app.scheduler, dependencies, track)
        app.print_summary()
    except PipelineError as e:
        app.print_error(e)
        app.print_summary()
        sys.exit(-1)


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
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def track(app, elements, deps, except_):
    """Consults the specified tracking branches for new versions available
    to build and updates the project with any newly available references.

    By default this will track just the specified element, but you can also
    update a whole tree of dependencies in one go.

    Specify `--deps` to control which sources to track:

    \b
        none:  No dependencies, just the element itself
        all:   All dependencies
    """
    app.initialize(elements, except_=except_, rewritable=True, track_elements=elements,
                   fetch_subprojects=True)
    try:
        dependencies = app.pipeline.deps_elements(deps)
        app.print_heading(deps=dependencies)
        app.pipeline.track(app.scheduler, dependencies)
        app.print_summary()
    except PipelineError as e:
        app.print_error(e)
        app.print_summary()
        sys.exit(-1)


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
    app.initialize(elements, use_configured_remote_caches=(remote is None),
                   add_remote_cache=remote, fetch_subprojects=True)
    try:
        to_pull = app.pipeline.deps_elements(deps)
        app.pipeline.pull(app.scheduler, to_pull)
        app.print_summary()
    except BstError as e:
        app.print_error(e)
        app.print_summary()
        sys.exit(-1)


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
    app.initialize(elements, use_configured_remote_caches=(remote is None),
                   add_remote_cache=remote, fetch_subprojects=True)
    try:
        to_push = app.pipeline.deps_elements(deps)
        app.pipeline.push(app.scheduler, to_push)
        app.print_summary()
    except BstError as e:
        app.print_error(e)
        app.print_summary()
        sys.exit(-1)


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
@click.option('--format', '-f', metavar='FORMAT', default=None,
              type=click.STRING,
              help='Format string for each element')
@click.option('--downloadable', default=False, is_flag=True,
              help="Refresh downloadable state")
@click.argument('elements', nargs=-1,
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def show(app, elements, deps, except_, order, format, downloadable):
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
    app.initialize(elements, except_=except_, use_configured_remote_caches=downloadable)
    try:
        dependencies = app.pipeline.deps_elements(deps)
    except PipelineError as e:
        click.echo("{}".format(e), err=True)
        sys.exit(-1)

    if order == "alpha":
        dependencies = sorted(dependencies)

    if not format:
        format = app.context.log_element_format

    report = app.logger.show_pipeline(dependencies, format)
    click.echo(report, color=app.colors)


##################################################################
#                          Shell Command                         #
##################################################################
@cli.command(short_help="Shell into an element's sandbox environment")
@click.option('--build', '-b', is_flag=True, default=False,
              help='Stage dependencies and sources to build')
@click.option('--sysroot', '-s', default=None,
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="An existing sysroot")
@click.option('--isolate', is_flag=True, default=False,
              help='Create an isolated build sandbox')
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('command', type=click.STRING, nargs=-1)
@click.pass_obj
def shell(app, element, sysroot, isolate, build, command):
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
    to run an interactive shell with `sh -i`.
    """
    from ..element import Scope
    if build:
        scope = Scope.BUILD
    else:
        scope = Scope.RUN

    app.initialize((element,))

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

    try:
        exitcode = app.pipeline.targets[0]._shell(scope, sysroot, isolate=isolate, command=command)
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
    app.initialize((element,))
    try:
        app.pipeline.checkout(directory, force, integrate, hardlinks)
        click.echo("", err=True)
    except BstError as e:
        app.print_error(e)
        sys.exit(-1)


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
@click.option('--track', default=False, is_flag=True,
              help="Track new source references before building")
@click.option('--force', '-f', default=False, is_flag=True,
              help="Overwrite files existing in checkout directory")
@click.option('--directory', default=os.getcwd(),
              help="The directory to write the tarball to")
@click.argument('target',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def source_bundle(app, target, force, directory,
                  track, compression, except_):
    """Produce a source bundle to be manually executed"""
    app.initialize((target,), rewritable=track, track_elements=[target] if track else None)
    try:
        dependencies = app.pipeline.deps_elements('all')
        app.print_heading(dependencies)
        app.pipeline.source_bundle(app.scheduler, dependencies, force, track,
                                   compression, directory)
        click.echo("", err=True)
    except BstError as e:
        click.echo("", err=True)
        click.echo("ERROR: {}".format(e), err=True)
        sys.exit(-1)


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
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch new source references before checking out the workspace")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.argument('directory', type=click.Path(file_okay=False))
@click.pass_obj
def workspace_open(app, no_checkout, force, track, element, directory):
    """Open a workspace for manual source modification"""

    app.initialize((element,), rewritable=track, track_elements=[element] if track else None)
    try:
        app.pipeline.open_workspace(app.scheduler, directory, no_checkout, track, force)
        click.echo("", err=True)
    except BstError as e:
        click.echo("", err=True)
        click.echo("ERROR: {}".format(e), err=True)
        sys.exit(-1)


##################################################################
#                     Workspace Close Command                    #
##################################################################
@workspace.command(name='close', short_help="Close a workspace")
@click.option('--remove-dir', default=False, is_flag=True,
              help="Remove the path that contains the closed workspace")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_close(app, remove_dir, element):
    """Close a workspace"""

    app.initialize((element,))

    if app.pipeline.project._get_workspace(app.pipeline.targets[0].name) is None:
        click.echo("ERROR: Workspace '{}' does not exist".format(element), err=True)
        sys.exit(-1)

    if app.interactive and remove_dir:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting', err=True)
            sys.exit(-1)

    try:
        app.pipeline.close_workspace(remove_dir)
        click.echo("", err=True)
    except BstError as e:
        click.echo("", err=True)
        click.echo("ERROR: {}".format(e), err=True)
        sys.exit(-1)


##################################################################
#                     Workspace Reset Command                    #
##################################################################
@workspace.command(name='reset', short_help="Reset a workspace to its original state")
@click.option('--track', default=False, is_flag=True,
              help="Track and fetch the latest source before resetting")
@click.option('--no-checkout', default=False, is_flag=True,
              help="Do not checkout the source, only link to the given directory")
@click.argument('element',
                type=click.Path(dir_okay=False, readable=True))
@click.pass_obj
def workspace_reset(app, track, no_checkout, element):
    """Reset a workspace to its original state"""
    app.initialize((element,))
    if app.interactive:
        if not click.confirm('This will remove all your changes, are you sure?'):
            click.echo('Aborting', err=True)
            sys.exit(-1)

    try:
        app.pipeline.reset_workspace(app.scheduler, track, no_checkout)
        click.echo("", err=True)
    except BstError as e:
        click.echo("", err=True)
        click.echo("ERROR: {}".format(e), err=True)
        sys.exit(-1)


##################################################################
#                     Workspace List Command                     #
##################################################################
@workspace.command(name='list', short_help="List open workspaces")
@click.pass_obj
def workspace_list(app):
    """List open workspaces"""

    from .. import _yaml
    from .._context import Context
    from .._project import Project

    directory = app.main_options['directory']
    config = app.main_options['config']

    try:
        context = Context()
        context.load(config)
    except BstError as e:
        click.echo("Error loading user configuration: {}".format(e), err=True)
        sys.exit(-1)

    try:
        project = Project(directory, context, cli_options=app.main_options['option'])
    except BstError as e:
        click.echo("Error loading project: {}".format(e), err=True)
        sys.exit(-1)

    workspaces = []
    for element_name, directory in project._list_workspaces():
        workspace = {
            'element': element_name,
            'directory': directory,
        }

        workspaces.append(workspace)

    _yaml.dump({
        'workspaces': workspaces
    })
