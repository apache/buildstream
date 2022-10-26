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

from buildstream._testing import cli  # pylint: disable=unused-import

from buildstream import utils, _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def generate_remote_import_element(input_path, output_path):
    return {
        "kind": "import",
        "sources": [
            {
                "kind": "remote",
                "url": "file://{}".format(input_path),
                "filename": output_path,
                "ref": utils.sha256sum(input_path),
            }
        ],
    }


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "with_workspace,guess_element",
    [(True, True), (True, False), (False, False)],
    ids=["workspace-guess", "workspace-no-guess", "no-workspace-no-guess"],
)
def test_source_checkout(datafiles, cli, tmpdir_factory, with_workspace, guess_element):
    tmpdir = tmpdir_factory.mktemp(os.path.basename(__file__))
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "checkout-deps.bst"
    workspace = os.path.join(str(tmpdir), "workspace")
    elm_cmd = [target] if not guess_element else []

    if with_workspace:
        ws_cmd = ["-C", workspace]
        result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, target])
        result.assert_success()
    else:
        ws_cmd = []

    args = ws_cmd + ["source", "checkout", "--deps", "none", "--directory", checkout, *elm_cmd]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, "checkout-deps", "etc", "buildstream", "config"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("force_flag", ["--force", "-f"])
def test_source_checkout_force(datafiles, cli, force_flag):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "checkout-deps.bst"

    # Make the checkout directory with 'some-thing' inside it
    os.makedirs(os.path.join(checkout, "some-thing"))

    result = cli.run(
        project=project, args=["source", "checkout", force_flag, "--deps", "none", "--directory", checkout, target]
    )
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, "checkout-deps", "etc", "buildstream", "config"))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_tar(datafiles, cli):
    project = str(datafiles)
    tar = os.path.join(cli.directory, "source-checkout.tar")
    target = "checkout-deps.bst"

    result = cli.run(project=project, args=["source", "checkout", "--tar", tar, "--deps", "none", target])
    result.assert_success()

    assert os.path.exists(tar)
    with tarfile.open(tar) as tf:
        expected_content = os.path.join(tar, "checkout-deps", "etc", "buildstream", "config")
        tar_members = [f.name for f in tf]
        for member in tar_members:
            assert member in expected_content


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("compression", [("gz"), ("xz"), ("bz2")])
def test_source_checkout_compressed_tar(datafiles, cli, compression):
    project = str(datafiles)
    tarfile_name = "source-checkout.tar" + compression
    tar = os.path.join(cli.directory, tarfile_name)
    target = "checkout-deps.bst"

    result = cli.run(
        project=project,
        args=["source", "checkout", "--tar", tar, "--compression", compression, "--deps", "none", target],
    )
    result.assert_success()
    with tarfile.open(name=tar, mode="r:" + compression) as tar:
        assert os.path.join("checkout-deps", "etc", "buildstream", "config") in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("deps", [("build"), ("none"), ("run"), ("all")])
def test_source_checkout_deps(datafiles, cli, deps):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "checkout-deps.bst"

    result = cli.run(project=project, args=["source", "checkout", "--directory", checkout, "--deps", deps, target])
    result.assert_success()

    # Sources of the target
    if deps == "build":
        assert not os.path.exists(os.path.join(checkout, "checkout-deps"))
    else:
        assert os.path.exists(os.path.join(checkout, "checkout-deps", "etc", "buildstream", "config"))

    # Sources of the target's build dependencies
    if deps in ("build", "all"):
        assert os.path.exists(os.path.join(checkout, "import-dev", "usr", "include", "pony.h"))
    else:
        assert not os.path.exists(os.path.join(checkout, "import-dev"))

    # Sources of the target's runtime dependencies
    if deps in ("run", "all"):
        assert os.path.exists(os.path.join(checkout, "import-bin", "usr", "bin", "hello"))
    else:
        assert not os.path.exists(os.path.join(checkout, "import-bin"))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_except(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "checkout-deps.bst"

    result = cli.run(
        project=project,
        args=["source", "checkout", "--directory", checkout, "--deps", "all", "--except", "import-bin.bst", target],
    )
    result.assert_success()

    # Sources for the target should be present
    assert os.path.exists(os.path.join(checkout, "checkout-deps", "etc", "buildstream", "config"))

    # Sources for import-bin.bst should not be present
    assert not os.path.exists(os.path.join(checkout, "import-bin"))

    # Sources for other dependencies should be present
    assert os.path.exists(os.path.join(checkout, "import-dev", "usr", "include", "pony.h"))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_fetch(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "remote-import-dev.bst"
    target_path = os.path.join(project, "elements", target)

    # Create an element with remote source
    element = generate_remote_import_element(
        os.path.join(project, "files", "dev-files", "usr", "include", "pony.h"), "pony.h"
    )
    _yaml.roundtrip_dump(element, target_path)

    # Testing implicit fetching requires that we do not have the sources
    # cached already
    assert cli.get_element_state(project, target) == "fetch needed"

    args = ["source", "checkout"]
    args += [target, checkout]
    result = cli.run(project=project, args=["source", "checkout", "--directory", checkout, target])

    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "remote-import-dev", "pony.h"))


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_build_scripts(cli, tmpdir, datafiles):
    project_path = str(datafiles)
    element_name = "source-bundle/source-bundle-hello.bst"
    normal_name = "source-bundle-source-bundle-hello"
    checkout = os.path.join(str(tmpdir), "source-checkout")

    args = ["source", "checkout", "--include-build-scripts", "--directory", checkout, element_name]
    result = cli.run(project=project_path, args=args)
    result.assert_success()

    # There sould be a script for each element (just one in this case) and a top level build script
    expected_scripts = ["build.sh", "build-" + normal_name]
    for script in expected_scripts:
        assert script in os.listdir(checkout)


@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_tar_buildscripts(cli, tmpdir, datafiles):
    project_path = str(datafiles)
    element_name = "source-bundle/source-bundle-hello.bst"
    normal_name = "source-bundle-source-bundle-hello"
    tar_file = os.path.join(str(tmpdir), "source-checkout.tar")

    args = ["source", "checkout", "--include-build-scripts", "--tar", tar_file, element_name]
    result = cli.run(project=project_path, args=args)
    result.assert_success()

    expected_scripts = ["build.sh", "build-" + normal_name]

    with tarfile.open(tar_file, "r") as tf:
        for script in expected_scripts:
            assert script in tf.getnames()


# Test that the --directory and --tar options conflict
@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_options_tar_and_dir_conflict(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    tar_file = os.path.join(str(tmpdir), "source-checkout.tar")
    target = "checkout-deps.bst"

    result = cli.run(project=project, args=["source", "checkout", "--directory", checkout, "--tar", tar_file, target])

    assert result.exit_code != 0
    assert "ERROR: options --directory and --tar conflict" in result.stderr


# Test that the --compression option without --tar fails
@pytest.mark.datafiles(DATA_DIR)
def test_source_checkout_compression_without_tar(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "source-checkout")
    target = "checkout-deps.bst"

    result = cli.run(
        project=project, args=["source", "checkout", "--directory", checkout, "--compression", "xz", target]
    )

    assert result.exit_code != 0
    assert "ERROR: --compression specified without --tar" in result.stderr
