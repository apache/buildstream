import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_manual_element(name, path, config, variables, environment):
    element = {
        'kind': 'manual',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'config': config,
        'variables': variables,
        'environment': environment
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
def test_manual_element(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'import/import.bst'

    create_manual_element(element_name, element_path, {
        'configure-commands': ["echo './configure' >> test"],
        'build-commands': ["echo 'make' >> test"],
        'install-commands': [
            "echo 'make install' >> test",
            "cp test %{install-root}"
        ],
        'strip-commands': ["echo 'strip' >> %{install-root}/test"]
    }, {}, {})

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['checkout', element_name, checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == """./configure
make
make install
strip
"""


@pytest.mark.datafiles(DATA_DIR)
def test_manual_element_environment(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'import/import.bst'

    create_manual_element(element_name, element_path, {
        'install-commands': [
            "echo $V >> test",
            "cp test %{install-root}"
        ]
    }, {
    }, {
        'V': 2
    })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['checkout', element_name, checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == "2\n"


@pytest.mark.datafiles(DATA_DIR)
def test_manual_element_noparallel(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'import/import.bst'

    create_manual_element(element_name, element_path, {
        'install-commands': [
            "echo $MAKEFLAGS >> test",
            "echo $V >> test",
            "cp test %{install-root}"
        ]
    }, {
        'notparallel': True
    }, {
        'MAKEFLAGS': '-j%{max-jobs} -Wall',
        'V': 2
    })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['checkout', element_name, checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == """-j1 -Wall
2
"""
