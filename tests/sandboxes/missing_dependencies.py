# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils.site import IS_LINUX

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "missing-dependencies",
)


@pytest.mark.skipif(not IS_LINUX, reason='Only available on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_missing_brwap_has_nice_error_message(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, 'elements', 'element.bst')

    # Write out our test target
    element = {
        'kind': 'script',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build',
            },
        ],
        'config': {
            'commands': [
                'false',
            ],
        },
    }
    _yaml.dump(element, element_path)

    # Build without access to host tools, this should fail with a nice error
    result = cli.run(
        project=project, args=['build', 'element.bst'], env={'PATH': ''})
    result.assert_task_error(ErrorDomain.SANDBOX, 'unavailable-local-sandbox')
    assert "not found" in result.stderr


@pytest.mark.skipif(not IS_LINUX, reason='Only available on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_old_brwap_has_nice_error_message(cli, datafiles, tmp_path):
    bwrap = tmp_path.joinpath('bin/bwrap')
    bwrap.parent.mkdir()
    with bwrap.open('w') as fp:
        fp.write('''
            #!/bin/sh
            echo bubblewrap 0.0.1
        '''.strip())

    bwrap.chmod(0o755)

    project = str(datafiles)
    element_path = os.path.join(project, 'elements', 'element3.bst')

    # Write out our test target
    element = {
        'kind': 'script',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build',
            },
        ],
        'config': {
            'commands': [
                'false',
            ],
        },
    }
    _yaml.dump(element, element_path)

    # Build without access to host tools, this should fail with a nice error
    result = cli.run(
        project=project,
        args=['--debug', '--verbose', 'build', 'element3.bst'],
        env={'PATH': str(tmp_path.joinpath('bin'))})
    result.assert_task_error(ErrorDomain.SANDBOX, 'unavailable-local-sandbox')
    assert "too old" in result.stderr
