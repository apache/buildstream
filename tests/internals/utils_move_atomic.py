# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import pytest

from buildstream.utils import (
    move_atomic,
    DirectoryExistsError,
    _get_file_mtimestamp,
    _set_file_mtime,
    _parse_timestamp,
)


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
    dst = tmp_path.joinpath("dst")
    move_atomic(src, dst)
    assert dst.joinpath("test").exists()
    _dst = str(dst)
    # set the mtime via stamp
    timestamp1 = "2020-01-08T11:05:50.832123Z"
    _set_file_mtime(_dst, _parse_timestamp(timestamp1))
    assert timestamp1 == _get_file_mtimestamp(_dst)
    # reset the mtime using an offset stamp
    timestamp2 = "2010-02-12T12:05:50.832123+01:00"
    _set_file_mtime(_dst, _parse_timestamp(timestamp2))
    assert _get_file_mtimestamp(_dst) == "2010-02-12T11:05:50.832123Z"
