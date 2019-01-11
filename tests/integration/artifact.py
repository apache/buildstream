#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors: Richard Maw <richard.maw@codethink.co.uk>
#

import os
import pytest

from tests.testutils import cli_integration as cli, create_artifact_share
from tests.testutils.site import HAVE_BWRAP, IS_LINUX

pytestmark = pytest.mark.integration


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_log(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Get the cache key of our test element
    result = cli.run(project=project, silent=True, args=[
        '--no-colors',
        'show', '--deps', 'none', '--format', '%{full-key}',
        'base.bst'
    ])
    key = result.output.strip()

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'base.bst'])
    assert result.exit_code == 0

    # Read the log via the element name
    result = cli.run(project=project, args=['artifact', 'log', 'base.bst'])
    assert result.exit_code == 0
    log = result.output

    # Read the log via the key
    result = cli.run(project=project, args=['artifact', 'log', 'test/base/' + key])
    assert result.exit_code == 0
    assert log == result.output

    # Read the log via glob
    result = cli.run(project=project, args=['artifact', 'log', 'test/base/*'])
    assert result.exit_code == 0
    # The artifact is cached under both a strong key and a weak key
    assert (log + log) == result.output


# Test that we can delete the artifact of the element which corresponds
# to the current project state
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_artifact_delete_element(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'integration.bst'

    # Build the element and ensure it's cached
    result = cli.run(project=project, args=['build', element])
    result.assert_success()
    assert cli.get_element_state(project, element) == 'cached'

    result = cli.run(project=project, args=['artifact', 'delete', element])
    result.assert_success()
    assert cli.get_element_state(project, element) != 'cached'


# Test that we can delete an artifact by specifying its ref.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_artifact_delete_artifact(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'integration.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'artifacts')
    cli.configure({'artifactdir': local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, 'cas', 'refs', 'heads', artifact))

    # Delete the artifact
    result = cli.run(project=project, args=['artifact', 'delete', artifact])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, 'cas', 'refs', 'heads', artifact))


# Test the `bst artifact delete` command with multiple, different arguments.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(IS_LINUX and not HAVE_BWRAP, reason='Only available with bubblewrap on Linux')
def test_artifact_delete_element_and_artifact(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'integration.bst'
    dep = 'base/base-alpine.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'artifacts')
    cli.configure({'artifactdir': local_cache})

    # First build an element so that we can find its artifact
    result = cli.run(project=project, args=['build', element])
    result.assert_success()
    assert cli.get_element_state(project, element) == 'cached'
    assert cli.get_element_state(project, dep) == 'cached'

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Explicitly check that the ARTIFACT exists in the cache
    assert os.path.exists(os.path.join(local_cache, 'cas', 'refs', 'heads', artifact))

    # Delete the artifact
    result = cli.run(project=project, args=['artifact', 'delete', artifact, dep])
    result.assert_success()

    # Check that the ARTIFACT is no longer in the cache
    assert not os.path.exists(os.path.join(local_cache, 'cas', 'refs', 'heads', artifact))

    # Check that the dependency ELEMENT is no longer cached
    assert cli.get_element_state(project, dep) != 'cached'


# Test that we receive the appropriate stderr when we try to delete an artifact
# that is not present in the cache.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_delete_unbuilt_artifact(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'integration.bst'

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), 'artifacts')
    cli.configure({'artifactdir': local_cache})

    # Ensure the element is not cached
    assert cli.get_element_state(project, element) != 'cached'

    # Obtain the artifact ref
    cache_key = cli.get_element_key(project, element)
    artifact = os.path.join('test', os.path.splitext(element)[0], cache_key)

    # Try deleting the uncached artifact
    result = cli.run(project=project, args=['artifact', 'delete', artifact])
    result.assert_success()

    expected_err = 'WARNING: {}, not found in local cache - no delete required\n'.format(artifact)
    assert result.stderr == expected_err
