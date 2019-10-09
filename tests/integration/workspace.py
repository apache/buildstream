# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX
from buildstream._exceptions import ErrorDomain


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_mount(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-mount.bst'

    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    assert os.path.exists(os.path.join(cli.directory, 'workspace'))


@pytest.mark.datafiles(DATA_DIR)
def test_workspace_mount_on_read_only_directory(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, 'workspace')
    os.makedirs(workspace)
    element_name = 'workspace/workspace-mount.bst'

    # make directory RO
    os.chmod(workspace, 0o555)

    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox')
@pytest.mark.xfail(reason="Incremental builds are currently incompatible with workspace source plugin.")
def test_workspace_commanddir(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-commanddir.bst'

    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    assert os.path.exists(os.path.join(cli.directory, 'workspace'))
    assert os.path.exists(os.path.join(cli.directory, 'workspace', 'build'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_updated_dependency(cli, datafiles):
    project = str(datafiles)
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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_update_dependency_failed(cli, datafiles):
    project = str(datafiles)
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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_updated_dependency_nested(cli, datafiles):
    project = str(datafiles)
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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

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
    _yaml.roundtrip_dump(dependency, os.path.join(element_path, dep_name))

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Buildstream should pick up the newly added element, and pick up
    # the lack of the newly removed element
    res = cli.run(project=project, args=['shell', element_name, '/usr/bin/test.sh'])
    assert res.exit_code == 0
    assert res.output == 'Hello world!\nHello test!\n\n'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox')
@pytest.mark.xfail(reason="Incremental builds are currently incompatible with workspace source plugin.")
def test_incremental_configure_commands_run_only_once(cli, datafiles):
    project = str(datafiles)
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
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

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


# Test that rebuilding an already built workspaced element does
# not crash after the last successfully built artifact is removed
# from the cache
#
# A user can remove their artifact cache, or manually remove the
# artifact with `bst artifact delete`, or BuildStream can delete
# the last successfully built artifact for this workspace as a
# part of a cleanup job.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.xfail(HAVE_SANDBOX == 'buildbox', reason='Not working with BuildBox')
def test_workspace_missing_last_successful(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, 'workspace')
    element_name = 'workspace/workspace-commanddir.bst'

    # Open workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    assert res.exit_code == 0

    # Build first, this will record the last successful build in local state
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    # Remove the artifact from the cache, invalidating the last successful build
    res = cli.run(project=project, args=['artifact', 'delete', element_name])
    assert res.exit_code == 0

    # Build again, ensure we dont crash just because the artifact went missing
    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0


# Check that we can still read failed workspace logs
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_workspace_failed_logs(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, 'failing_amhello')
    element_name = 'autotools/amhello-failure.bst'

    # Open workspace
    res = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, element_name])
    res.assert_success()

    # Try to build and ensure the build fails
    res = cli.run(project=project, args=['build', element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)
    assert cli.get_element_state(project, element_name) == 'failed'

    res = cli.run(project=project, args=['artifact', 'log', element_name])
    res.assert_success()

    log = res.output
    # Assert that we can get the log
    assert log != ""
    fail_str = "FAILURE {}: Running build-commands".format(element_name)
    assert fail_str in log
