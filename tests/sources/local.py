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
import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX
from tests.testutils import filetypegenerator

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "local",
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_missing_path(cli, datafiles):
    project = str(datafiles)

    # Removing the local file causes preflight to fail
    localfile = os.path.join(project, "file.txt")
    os.remove(localfile)

    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_non_regular_file_or_directory(cli, datafiles):
    project = str(datafiles)
    localfile = os.path.join(project, "file.txt")

    for _file_type in filetypegenerator.generate_file_types(localfile):
        result = cli.run(project=project, args=["show", "target.bst"])
        if os.path.isdir(localfile) and not os.path.islink(localfile):
            result.assert_success()
        elif os.path.isfile(localfile) and not os.path.islink(localfile):
            result.assert_success()
        else:
            result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID_KIND)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_invalid_absolute_path(cli, datafiles):
    project = str(datafiles)

    with open(os.path.join(project, "target.bst"), "r", encoding="utf-8") as f:
        old_yaml = f.read()

    new_yaml = old_yaml.replace("file.txt", os.path.join(project, "file.txt"))
    assert old_yaml != new_yaml

    with open(os.path.join(project, "target.bst"), "w", encoding="utf-8") as f:
        f.write(new_yaml)

    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "invalid-relative-path"))
def test_invalid_relative_path(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_stage_file(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "directory"))
def test_stage_directory(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file and directory and other file
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "anotherfile.txt"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "symlink"))
def test_stage_symlink(cli, tmpdir, datafiles):

    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Workaround datafiles bug:
    #
    #   https://github.com/omarkohl/pytest-datafiles/issues/1
    #
    # Create the symlink by hand.
    symlink = os.path.join(project, "files", "symlink-to-file.txt")
    os.symlink("file.txt", symlink)

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file and directory and other file
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "symlink-to-file.txt"))
    assert os.path.islink(os.path.join(checkoutdir, "symlink-to-file.txt"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "file-exists"))
def test_stage_file_exists(cli, datafiles):
    project = str(datafiles)

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.ELEMENT, "stage-sources-fail")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "directory"))
def test_stage_directory_symlink(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    symlink = os.path.join(project, "files", "symlink-to-subdir")
    os.symlink("subdir", symlink)

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected directory and directory symlink
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "anotherfile.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "symlink-to-subdir", "anotherfile.txt"))
    assert os.path.islink(os.path.join(checkoutdir, "symlink-to-subdir"))


@pytest.mark.integration
@pytest.mark.datafiles(os.path.join(DATA_DIR, "deterministic-umask"))
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_deterministic_source_umask(cli, tmpdir, datafiles):
    def create_test_file(*path, mode=0o644, content="content\n"):
        path = os.path.join(*path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            os.fchmod(f.fileno(), mode)

    def create_test_directory(*path, mode=0o644):
        create_test_file(*path, ".keep", content="")
        path = os.path.join(*path)
        os.chmod(path, mode)

    project = str(datafiles)
    element_name = "list.bst"
    element_path = os.path.join(project, "elements", element_name)
    sourcedir = os.path.join(project, "source")

    create_test_file(sourcedir, "a.txt", mode=0o700)
    create_test_file(sourcedir, "b.txt", mode=0o755)
    create_test_file(sourcedir, "c.txt", mode=0o600)
    create_test_file(sourcedir, "d.txt", mode=0o400)
    create_test_file(sourcedir, "e.txt", mode=0o644)
    create_test_file(sourcedir, "f.txt", mode=0o4755)
    create_test_file(sourcedir, "g.txt", mode=0o2755)
    create_test_file(sourcedir, "h.txt", mode=0o1755)
    create_test_directory(sourcedir, "dir-a", mode=0o0700)
    create_test_directory(sourcedir, "dir-c", mode=0o0755)
    create_test_directory(sourcedir, "dir-d", mode=0o4755)
    create_test_directory(sourcedir, "dir-e", mode=0o2755)
    create_test_directory(sourcedir, "dir-f", mode=0o1755)

    source = {"kind": "local", "path": "source"}
    element = {
        "kind": "manual",
        "depends": [{"filename": "base.bst", "type": "build"}],
        "sources": [source],
        "config": {"install-commands": ['ls -l >"%{install-root}/ls-l"']},
    }
    _yaml.roundtrip_dump(element, element_path)
