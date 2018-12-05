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

import os
from unittest import mock

import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from tests.testutils import cli, create_element_size, update_element_size, wait_for_cache_granularity


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "expiry"
)


# Ensure that the cache successfully removes an old artifact if we do
# not have enough space left.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_expires(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')
    checkout = os.path.join(project, 'checkout')

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
    assert cli.get_element_state(project, 'target.bst') != 'cached'
    assert cli.get_element_state(project, 'target2.bst') == 'cached'


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
def test_artifact_too_large(cli, datafiles, tmpdir, size):
    project = os.path.join(datafiles.dirname, datafiles.basename)
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
    res.assert_task_error(ErrorDomain.ARTIFACT, 'cache-too-full')


@pytest.mark.datafiles(DATA_DIR)
def test_expiry_order(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')
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

    assert (tuple(cli.get_element_state(project, element) for element in
                  ('unrelated.bst', 'target.bst', 'target2.bst', 'dep.bst', 'expire.bst')) ==
            ('buildable', 'buildable', 'buildable', 'cached', 'cached', ))


# Ensure that we don't accidentally remove an artifact from something
# in the current build pipeline, because that would be embarassing,
# wouldn't it?
@pytest.mark.datafiles(DATA_DIR)
def test_keep_dependencies(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')

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
    assert cli.get_element_state(project, 'dependency.bst') == 'cached'
    assert cli.get_element_state(project, 'unrelated.bst') == 'cached'

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

    assert cli.get_element_state(project, 'unrelated.bst') != 'cached'
    assert cli.get_element_state(project, 'dependency.bst') == 'cached'
    assert cli.get_element_state(project, 'target.bst') == 'cached'


# Assert that we never delete a dependency required for a build tree
@pytest.mark.datafiles(DATA_DIR)
def test_never_delete_required(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000
        },
        'scheduler': {
            'builders': 1
        }
    })

    # Create a linear build tree
    create_element_size('dep1.bst', project, element_path, [], 8000000)
    create_element_size('dep2.bst', project, element_path, ['dep1.bst'], 8000000)
    create_element_size('dep3.bst', project, element_path, ['dep2.bst'], 8000000)
    create_element_size('target.bst', project, element_path, ['dep3.bst'], 8000000)

    # We try to build this pipeline, but it's too big for the
    # cache. Since all elements are required, the build should fail.
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_main_error(ErrorDomain.STREAM, None)
    res.assert_task_error(ErrorDomain.ARTIFACT, 'cache-too-full')

    # Only the first artifact fits in the cache, but we expect
    # that the first *two* artifacts will be cached.
    #
    # This is because after caching the first artifact we must
    # proceed to build the next artifact, and we cannot really
    # know how large an artifact will be until we try to cache it.
    #
    # In this case, we deem it more acceptable to not delete an
    # artifact which caused the cache to outgrow the quota.
    #
    # Note that this test only works because we have forced
    # the configuration to build one element at a time, in real
    # life there may potentially be N-builders cached artifacts
    # which exceed the quota
    #
    assert cli.get_element_state(project, 'dep1.bst') == 'cached'
    assert cli.get_element_state(project, 'dep2.bst') == 'cached'

    assert cli.get_element_state(project, 'dep3.bst') != 'cached'
    assert cli.get_element_state(project, 'target.bst') != 'cached'


# Assert that we never delete a dependency required for a build tree,
# even when the artifact cache was previously populated with
# artifacts we do not require, and the new build is run with dynamic tracking.
#
@pytest.mark.datafiles(DATA_DIR)
def test_never_delete_required_track(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000
        },
        'scheduler': {
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
    assert cli.get_element_state(project, 'dep1.bst') == 'cached'
    assert cli.get_element_state(project, 'dep2.bst') == 'cached'
    assert cli.get_element_state(project, 'dep3.bst') == 'cached'
    assert cli.get_element_state(project, 'target.bst') == 'cached'

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
    res.assert_task_error(ErrorDomain.ARTIFACT, 'cache-too-full')

    # Expect the same result that we did in test_never_delete_required()
    #
    assert cli.get_element_state(project, 'dep1.bst') == 'cached'
    assert cli.get_element_state(project, 'dep2.bst') == 'cached'
    assert cli.get_element_state(project, 'dep3.bst') != 'cached'
    assert cli.get_element_state(project, 'target.bst') != 'cached'


# Ensure that only valid cache quotas make it through the loading
# process.
@pytest.mark.parametrize("quota,success", [
    ("1", True),
    ("1K", True),
    ("50%", True),
    ("infinity", True),
    ("0", True),
    ("-1", False),
    ("pony", False),
    ("7K", False),
    ("70%", False),
    ("200%", False)
])
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_cache_quota(cli, datafiles, tmpdir, quota, success):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    os.makedirs(os.path.join(project, 'elements'))

    cli.configure({
        'cache': {
            'quota': quota,
        }
    })

    # We patch how we get space information
    # Ideally we would instead create a FUSE device on which we control
    # everything.
    # If the value is a percentage, we fix the current values to take into
    # account the block size, since this is important in how we compute the size

    if quota.endswith("%"):  # We set the used space at 60% of total space
        stats = os.statvfs(".")
        free_space = 0.6 * stats.f_bsize * stats.f_blocks
        total_space = stats.f_bsize * stats.f_blocks
    else:
        free_space = 6000
        total_space = 10000

    volume_space_patch = mock.patch(
        "buildstream._artifactcache.artifactcache.ArtifactCache._get_volume_space_info_for",
        autospec=True,
        return_value=(free_space, total_space),
    )

    cache_size_patch = mock.patch(
        "buildstream._artifactcache.artifactcache.ArtifactCache.get_cache_size",
        autospec=True,
        return_value=0,
    )

    with volume_space_patch, cache_size_patch:
        res = cli.run(project=project, args=['workspace', 'list'])

    if success:
        res.assert_success()
    else:
        res.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_extract_expiry(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = 'elements'

    cli.configure({
        'cache': {
            'quota': 10000000,
        }
    })

    create_element_size('target.bst', project, element_path, [], 6000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()
    assert cli.get_element_state(project, 'target.bst') == 'cached'

    # Force creating extract
    res = cli.run(project=project, args=['artifact', 'checkout', 'target.bst',
                                         '--directory', os.path.join(str(tmpdir), 'checkout')])
    res.assert_success()

    extractdir = os.path.join(project, 'cache', 'artifacts', 'extract', 'test', 'target')
    extracts = os.listdir(extractdir)
    assert(len(extracts) == 1)
    extract = os.path.join(extractdir, extracts[0])

    # Remove target.bst from artifact cache
    create_element_size('target2.bst', project, element_path, [], 6000000)
    res = cli.run(project=project, args=['build', 'target2.bst'])
    res.assert_success()
    assert cli.get_element_state(project, 'target.bst') != 'cached'

    # Now the extract should be removed.
    assert not os.path.exists(extract)
