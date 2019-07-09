# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
from unittest import mock

from buildstream import _yaml
from buildstream._cas.cascache import CACHE_SIZE_FILE
from buildstream._exceptions import ErrorDomain
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils import create_element_size

# XXX: Currently lacking:
#      * A way to check whether it's faster to read cache size on
#        successive invocations.
#      * A way to check whether the cache size file has been read.


def create_project(project_dir):
    project_file = os.path.join(project_dir, "project.conf")
    project_conf = {
        "name": "test"
    }
    _yaml.roundtrip_dump(project_conf, project_file)
    element_name = "test.bst"
    create_element_size(element_name, project_dir, ".", [], 1024)


def test_cache_size_roundtrip(cli, tmpdir):
    # Builds (to put files in the cache), then invokes buildstream again
    # to check nothing breaks

    # Create project
    project_dir = str(tmpdir)
    create_project(project_dir)

    # Build, to populate the cache
    res = cli.run(project=project_dir, args=["build", "test.bst"])
    res.assert_success()

    # Show, to check that nothing breaks while reading cache size
    res = cli.run(project=project_dir, args=["show", "test.bst"])
    res.assert_success()


def test_cache_size_write(cli, tmpdir):
    # Builds (to put files in the cache), then checks a number is
    # written to the cache size file.

    project_dir = str(tmpdir)
    create_project(project_dir)

    # Artifact cache must be in a known place
    casdir = os.path.join(project_dir, "cas")
    cli.configure({"cachedir": project_dir})

    # Build, to populate the cache
    res = cli.run(project=project_dir, args=["build", "test.bst"])
    res.assert_success()

    # Inspect the artifact cache
    sizefile = os.path.join(casdir, CACHE_SIZE_FILE)
    assert os.path.isfile(sizefile)


def test_quota_over_1024T(cli, tmpdir):
    KiB = 1024
    MiB = (KiB * 1024)
    GiB = (MiB * 1024)
    TiB = (GiB * 1024)

    cli.configure({
        'cache': {
            'quota': 2048 * TiB
        }
    })
    project = tmpdir.join("main")
    os.makedirs(str(project))
    _yaml.roundtrip_dump({'name': 'main'}, str(project.join("project.conf")))

    volume_space_patch = mock.patch(
        "buildstream._cas.CASQuota._get_cache_volume_size",
        autospec=True,
        return_value=(1025 * TiB, 1025 * TiB)
    )

    with volume_space_patch:
        result = cli.run(project, args=["build", "file.bst"])
        result.assert_main_error(ErrorDomain.CAS, 'insufficient-storage-for-quota')
