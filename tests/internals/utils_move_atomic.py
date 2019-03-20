# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import pytest

from buildstream.utils import move_atomic, DirectoryExistsError


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
