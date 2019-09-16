# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains
from buildstream.testing._utils.site import HAVE_SANDBOX


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'project'
)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_filter_pass_integration(datafiles, cli):
    project = str(datafiles)

    # Passing integration commands should build nicely
    result = cli.run(project=project, args=['build', 'filter/filter.bst'])
    result.assert_success()

    # Checking out the element should work
    checkout_dir = os.path.join(project, 'filter')
    result = cli.run(project=project, args=['artifact', 'checkout', '--integrate', '--hardlinks',
                                            '--directory', checkout_dir, 'filter/filter.bst'])
    result.assert_success()

    # Check that the integration command was run
    assert_contains(checkout_dir, ['/foo'])
    shutil.rmtree(checkout_dir)
