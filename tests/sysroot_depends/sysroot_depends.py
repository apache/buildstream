import os
import pytest
from tests.testutils import cli_integration as cli
from tests.testutils.site import IS_LINUX, HAVE_BWRAP


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_sysroot_dependency_smoke_test(datafiles, cli, tmpdir):
    "Test simple sysroot use case without integration"

    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    result = cli.run(project=project,
                     args=['build', 'target.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'target.bst', checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, 'a.txt'))
    assert os.path.exists(os.path.join(checkout, 'sysroot', 'b.txt'))


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_skip_integration_commands_build_element(datafiles, cli, tmpdir):
    "Integration commands are not run on sysroots"

    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    result = cli.run(project=project,
                     args=['build', 'manual-integration.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'manual-integration.bst', checkout])
    result.assert_success()

    sysroot_integrated = os.path.join(checkout, 'sysroot', 'integrated.txt')
    integrated = os.path.join(checkout, 'integrated.txt')
    assert os.path.exists(sysroot_integrated)
    with open(sysroot_integrated, 'r') as f:
        assert f.read() == '0\n'
    # We need to make sure that integration command has not been run on / either.
    assert not os.path.exists(integrated)


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_sysroot_only_for_build(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    result = cli.run(project=project,
                     args=['build', 'compose-layers.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'compose-layers.bst', checkout])

    result.assert_success()
    assert os.path.exists(os.path.join(checkout, '1'))
    assert os.path.exists(os.path.join(checkout, '2'))
    assert not os.path.exists(os.path.join(checkout, 'sysroot', '1'))


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_sysroot_only_for_build_with_sysroot(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    result = cli.run(project=project,
                     args=['build', 'compose-layers-with-sysroot.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'compose-layers-with-sysroot.bst', checkout])

    result.assert_success()
    assert os.path.exists(os.path.join(checkout, 'other-sysroot', '1'))
    assert os.path.exists(os.path.join(checkout, 'other-sysroot', '2'))
    assert not os.path.exists(os.path.join(checkout, 'sysroot', '1'))


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_shell_no_sysroot(cli, tmpdir, datafiles):
    "bst shell does not have sysroots and dependencies are integrated"

    project = str(datafiles)

    result = cli.run(project=project,
                     args=['build', 'base.bst', 'manual-integration-runtime.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['shell', 'manual-integration-runtime.bst', '--', 'cat', '/integrated.txt'])
    result.assert_success()
    assert result.output == '1\n'

    result = cli.run(project=project,
                     args=['shell', 'manual-integration-runtime.bst', '--', 'ls', '/sysroot/integrated.txt'])
    assert result.exit_code != 0
    assert result.output == ''


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_shell_build_sysroot(cli, tmpdir, datafiles):
    "Build shell should stage build dependencies sysroot'ed non integrated"

    project = str(datafiles)

    result = cli.run(project=project,
                     args=['build', 'base.bst', 'integration.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['shell', '-b', 'manual-integration.bst', '--', 'cat', '/sysroot/integrated.txt'])
    result.assert_success()
    assert result.output == '0\n'


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_show_dependencies_only_once(cli, tmpdir, datafiles):
    """Dependencies should not show up in status several times when they
    are staged with multiple sysroots"""

    project = str(datafiles)

    result = cli.run(project=project,
                     args=['show', '--format', '%{name}', 'manual-integration.bst'])
    result.assert_success()
    pipeline = result.output.splitlines()
    assert pipeline == ['base/base-alpine.bst',
                        'base.bst',
                        'integration.bst',
                        'manual-integration.bst']


@pytest.mark.integration
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_sysroot_path_subst_variable(datafiles, cli, tmpdir):
    "Test that variables are expanded in sysroot path"

    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), 'checkout')

    result = cli.run(project=project,
                     args=['build', 'target-variable.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['checkout', 'target-variable.bst', checkout])
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, 'test', 'b.txt'))
