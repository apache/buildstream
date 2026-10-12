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

import pytest

from buildstream._testing import cli, cli_integration, Cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain
from buildstream._testing._utils.site import HAVE_SANDBOX

from tests.testutils import create_artifact_share

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


#
# Checkout the buildtree and the buildroot of a build element
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize("hardlinks", [False, True], ids=["copy", "hardlinks"])
def test_checkout_buildtree(cli_integration, tmpdir, datafiles, hardlinks):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    args = ["artifact", "checkout", "--buildtree", "--directory", checkout, element_name]
    if hardlinks:
        args += ["--hardlinks"]
    res = cli_integration.run(project=project, args=args)
    res.assert_success()

    # Only the content of the build directory is checked out
    assert os.listdir(checkout) == ["test"]
    with open(os.path.join(checkout, "test"), encoding="utf-8") as f:
        assert f.read() == "Hi\n"

    checkout = os.path.join(str(tmpdir), "checkout-buildroot")
    args = ["artifact", "checkout", "--buildroot", "--directory", checkout, element_name]
    if hardlinks:
        args += ["--hardlinks"]
    res = cli_integration.run(project=project, args=args)
    res.assert_success()

    # The whole build sandbox is checked out, including the build directory
    with open(
        os.path.join(checkout, "buildstream", "test", "build-shell", "buildtree.bst", "test"), encoding="utf-8"
    ) as f:
        assert f.read() == "Hi\n"
    assert os.path.lexists(os.path.join(checkout, "bin", "sh"))


#
# Checkout the buildtree and the buildroot as a tarball
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize("compression", [None, "gz", "xz", "bz2"])
def test_checkout_buildtree_tar(cli_integration, tmpdir, datafiles, compression):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    tar = os.path.join(str(tmpdir), "buildtree.tar")

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    args = ["artifact", "checkout", "--buildtree", "--tar", tar, element_name]
    if compression:
        args += ["--compression", compression]
    res = cli_integration.run(project=project, args=args)
    res.assert_success()

    with tarfile.open(tar, "r:" + (compression or "")) as tf:
        assert tf.getnames() == [os.path.join(".", "test")]

    tar = os.path.join(str(tmpdir), "buildroot.tar")
    args = ["artifact", "checkout", "--buildroot", "--tar", tar, element_name]
    if compression:
        args += ["--compression", compression]
    res = cli_integration.run(project=project, args=args)
    res.assert_success()

    with tarfile.open(tar, "r:" + (compression or "")) as tf:
        names = tf.getnames()
        assert os.path.join(".", "buildstream", "test", "build-shell", "buildtree.bst", "test") in names
        assert os.path.join(".", "bin", "sh") in names


#
# Checkout the buildtree of a failed build
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_checkout_buildtree_from_failure(cli_integration, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/buildtree-fail.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    res = cli_integration.run(project=project, args=["build", element_name])
    res.assert_main_error(ErrorDomain.STREAM, None)

    res = cli_integration.run(
        project=project, args=["artifact", "checkout", "--buildtree", "--directory", checkout, element_name]
    )
    res.assert_success()
    assert "WARNING using a buildtree from a failed build" in res.stderr
    assert os.listdir(checkout) == ["test"]


#
# Elements which are not build elements only have a buildroot
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_checkout_buildtree_script_element(cli_integration, tmpdir, datafiles):
    project = str(datafiles)
    element_name = "build-shell/script.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    res = cli_integration.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
    res.assert_success()

    # Requesting the buildtree fails, suggesting to use the buildroot instead
    res = cli_integration.run(
        project=project, args=["artifact", "checkout", "--buildtree", "--directory", checkout, element_name]
    )
    res.assert_main_error(ErrorDomain.STREAM, "missing-buildtree-buildroot-available")
    assert "--buildroot" in res.stderr

    res = cli_integration.run(
        project=project, args=["artifact", "checkout", "--buildroot", "--directory", checkout, element_name]
    )
    res.assert_success()
    with open(os.path.join(checkout, "test"), encoding="utf-8") as f:
        assert f.read() == "Hi\n"


#
# Neither the buildtree nor the buildroot is available when they were not
# cached at build time
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize(
    "option,expect_error",
    [
        ("--buildtree", "missing-buildtree-artifact-created-without-buildtree"),
        ("--buildroot", "missing-buildroot-artifact-created-without-buildroot"),
    ],
)
def test_checkout_buildtree_not_created(cli, tmpdir, datafiles, option, expect_error):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    # Use a fresh cache, so that the artifact cannot have been built with
    # a buildtree by another test
    res = cli.run(project=project, args=["--cache-buildtrees", "never", "build", element_name])
    res.assert_success()

    res = cli.run(project=project, args=["artifact", "checkout", option, "--directory", checkout, element_name])
    res.assert_main_error(ErrorDomain.STREAM, expect_error)


#
# The artifact is not cached at all
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("option", ["--buildtree", "--buildroot"])
def test_checkout_buildtree_artifact_not_cached(cli, tmpdir, datafiles, option):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    res = cli.run(project=project, args=["artifact", "checkout", option, "--directory", checkout, element_name])
    res.assert_main_error(ErrorDomain.STREAM, "missing-artifact")


#
# The artifact was created with a buildtree, but the buildtree is only
# pulled from the remote with the pull-buildtrees configuration
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize(
    "option,expect_error",
    [
        ("--buildtree", "missing-buildtree-not-cached"),
        ("--buildroot", "missing-buildroot-not-cached"),
    ],
)
def test_checkout_buildtree_pull(cli, tmpdir, datafiles, option, expect_error):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"
    checkout = os.path.join(str(tmpdir), "checkout")

    with create_artifact_share(os.path.join(str(tmpdir), "share")) as share:
        # Build and push the artifact with its buildtree from a separate local cache
        build_cli = Cli(os.path.join(str(tmpdir), "build-cache"))
        build_cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        res = build_cli.run(project=project, args=["--cache-buildtrees", "always", "build", element_name])
        res.assert_success()
        assert share.get_artifact(build_cli.get_artifact_name(project, "test", element_name))

        # The artifact is only available in the share
        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})
        assert cli.get_element_state(project, element_name) != "cached"

        # Without pull-buildtrees, the artifact is pulled but not the buildtree
        res = cli.run(project=project, args=["artifact", "checkout", option, "--directory", checkout, element_name])
        res.assert_main_error(ErrorDomain.STREAM, expect_error)
        assert "pull-buildtrees" in res.stderr
        assert cli.get_element_state(project, element_name) == "cached"

        # With pull-buildtrees, the missing buildtree is pulled
        res = cli.run(
            project=project,
            args=["--pull-buildtrees", "artifact", "checkout", option, "--directory", checkout, element_name],
        )
        res.assert_success()
        if option == "--buildtree":
            assert os.listdir(checkout) == ["test"]
        else:
            assert os.path.exists(
                os.path.join(checkout, "buildstream", "test", "build-shell", "buildtree.bst", "test")
            )


#
# Invalid combinations of options
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "args,expect_error",
    [
        (["--buildtree", "--buildroot"], "ERROR: options --buildtree and --buildroot conflict"),
        (["--buildtree", "--deps", "none"], "ERROR: options --deps and --buildtree conflict"),
        (["--buildroot", "--deps", "build"], "ERROR: options --deps and --buildroot conflict"),
        (["--buildtree", "--integrate"], "ERROR: options --integrate/--no-integrate and --buildtree conflict"),
        (["--buildroot", "--no-integrate"], "ERROR: options --integrate/--no-integrate and --buildroot conflict"),
    ],
)
def test_checkout_buildtree_conflicting_options(cli, datafiles, args, expect_error):
    project = str(datafiles)
    element_name = "build-shell/buildtree.bst"

    res = cli.run(project=project, args=["artifact", "checkout", *args, element_name])
    assert res.exit_code != 0
    assert expect_error in res.stderr
