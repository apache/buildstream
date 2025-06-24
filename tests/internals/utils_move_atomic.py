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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

from os.path import getmtime

import pytest

from buildstream.utils import (
    move_atomic,
    DirectoryExistsError,
    _set_file_mtime,
)
from buildstream._testing._utils.site import have_subsecond_mtime


@pytest.fixture
def src(tmp_path):
    src = tmp_path.joinpath("src")
    src.mkdir()

    with src.joinpath("test").open("w") as fp:
        fp.write("test")

    return src


def test_move_to_empty_dir(src, tmp_path):
    dst = tmp_path.joinpath("dst")

    move_atomic(src, dst)

    assert dst.joinpath("test").exists()


def test_move_to_empty_dir_create_parents(src, tmp_path):
    dst = tmp_path.joinpath("nested/dst")

    move_atomic(src, dst)
    assert dst.joinpath("test").exists()


def test_move_to_empty_dir_no_create_parents(src, tmp_path):
    dst = tmp_path.joinpath("nested/dst")

    with pytest.raises(FileNotFoundError):
        move_atomic(src, dst, ensure_parents=False)


def test_move_non_existing_dir(tmp_path):
    dst = tmp_path.joinpath("dst")
    src = tmp_path.joinpath("src")

    with pytest.raises(FileNotFoundError):
        move_atomic(src, dst)


def test_move_to_existing_empty_dir(src, tmp_path):
    dst = tmp_path.joinpath("dst")
    dst.mkdir()

    move_atomic(src, dst)
    assert dst.joinpath("test").exists()


def test_move_to_existing_file(src, tmp_path):
    dst = tmp_path.joinpath("dst")

    with dst.open("w") as fp:
        fp.write("error")

    with pytest.raises(NotADirectoryError):
        move_atomic(src, dst)


def test_move_file_to_existing_file(tmp_path):
    dst = tmp_path.joinpath("dst")
    src = tmp_path.joinpath("src")

    with src.open("w") as fp:
        fp.write("src")

    with dst.open("w") as fp:
        fp.write("dst")

    move_atomic(src, dst)
    with dst.open() as fp:
        assert fp.read() == "src"


def test_move_to_existing_non_empty_dir(src, tmp_path):
    dst = tmp_path.joinpath("dst")
    dst.mkdir()

    with dst.joinpath("existing").open("w") as fp:
        fp.write("already there")

    with pytest.raises(DirectoryExistsError):
        move_atomic(src, dst)


def test_move_to_empty_dir_set_mtime(src, tmp_path):
    # Skip this test if we do not have support for subsecond precision mtimes
    #
    if not have_subsecond_mtime(str(tmp_path)):
        pytest.skip("Filesystem does not support subsecond mtime precision: {}".format(str(tmp_path)))

    dst = tmp_path.joinpath("dst")
    move_atomic(src, dst)
    assert dst.joinpath("test").exists()
    _dst = str(dst)
    # set the mtime via stamp
    timestamp1 = 1578481550.832123
    _set_file_mtime(_dst, timestamp1)
    assert timestamp1 == getmtime(_dst)
