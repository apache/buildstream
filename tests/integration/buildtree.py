#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import tarfile
import shutil

import pytest

from buildstream._testing import cli, cli_integration, Cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain
from buildstream._testing._utils.site import HAVE_SANDBOX

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")

#
# Verify fail cases when checkout buildtree
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_checkout_fail(cli, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(cli.directory, "checkout")
    tar = os.path.join(cli.directory, "source-checkout.tar")

    res = cli.run(project=project, args=["--cache-buildtrees", "never", "build", element_name])
    res.assert_success()

    res = cli.run(project=project, args=["buildtree", "checkout", "--directory", checkout, element_name])
    res.assert_main_error(ErrorDomain.STREAM, "missing-buildtree-artifact-created-without-buildtree")

    res = cli.run(project=project, args=["buildtree", "checkout", "--compression", "gz", "--directory", checkout, element_name])
    assert res.exit_code != 0
    assert "ERROR: --compression can only be provided if --tar is provided" in res.stderr


    res = cli.run(project=project, args=["buildtree", "checkout", "--tar", tar, "--directory", checkout, element_name])
    assert res.exit_code != 0
    assert "ERROR: options --directory and --tar conflict" in res.stderr

    res = cli.run(project=project, args=["buildtree", "checkout", "--tar", tar, "--hardlinks", element_name])
    assert res.exit_code != 0
    assert "ERROR: options --hardlinks and --tar conflict" in res.stderr

#
# Verify checkout buildtree
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_buildtree_checkout(cli, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(cli.directory, "checkout")
    tar = os.path.join(cli.directory, "source-checkout.tar")

    # Build only once with cached buildtree
    res = cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    # verify checkout buildtree only
    res = cli.run(project=project, args=["buildtree", "checkout", "--directory", checkout, element_name])
    res.assert_success()

    expect_buildtree = ['test']
    assert expect_buildtree == os.listdir(checkout)
    shutil.rmtree(checkout)

    # verify checkout buildtree only tar
    res = cli.run(project=project, args=["buildtree", "checkout", "--tar", tar, element_name])
    res.assert_success()

    assert os.path.exists(tar)
    with tarfile.open(tar) as tf:
        expected_content = [os.path.join(".", expect) for expect in expect_buildtree]
        tar_members = [f.name for f in tf]
        assert tar_members == expected_content
    os.remove(tar)

    # verify checkout buildtree only tar in different compression formats
    for compression in ["gz", "xz", "bz2"]:
        res = cli.run(project=project, args=["buildtree", "checkout", "--tar", "-", "--compression", compression, element_name], binary_capture=True)
        res.assert_success()

        with open(tar, "wb") as f:
            f.write(res.output)

        with tarfile.open(tar, "r:" + compression) as tf:
            expected_content = [os.path.join(".", expect) for expect in expect_buildtree]
            tar_members = [f.name for f in tf]
            assert tar_members == expected_content

        os.remove(tar)

    # verify checkout whole buildroot
    res = cli.run(project=project, args=["buildtree", "checkout", "--buildroot", "--directory", checkout, element_name])
    res.assert_success()

    expect_buildroot = ['lib', 'media', 'proc', 'usr', 'home', 'buildstream-install', 'dev', 'var', 'sys', 'bin', 'run', 'buildstream', 'tmp', 'sbin', 'etc', 'mnt', 'srv', 'root']
    assert expect_buildroot == os.listdir(checkout)

    # verify checkout whole buildroot with force flag
    res = cli.run(project=project, args=["buildtree", "checkout", "--force", "--directory", checkout, element_name])
    res.assert_success()

    assert sorted([*expect_buildtree, *expect_buildroot]) == sorted(os.listdir(checkout))

    shutil.rmtree(checkout)

    # verify checkout whole buildroot with hardlinks
    res = cli.run(project=project, args=["buildtree", "checkout", "--buildroot", "--hardlinks", "--directory", checkout, element_name])
    res.assert_success()

    expect_buildroot = ['lib', 'media', 'proc', 'usr', 'home', 'buildstream-install', 'dev', 'var', 'sys', 'bin', 'run', 'buildstream', 'tmp', 'sbin', 'etc', 'mnt', 'srv', 'root']
    assert expect_buildroot == os.listdir(checkout)
    shutil.rmtree(checkout)
