import os
import pytest

from buildstream import _yaml
from buildstream.plugintestutils import cli_integration as cli
from tests.testutils.site import HAVE_SANDBOX
from buildstream.plugintestutils.integration import walk_dir


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_mount(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-mount.bst'

    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    assert os.path.exists(os.path.join(cli.directory, 'workspace'))


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_commanddir(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-commanddir.bst'

    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    assert os.path.exists(os.path.join(cli.directory, 'workspace'))
    assert os.path.exists(os.path.join(cli.directory, 'workspace', 'build'))


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_updated_dependency(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace/workspace-updated-dependency.bst'
    dep_name = 'workspace/dependency.bst'

    dependency = {
        'kind': 'manual',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'config': {
            'build-commands': [
                'mkdir -p %{install-root}/etc/test/',
                'echo "Hello world!" > %{install-root}/etc/test/hello.txt'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, dep_name)), exist_ok=True)
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # First open the workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    # We build the workspaced element, so that we have an artifact
    # with specific built dependencies
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Now we update a dependency of our element.
    dependency['config']['build-commands'] = [
        'mkdir -p %{install-root}/etc/test/',
        'echo "Hello china!" > %{install-root}/etc/test/hello.txt'
    ]
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # `Make` would look at timestamps and normally not realize that
    # our dependency's header files changed. BuildStream must
    # therefore ensure that we change the mtimes of any files touched
    # since the last successful build of this element, otherwise this
    # build will fail.
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['shell', element_name, '/usr/bin/test.sh'])
    assert res.exit_code == 0
    assert res.output == 'Hello china!\n\n'


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_update_dependency_failed(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace/workspace-updated-dependency-failed.bst'
    dep_name = 'workspace/dependency.bst'

    dependency = {
        'kind': 'manual',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'config': {
            'build-commands': [
                'mkdir -p %{install-root}/etc/test/',
                'echo "Hello world!" > %{install-root}/etc/test/hello.txt',
                'echo "Hello brazil!" > %{install-root}/etc/test/brazil.txt'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, dep_name)), exist_ok=True)
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # First open the workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    # We build the workspaced element, so that we have an artifact
    # with specific built dependencies
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Now we update a dependency of our element.
    dependency['config']['build-commands'] = [
        'mkdir -p %{install-root}/etc/test/',
        'echo "Hello china!" > %{install-root}/etc/test/hello.txt',
        'echo "Hello brazil!" > %{install-root}/etc/test/brazil.txt'
    ]
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # And our build fails!
    with open(os.path.join(workspace, 'Makefile'), 'a') as f:
        f.write("\texit 1")

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code != 0

    # We update our dependency again...
    dependency['config']['build-commands'] = [
        'mkdir -p %{install-root}/etc/test/',
        'echo "Hello world!" > %{install-root}/etc/test/hello.txt',
        'echo "Hello spain!" > %{install-root}/etc/test/brazil.txt'
    ]
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # And fix the source
    with open(os.path.join(workspace, 'Makefile'), 'r') as f:
        makefile = f.readlines()
    with open(os.path.join(workspace, 'Makefile'), 'w') as f:
        f.write("\n".join(makefile[:-1]))

    # Since buildstream thinks hello.txt did not change, we could end
    # up not rebuilding a file! We need to make sure that a case like
    # this can't blind-side us.
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['shell', element_name, '/usr/bin/test.sh'])
    assert res.exit_code == 0
    assert res.output == 'Hello world!\nHello spain!\n\n'


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_updated_dependency_nested(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace/workspace-updated-dependency-nested.bst'
    dep_name = 'workspace/dependency.bst'

    dependency = {
        'kind': 'manual',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'config': {
            'build-commands': [
                'mkdir -p %{install-root}/etc/test/tests/',
                'echo "Hello world!" > %{install-root}/etc/test/hello.txt',
                'echo "Hello brazil!" > %{install-root}/etc/test/tests/brazil.txt'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, dep_name)), exist_ok=True)
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    # First open the workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    # We build the workspaced element, so that we have an artifact
    # with specific built dependencies
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Now we update a dependency of our element.
    dependency['config']['build-commands'] = [
        'mkdir -p %{install-root}/etc/test/tests/',
        'echo "Hello world!" > %{install-root}/etc/test/hello.txt',
        'echo "Hello test!" > %{install-root}/etc/test/tests/tests.txt'
    ]
    _yaml.dump(dependency, os.path.join(element_path, dep_name))

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Buildstream should pick up the newly added element, and pick up
    # the lack of the newly removed element
    res = cli.run(project=project, args=['shell', element_name, '/usr/bin/test.sh'])
    assert res.exit_code == 0
    assert res.output == 'Hello world!\nHello test!\n\n'


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_incremental_configure_commands_run_only_once(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_path = os.path.join(project, 'elements')
    element_name = 'workspace/incremental.bst'

    element = {
        'kind': 'manual',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'sources': [{
            'kind': 'local',
            'path': 'files/workspace-configure-only-once'
        }],
        'config': {
            'configure-commands': [
                '$SHELL configure'
            ]
        }
    }
    _yaml.dump(element, os.path.join(element_path, element_name))

    # We open a workspace on the above element
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    res.assert_success()

    # Then we build, and check whether the configure step succeeded
    res = cli.run(project=project, args=['build', element_name])
    res.assert_success()
    assert os.path.exists(os.path.join(workspace, 'prepared'))

    # When we build again, the configure commands should not be
    # called, and we should therefore exit cleanly (the configure
    # commands are set to always fail after the first run)
    res = cli.run(project=project, args=['build', element_name])
    res.assert_success()
    assert not os.path.exists(os.path.join(workspace, 'prepared-again'))


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_contains_buildtree(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'autotools/amhello.bst'

    # Ensure we're not using the shared artifact cache
    cli.configure({
        'artifactdir': os.path.join(str(tmpdir), 'artifacts')
    })

    # First open the workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    res.assert_success()

    # Check that by default the buildtree wasn't staged as not yet available in the cache
    assert not os.path.exists(os.path.join(workspace, 'src', 'hello'))

    # Close the workspace, removing the dir
    res = cli.run(project=project, args=['workspace', 'close', '--remove-dir', element_name])
    res.assert_success()

    # Build the element, so we have it cached along with the buildtreee
    res = cli.run(project=project, args=['build', element_name])
    res.assert_success()

    # Open up the workspace, as the buildtree is cached by default it should open with the buildtree
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    res.assert_success()

    # Check that the buildtree was staged, by asserting output of the build exists in the dir
    assert os.path.exists(os.path.join(workspace, 'src', 'hello'))
