import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.python_repo import setup_pypi_repo
from tests.testutils.integration import assert_contains
from tests.testutils.site import HAVE_BWRAP, IS_LINUX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_pip_source_import(cli, tmpdir, datafiles, setup_pypi_repo):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'pip/hello.bst'

    # check that exotically named packages are imported correctly
    myreqs_packages = ['hellolib']
    packages = ['app2', 'app.3', 'app-4', 'app_5', 'app.no.6', 'app-no-7', 'app_no_8']

    # create mock pypi repository
    pypi_repo = os.path.join(project, 'files', 'pypi-repo')
    os.makedirs(pypi_repo, exist_ok=True)
    setup_pypi_repo(myreqs_packages + packages, pypi_repo)

    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': 'files/pip-source'
            },
            {
                'kind': 'pip',
                'url': 'file://{}'.format(os.path.realpath(pypi_repo)),
                'requirements-files': ['myreqs.txt'],
                'packages': packages
            }
        ]
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=['source', 'track', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/.bst_pip_downloads',
                               '/.bst_pip_downloads/hellolib-0.1.tar.gz',
                               '/.bst_pip_downloads/app2-0.1.tar.gz',
                               '/.bst_pip_downloads/app.3-0.1.tar.gz',
                               '/.bst_pip_downloads/app-4-0.1.tar.gz',
                               '/.bst_pip_downloads/app_5-0.1.tar.gz',
                               '/.bst_pip_downloads/app.no.6-0.1.tar.gz',
                               '/.bst_pip_downloads/app-no-7-0.1.tar.gz',
                               '/.bst_pip_downloads/app_no_8-0.1.tar.gz'])


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_pip_source_build(cli, tmpdir, datafiles, setup_pypi_repo):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    element_name = 'pip/hello.bst'

    # check that exotically named packages are imported correctly
    myreqs_packages = ['hellolib']
    packages = ['app2', 'app.3', 'app-4', 'app_5', 'app.no.6', 'app-no-7', 'app_no_8']

    # create mock pypi repository
    pypi_repo = os.path.join(project, 'files', 'pypi-repo')
    os.makedirs(pypi_repo, exist_ok=True)
    setup_pypi_repo(myreqs_packages + packages, pypi_repo)

    element = {
        'kind': 'manual',
        'depends': ['base.bst'],
        'sources': [
            {
                'kind': 'local',
                'path': 'files/pip-source'
            },
            {
                'kind': 'pip',
                'url': 'file://{}'.format(os.path.realpath(pypi_repo)),
                'requirements-files': ['myreqs.txt'],
                'packages': packages
            }
        ],
        'config': {
            'install-commands': [
                'pip3 install --no-index --prefix %{install-root}/usr .bst_pip_downloads/*.tar.gz',
                'install app1.py %{install-root}/usr/bin/'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=['source', 'track', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/app1.py'])
    assert result.exit_code == 0
    assert result.output == "Hello App1! This is hellolib\n"
