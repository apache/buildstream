import io
import os
import sys
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import walk_dir


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_compose_element(name, path, config={}):
    element = {
        'kind': 'compose',
        'depends': [{
            'filename': 'compose/amhello.bst',
            'type': 'build'
        }, {
            'filename': 'compose/test.bst',
            'type': 'build'
        }],
        'config': config
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("include_domains,exclude_domains,expected", [
    # Test flat inclusion
    ([], [], ['/usr', '/usr/lib', '/usr/bin',
              '/usr/share', '/usr/lib/debug',
              '/usr/lib/debug/usr', '/usr/lib/debug/usr/bin',
              '/usr/lib/debug/usr/bin/hello', '/usr/bin/hello',
              '/usr/share/doc', '/usr/share/doc/amhello',
              '/usr/share/doc/amhello/README',
              '/tests', '/tests/test']),
    # Test only runtime
    (['runtime'], [], ['/usr', '/usr/lib', '/usr/share',
                       '/usr/bin', '/usr/bin/hello']),
    # Test with runtime and doc
    (['runtime', 'doc'], [], ['/usr', '/usr/lib', '/usr/share',
                              '/usr/bin', '/usr/bin/hello',
                              '/usr/share/doc', '/usr/share/doc/amhello',
                              '/usr/share/doc/amhello/README']),
    # Test with only runtime excluded
    ([], ['runtime'], ['/usr', '/usr/lib', '/usr/share',
                       '/usr/lib/debug', '/usr/lib/debug/usr',
                       '/usr/lib/debug/usr/bin',
                       '/usr/lib/debug/usr/bin/hello',
                       '/usr/share/doc', '/usr/share/doc/amhello',
                       '/usr/share/doc/amhello/README',
                       '/tests', '/tests/test']),
    # Test with runtime and doc excluded
    ([], ['runtime', 'doc'], ['/usr', '/usr/lib', '/usr/share',
                              '/usr/lib/debug', '/usr/lib/debug/usr',
                              '/usr/lib/debug/usr/bin',
                              '/usr/lib/debug/usr/bin/hello',
                              '/tests', '/tests/test']),
    # Test with runtime simultaneously in- and excluded
    (['runtime'], ['runtime'], ['/usr', '/usr/lib', '/usr/share']),
    # Test with runtime included and doc excluded
    (['runtime'], ['doc'], ['/usr', '/usr/lib', '/usr/share',
                            '/usr/bin', '/usr/bin/hello']),
    # Test including a custom 'test' domain
    (['test'], [], ['/usr', '/usr/lib', '/usr/share',
                    '/tests', '/tests/test']),
    # Test excluding a custom 'test' domain
    ([], ['test'], ['/usr', '/usr/lib', '/usr/bin',
                    '/usr/share', '/usr/lib/debug',
                    '/usr/lib/debug/usr', '/usr/lib/debug/usr/bin',
                    '/usr/lib/debug/usr/bin/hello', '/usr/bin/hello',
                    '/usr/share/doc', '/usr/share/doc/amhello',
                    '/usr/share/doc/amhello/README'])
])
def test_compose_include(cli, tmpdir, datafiles, include_domains,
                         exclude_domains, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'compose/compose-amhello.bst'

    # Create a yaml configuration from the specified include and
    # exclude domains
    config = {
        'include': include_domains,
        'exclude': exclude_domains
    }
    create_compose_element(element_name, element_path, config=config)

    result = cli.run(project=project, args=['track', 'compose/amhello.bst'])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert set(walk_dir(checkout)) == set(expected)
