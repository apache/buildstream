import os
import pytest
import tarfile
from pathlib import Path

from tests.testutils import cli

from buildstream import utils, _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'project',
)


def generate_remote_import_element(input_path, output_path):
    return {
        'kind': 'import',
        'sources': [
            {
                'kind': 'remote',
                'url': 'file://{}'.format(input_path),
                'filename': output_path,
                'ref': utils.sha256sum(input_path),
            }
        ]
    }


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "with_workspace,guess_element",
    [(True, True), (True, False), (False, False)],
    ids=["workspace-guess", "workspace-no-guess", "no-workspace-no-guess"]
)
def test_source_checkout(datafiles, cli, tmpdir_factory, with_workspace, guess_element):
    tmpdir = tmpdir_factory.mktemp("")
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout')
    target = 'checkout-deps.bst'
    workspace = os.path.join(str(tmpdir), 'workspace')
    elm_cmd = [target] if not guess_element else []

    if with_workspace:
        ws_cmd = ['-C', workspace]
        result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, target])
        result.assert_success()
    else:
        ws_cmd = []

    args = ws_cmd + ['source-checkout', '--deps', 'none'] + elm_cmd + [checkout]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, 'checkout-deps', 'etc', 'buildstream', 'config'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize('force_flag', ['--force', '-f'])
def test_source_checkout_force(datafiles, cli, force_flag):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout')
    target = 'checkout-deps.bst'

    os.makedirs(os.path.join(checkout, 'some-thing'))
    # Path(os.path.join(checkout, 'some-file')).touch()

    result = cli.run(project=project, args=['source-checkout', force_flag, target, '--deps', 'none', checkout])
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, 'checkout-deps', 'etc', 'buildstream', 'config'))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_tar(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout.tar')
    target = 'checkout-deps.bst'

    result = cli.run(project=project, args=['source-checkout', '--tar', target, '--deps', 'none', checkout])
    result.assert_success()

    assert os.path.exists(checkout)
    with tarfile.open(checkout) as tf:
        expected_content = os.path.join(checkout, 'checkout-deps', 'etc', 'buildstream', 'config')
        tar_members = [f.name for f in tf]
        for member in tar_members:
            assert member in expected_content


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize('deps', [('build'), ('none'), ('run'), ('all')])
def test_source_checkout_deps(datafiles, cli, deps):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout')
    target = 'checkout-deps.bst'

    result = cli.run(project=project, args=['source-checkout', target, '--deps', deps, checkout])
    result.assert_success()

    # Sources of the target
    if deps == 'build':
        assert not os.path.exists(os.path.join(checkout, 'checkout-deps'))
    else:
        assert os.path.exists(os.path.join(checkout, 'checkout-deps', 'etc', 'buildstream', 'config'))

    # Sources of the target's build dependencies
    if deps in ('build', 'all'):
        assert os.path.exists(os.path.join(checkout, 'import-dev', 'usr', 'include', 'pony.h'))
    else:
        assert not os.path.exists(os.path.join(checkout, 'import-dev'))

    # Sources of the target's runtime dependencies
    if deps in ('run', 'all'):
        assert os.path.exists(os.path.join(checkout, 'import-bin', 'usr', 'bin', 'hello'))
    else:
        assert not os.path.exists(os.path.join(checkout, 'import-bin'))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_except(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout')
    target = 'checkout-deps.bst'

    result = cli.run(project=project, args=['source-checkout', target,
                                            '--deps', 'all',
                                            '--except', 'import-bin.bst',
                                            checkout])
    result.assert_success()

    # Sources for the target should be present
    assert os.path.exists(os.path.join(checkout, 'checkout-deps', 'etc', 'buildstream', 'config'))

    # Sources for import-bin.bst should not be present
    assert not os.path.exists(os.path.join(checkout, 'import-bin'))

    # Sources for other dependencies should be present
    assert os.path.exists(os.path.join(checkout, 'import-dev', 'usr', 'include', 'pony.h'))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize('fetch', [(False), (True)])
def test_source_checkout_fetch(datafiles, cli, fetch):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'source-checkout')
    target = 'remote-import-dev.bst'
    target_path = os.path.join(project, 'elements', target)

    # Create an element with remote source
    element = generate_remote_import_element(
        os.path.join(project, 'files', 'dev-files', 'usr', 'include', 'pony.h'),
        'pony.h')
    _yaml.dump(element, target_path)

    # Testing --fetch option requires that we do not have the sources
    # cached already
    assert cli.get_element_state(project, target) == 'fetch needed'

    args = ['source-checkout']
    if fetch:
        args += ['--fetch']
    args += [target, checkout]
    result = cli.run(project=project, args=args)

    if fetch:
        result.assert_success()
        assert os.path.exists(os.path.join(checkout, 'remote-import-dev', 'pony.h'))
    else:
        result.assert_main_error(ErrorDomain.PIPELINE, 'uncached-sources')


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_build_scripts(cli, tmpdir, datafiles):
    project_path = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'source-bundle/source-bundle-hello.bst'
    normal_name = 'source-bundle-source-bundle-hello'
    checkout = os.path.join(str(tmpdir), 'source-checkout')

    args = ['source-checkout', '--include-build-scripts', element_name, checkout]
    result = cli.run(project=project_path, args=args)
    result.assert_success()

    # There sould be a script for each element (just one in this case) and a top level build script
    expected_scripts = ['build.sh', 'build-' + normal_name]
    for script in expected_scripts:
        assert script in os.listdir(checkout)


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_tar_buildscripts(cli, tmpdir, datafiles):
    project_path = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'source-bundle/source-bundle-hello.bst'
    normal_name = 'source-bundle-source-bundle-hello'
    tar_file = os.path.join(str(tmpdir), 'source-checkout.tar')

    args = ['source-checkout', '--include-build-scripts', '--tar', element_name, tar_file]
    result = cli.run(project=project_path, args=args)
    result.assert_success()

    expected_scripts = ['build.sh', 'build-' + normal_name]

    with tarfile.open(tar_file, 'r') as tf:
        for script in expected_scripts:
            assert script in tf.getnames()
