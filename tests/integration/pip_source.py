import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import assert_contains


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_pip_source_import(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'pip/hello.bst'

    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': 'files/pip-source'
            },
            {
                'kind': 'pip',
                'url': 'file://{}'.format(os.path.realpath(os.path.join(project, 'files', 'pypi-repo'))),
                'requirements-files': ['myreqs.txt'],
                'packages': ['app2']
            }
        ]
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=['track', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/.bst_pip_downloads',
                               '/.bst_pip_downloads/HelloLib-0.1.tar.gz',
                               '/.bst_pip_downloads/App2-0.1.tar.gz'])


@pytest.mark.datafiles(DATA_DIR)
def test_pip_source_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    element_name = 'pip/hello.bst'

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
                'url': 'file://{}'.format(os.path.realpath(os.path.join(project, 'files', 'pypi-repo'))),
                'requirements-files': ['myreqs.txt'],
                'packages': ['app2']
            }
        ],
        'config': {
            'install-commands': [
                'pip3 install --no-index --prefix %{install-root}/usr .bst_pip_downloads/*.tar.gz',
                'chmod +x app1.py',
                'install app1.py  %{install-root}/usr/bin/'
            ]
        }
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=['track', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/app1.py'])
    assert result.exit_code == 0
    assert result.output == """Hello App1!
"""
