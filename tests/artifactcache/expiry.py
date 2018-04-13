import os

import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from tests.testutils import cli


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "expiry"
)


def create_element(name, path, dependencies, size):
    os.makedirs(path, exist_ok=True)

    # Create a file to be included in this element's artifact
    with open(os.path.join(path, name + '_data'), 'wb+') as f:
        f.write(os.urandom(size))

    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': os.path.join(path, name + '_data')
            }
        ],
        'depends': dependencies
    }
    _yaml.dump(element, os.path.join(path, name))


# Ensure that the cache successfully removes an old artifact if we do
# not have enough space left.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_expires(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')
    checkout = os.path.join(project, 'checkout')

    cli.configure({
        'cache-quota': 10000000,
        'cache-headroom': 0
    })

    # Create an element that uses almost the entire cache (an empty
    # ostree cache starts at about ~10KiB, so we need a bit of a
    # buffer)
    create_element('target.bst', element_path, [], 6000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    # Our cache should now be almost full. Let's create another
    # artifact and see if we can cause buildstream to delete the old
    # one.
    create_element('target2.bst', element_path, [], 6000000)
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
    element_path = os.path.join(project, 'elements')

    cli.configure({
        'cache-quota': 400000,
        'cache-headroom': 0
    })

    # Create an element whose artifact is too large
    create_element('target.bst', element_path, [], size)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_main_error(ErrorDomain.PIPELINE, None)


@pytest.mark.datafiles(DATA_DIR)
def test_expiry_order(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')
    checkout = os.path.join(project, 'workspace')

    cli.configure({
        'cache-quota': 10000000,
        'cache-headroom': 0
    })

    # Create an artifact
    create_element('dep.bst', element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'dep.bst'])
    res.assert_success()

    # Create another artifact
    create_element('unrelated.bst', element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'unrelated.bst'])
    res.assert_success()

    # Now extract dep.bst
    res = cli.run(project=project, args=['checkout', 'dep.bst', checkout])
    res.assert_success()

    # And build something else
    create_element('target.bst', element_path, [], 2000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    # Finally, build something that will cause the cache to overflow
    create_element('expire.bst', element_path, [], 5000000)
    res = cli.run(project=project, args=['build', 'expire.bst'])
    res.assert_success()

    # We *should* have removed unrelated.bst, as opposed to any of the
    # other artifacts.
    assert cli.get_element_state(project, 'dep.bst') == 'cached'
    assert cli.get_element_state(project, 'target.bst') == 'cached'
    assert cli.get_element_state(project, 'expire.bst') == 'cached'
    assert cli.get_element_state(project, 'unrelated.bst') != 'cached'


# Ensure that we don't accidentally remove an artifact from something
# in the current build pipeline, because that would be embarassing,
# wouldn't it?
@pytest.mark.datafiles(DATA_DIR)
def test_keep_dependencies(cli, datafiles, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    cache_location = os.path.join(project, 'cache', 'artifacts', 'ostree')

    cli.configure({
        'cache-quota': 10000000,
        'cache-headroom': 0
    })

    # Create a pretty big dependency
    create_element('dependency.bst', element_path, [], 4000000)
    res = cli.run(project=project, args=['build', 'dependency.bst'])
    res.assert_success()

    # Now create some other unrelated artifact
    create_element('unrelated.bst', element_path, [], 4000000)
    res = cli.run(project=project, args=['build', 'unrelated.bst'])
    res.assert_success()

    # Check that the correct element remains in the cache
    assert cli.get_element_state(project, 'dependency.bst') == 'cached'
    assert cli.get_element_state(project, 'unrelated.bst') == 'cached'

    # We try to build an element which depends on the LRU artifact,
    # and could therefore fail if we didn't make sure dependencies
    # aren't removed.
    create_element('target.bst', element_path, ['dependency.bst'], 4000000)
    res = cli.run(project=project, args=['build', 'target.bst'])
    res.assert_success()

    assert cli.get_element_state(project, 'unrelated.bst') != 'cached'
    assert cli.get_element_state(project, 'dependency.bst') == 'cached'
    assert cli.get_element_state(project, 'target.bst') == 'cached'


# Ensure that only valid cache quotas make it through the loading
# process.
@pytest.mark.parametrize("quota,headroom,success", [
    ("1", "1", True),
    ("1K", "1", True),
    ("50%", "1", True),
    ("infinity", "1", True),
    ("0", "0", True),
    ("-1", "0", False),
    ("pony", "horse", False),
    ("0", "-1", False),
    ("200%", "0", False)
])
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_cache_quota(cli, datafiles, tmpdir, quota, headroom, success):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')

    cli.configure({
        'cache-quota': quota,
        'cache-headroom': headroom
    })

    res = cli.run(project=project, args=['workspace', 'list'])
    if success:
        res.assert_success()
    else:
        res.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
