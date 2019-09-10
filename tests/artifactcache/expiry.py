#
#  Copyright (C) 2018 Codethink Limited
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
#  Authors: Tristan Maat <tristan.maat@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import time

import pytest

from buildstream._cas import CASCache
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils import create_element_size, update_element_size, wait_for_cache_granularity


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "expiry"
)


def get_cache_usage(directory):
    cas_cache = CASCache(directory)
    try:
        wait = 0.1
        for _ in range(0, int(5 / wait)):
            used_size = cas_cache.get_cache_usage().used_size
            if used_size is not None:
                return used_size
            time.sleep(wait)

        assert False, "Unable to retrieve cache usage"
        return None
    finally:
        cas_cache.release_resources()


# Ensure that the cache successfully removes an old artifact if we do
# not have enough space left.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_expires(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000,
        }
    })

    # Create an element that uses almost the entire cache (an empty
    # ostree cache starts at about ~10KiB, so we need a bit of a
    # buffer)
    create_element_size('target.bst', project, element_path, [], 6000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Our cache should now be almost full. Let's create another
    # artifact and see if we can cause buildstream to delete the old
    # one.
    create_element_size('target2.bst', project, element_path, [], 6000000)
    res = cli.run(project=project, args=['build', 'target2.bst'])
    res.assert_success()

    # Check that the correct element remains in the cache
    states = cli.get_element_states(project, ['target.bst', 'target2.bst'])
    assert states['target.bst'] != 'cached'
    assert states['target2.bst'] == 'cached'


# Ensure that we don't end up deleting the whole cache (or worse) if
# we try to store an artifact that is too large to fit in the quota.
@pytest.mark.parametrize('size', [
    # Test an artifact that is obviously too large
    (500000),
    # Test an artifact that might be too large due to slight overhead
    # of storing stuff in ostree
    (399999)
])
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_too_large(cli, datafiles, size):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 400000
        }
    })

    # Create an element whose artifact is too large
    create_element_size('target.bst', project, element_path, [], size)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_main_error(ErrorDomain.STREAM, None)
    res.assert_task_error(ErrorDomain.CAS, 'cache-too-full')


@pytest.mark.datafiles(DATA_DIR)
def test_expiry_order(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'
    checkout = os.path.join(project, 'workspace')

    cli.configure({
        'cache': {
            'quota': 9000000
        }
    })

    # Create an artifact
    create_element_size('dep.bst', project, element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'dep.bst'])
    res.assert_success()

    # Create another artifact
    create_element_size('unrelated.bst', project, element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'unrelated.bst'])
    res.assert_success()

    # And build something else
    create_element_size('target.bst', project, element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    create_element_size('target2.bst', project, element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'target2.bst'])
    res.assert_success()

    wait_for_cache_granularity()

    # Now extract dep.bst
    res = cli.run(project=project, args=['artifact', 'checkout', 'dep.bst', '--directory', checkout])
    res.assert_success()

    # Finally, build something that will cause the cache to overflow
    create_element_size('expire.bst', project, element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'expire.bst'])
    res.assert_success()

    # While dep.bst was the first element to be created, it should not
    # have been removed.
    # Note that buildstream will reduce the cache to 50% of the
    # original size - we therefore remove multiple elements.
    check_elements = [
        'unrelated.bst', 'target.bst', 'target2.bst', 'dep.bst', 'expire.bst'
    ]
    states = cli.get_element_states(project, check_elements)
    assert (tuple(states[element] for element in check_elements) ==
            ('buildable', 'buildable', 'buildable', 'cached', 'cached', ))


# Ensure that we don't accidentally remove an artifact from something
# in the current build pipeline, because that would be embarassing,
# wouldn't it?
@pytest.mark.datafiles(DATA_DIR)
def test_keep_dependencies(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000
        }
    })

    # Create a pretty big dependency
    create_element_size('dependency.bst', project, element_path, [], 5000000)
    res = cli.run(project=project, args=['build', 'dependency.bst'])
    res.assert_success()

    # Now create some other unrelated artifact
    create_element_size('unrelated.bst', project, element_path, [], 4000000)
    res = cli.run(project=project, args=['build', 'unrelated.bst'])
    res.assert_success()

    # Check that the correct element remains in the cache
    states = cli.get_element_states(project, ['dependency.bst', 'unrelated.bst'])
    assert states['dependency.bst'] == 'cached'
    assert states['unrelated.bst'] == 'cached'

    # We try to build an element which depends on the LRU artifact,
    # and could therefore fail if we didn't make sure dependencies
    # aren't removed.
    #
    # Since some artifact caches may implement weak cache keys by
    # duplicating artifacts (bad!) we need to make this equal in size
    # or smaller than half the size of its dependencies.
    #
    create_element_size('target.bst', project,
                        element_path, ['dependency.bst'], 2000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    states = cli.get_element_states(project, ['target.bst', 'unrelated.bst'])
    assert states['target.bst'] == 'cached'
    assert states['dependency.bst'] == 'cached'
    assert states['unrelated.bst'] != 'cached'


# Assert that we never delete a dependency required for a build tree
@pytest.mark.datafiles(DATA_DIR)
def test_never_delete_required(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000
        },
        'scheduler': {
            'fetchers': 1,
            'builders': 1
        }
    })

    # Create a linear build tree
    create_element_size('dep1.bst', project, element_path, [], 8000000)
    create_element_size('dep2.bst', project, element_path, ['dep1.bst'], 8000000)
    create_element_size('dep3.bst', project, element_path, ['dep2.bst'], 8000000)
    create_element_size('target.bst', project, element_path, ['dep3.bst'], 8000000)

    # Build dep1.bst, which should fit into the cache.
    res = cli.run(project=project, args=['build', 'dep1.bst'])
    res.assert_success()

    # We try to build this pipeline, but it's too big for the
    # cache. Since all elements are required, the build should fail.
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_main_error(ErrorDomain.STREAM, None)
    res.assert_task_error(ErrorDomain.CAS, 'cache-too-full')

    states = cli.get_element_states(project, ['target.bst'])
    assert states['dep1.bst'] == 'cached'
    assert states['dep2.bst'] != 'cached'
    assert states['dep3.bst'] != 'cached'
    assert states['target.bst'] != 'cached'


# Assert that we never delete a dependency required for a build tree,
# even when the artifact cache was previously populated with
# artifacts we do not require, and the new build is run with dynamic tracking.
#
@pytest.mark.datafiles(DATA_DIR)
def test_never_delete_required_track(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000
        },
        'scheduler': {
            'fetchers': 1,
            'builders': 1
        }
    })

    # Create a linear build tree
    repo_dep1 = create_element_size('dep1.bst', project, element_path, [], 2000000)
    repo_dep2 = create_element_size('dep2.bst', project, element_path, ['dep1.bst'], 2000000)
    repo_dep3 = create_element_size('dep3.bst', project, element_path, ['dep2.bst'], 2000000)
    repo_target = create_element_size('target.bst', project, element_path, ['dep3.bst'], 2000000)

    # This should all fit into the artifact cache
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    # They should all be cached
    states = cli.get_element_states(project, ['target.bst'])
    assert states['dep1.bst'] == 'cached'
    assert states['dep2.bst'] == 'cached'
    assert states['dep3.bst'] == 'cached'
    assert states['target.bst'] == 'cached'

    # Now increase the size of all the elements
    #
    update_element_size('dep1.bst', project, repo_dep1, 8000000)
    update_element_size('dep2.bst', project, repo_dep2, 8000000)
    update_element_size('dep3.bst', project, repo_dep3, 8000000)
    update_element_size('target.bst', project, repo_target, 8000000)

    # Now repeat the same test we did in test_never_delete_required(),
    # except this time let's add dynamic tracking
    #
    res = cli.run(project=project, args=['build', '--track-all', 'target.bst'])
    res.assert_main_error(ErrorDomain.STREAM, None)
    res.assert_task_error(ErrorDomain.CAS, 'cache-too-full')

    # Expect the almost the same result that we did in test_never_delete_required()
    # As the source will be downloaded first, we will be over the limit once
    # the source for dep2.bst is downloaded
    #
    states = cli.get_element_states(project, ['target.bst'])
    assert states['dep1.bst'] == 'cached'
    assert states['dep2.bst'] == 'buildable'
    assert states['dep3.bst'] != 'cached'
    assert states['target.bst'] != 'cached'


# Ensure that only valid cache quotas make it through the loading
# process.
#
# Parameters:
#    quota (str): A quota size configuration for the config file
#    err_domain (str): An ErrorDomain, or 'success' or 'warning'
#    err_reason (str): A reson to compare with an error domain
#
# If err_domain is 'success', then err_reason is unused.
#
@pytest.mark.parametrize("quota,err_domain,err_reason", [
    # Valid configurations
    ("1", 'success', None),
    ("1K", 'success', None),
    ("50%", 'success', None),
    ("infinity", 'success', None),
    ("0", 'success', None),
    # Invalid configurations
    ("-1", ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA),
    ("pony", ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA),
    ("200%", ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA),
])
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_cache_quota(cli, datafiles, quota, err_domain, err_reason):
    project = str(datafiles)
    os.makedirs(os.path.join(project, 'elements'))

    cli.configure({
        'cache': {
            'quota': quota,
        },
    })

    res = cli.run(project=project, args=['workspace', 'list'])

    if err_domain == 'success':
        res.assert_success()
    else:
        res.assert_main_error(err_domain, err_reason)


# Ensures that when launching BuildStream with a full artifact cache,
# the cache size and cleanup jobs are run before any other jobs.
#
@pytest.mark.datafiles(DATA_DIR)
def test_cleanup_first(cli, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000,
        }
    })

    # Create an element that uses almost the entire cache (an empty
    # ostree cache starts at about ~10KiB, so we need a bit of a
    # buffer)
    create_element_size('target.bst', project, element_path, [], 8000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Now configure with a smaller quota, create a situation
    # where the cache must be cleaned up before building anything else.
    #
    # Fix the fetchers and builders just to ensure a predictable
    # sequence of events (although it does not effect this test)
    cli.configure({
        'cache': {
            'quota': 5000000,
        },
        'scheduler': {
            'fetchers': 1,
            'builders': 1
        }
    })

    # Our cache is now more than full, BuildStream
    create_element_size('target2.bst', project, element_path, [], 4000000)
    res = cli.run(project=project, args=['build', 'target2.bst'])
    res.assert_success()

    # Check that the correct element remains in the cache
    states = cli.get_element_states(project, ['target.bst', 'target2.bst'])
    assert states['target.bst'] != 'cached'
    assert states['target2.bst'] == 'cached'


@pytest.mark.datafiles(DATA_DIR)
def test_cache_usage_monitor(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_path = 'elements'

    assert get_cache_usage(cli.directory) == 0

    ELEMENT_SIZE = 1000000
    create_element_size('target.bst', project, element_path, [], ELEMENT_SIZE)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    assert get_cache_usage(cli.directory) >= ELEMENT_SIZE
