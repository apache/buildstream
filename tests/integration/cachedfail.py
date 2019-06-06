# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain
from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_BWRAP, HAVE_SANDBOX, IS_LINUX

from tests.conftest import clean_platform_cache
from tests.testutils import create_artifact_share


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_build_checkout_cached_fail(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, 'elements', 'element.bst')
    checkout = os.path.join(cli.directory, 'checkout')

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
                'touch %{install-root}/foo',
                'false',
            ],
        },
    }
    _yaml.dump(element, element_path)

    # Try to build it, this should result in a failure that contains the content
    result = cli.run(project=project, args=['build', 'element.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, 'element.bst') == 'failed'

    # Now check it out
    result = cli.run(project=project, args=[
        'artifact', 'checkout', 'element.bst', '--directory', checkout
    ])
    result.assert_success()

    # Check that the checkout contains the file created before failure
    filename = os.path.join(checkout, 'foo')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_build_depend_on_cached_fail(cli, datafiles):
    project = str(datafiles)
    dep_path = os.path.join(project, 'elements', 'dep.bst')
    target_path = os.path.join(project, 'elements', 'target.bst')

    dep = {
        'kind': 'script',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build',
            },
        ],
        'config': {
            'commands': [
                'touch %{install-root}/foo',
                'false',
            ],
        },
    }
    _yaml.dump(dep, dep_path)
    target = {
        'kind': 'script',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build',
            },
            {
                'filename': 'dep.bst',
                'type': 'build',
            },
        ],
        'config': {
            'commands': [
                'test -e /foo',
            ],
        },
    }
    _yaml.dump(target, target_path)

    # Try to build it, this should result in caching a failure to build dep
    result = cli.run(project=project, args=['build', 'dep.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, 'dep.bst') == 'failed'

    # Now we should fail because we've a cached fail of dep
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's not yet built, since one of its dependencies isn't ready.
    assert cli.get_element_state(project, 'target.bst') == 'waiting'


@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("on_error", ("continue", "quit"))
def test_push_cached_fail(cli, tmpdir, datafiles, on_error):
    if on_error == 'quit':
        pytest.xfail('https://gitlab.com/BuildStream/buildstream/issues/534')

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
                # Ensure unique cache key for different test variants
                'TEST="{}"'.format(os.environ.get('PYTEST_CURRENT_TEST')),
            ],
        },
    }
    _yaml.dump(element, element_path)

    with create_artifact_share(os.path.join(str(tmpdir), 'remote')) as share:
        cli.configure({
            'artifacts': {'url': share.repo, 'push': True},
        })

        # Build the element, continuing to finish active jobs on error.
        result = cli.run(project=project, args=['--on-error={}'.format(on_error), 'build', 'element.bst'])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # This element should have failed
        assert cli.get_element_state(project, 'element.bst') == 'failed'
        # This element should have been pushed to the remote
        assert share.has_artifact(cli.get_artifact_name(project, 'test', 'element.bst'))


@pytest.mark.skipif(not (IS_LINUX and HAVE_BWRAP), reason='Only available with bubblewrap on Linux')
@pytest.mark.datafiles(DATA_DIR)
def test_host_tools_errors_are_not_cached(cli, datafiles):
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
                'true',
            ],
        },
    }
    _yaml.dump(element, element_path)

    # Build without access to host tools, this will fail
    result1 = cli.run(project=project, args=['build', 'element.bst'], env={'PATH': ''})
    result1.assert_task_error(ErrorDomain.SANDBOX, 'unavailable-local-sandbox')
    assert cli.get_element_state(project, 'element.bst') == 'buildable'

    # clean the cache before running again
    clean_platform_cache()

    # When rebuilding, this should work
    result2 = cli.run(project=project, args=['build', 'element.bst'])
    result2.assert_success()
    assert cli.get_element_state(project, 'element.bst') == 'cached'
