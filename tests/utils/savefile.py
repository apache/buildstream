import os
import pytest

from buildstream.utils import save_file_atomic


def test_save_new_file(tmpdir):
    filename = os.path.join(tmpdir, 'savefile-success.test')
    with save_file_atomic(filename, 'w') as f:
        f.write('foo\n')

    assert os.listdir(tmpdir) == ['savefile-success.test']
    with open(filename) as f:
        assert f.read() == 'foo\n'


def test_save_over_existing_file(tmpdir):
    filename = os.path.join(tmpdir, 'savefile-overwrite.test')

    with open(filename, 'w') as f:
        f.write('existing contents\n')

    with save_file_atomic(filename, 'w') as f:
        f.write('overwritten contents\n')

    assert os.listdir(tmpdir) == ['savefile-overwrite.test']
    with open(filename) as f:
        assert f.read() == 'overwritten contents\n'


def test_exception_new_file(tmpdir):
    filename = os.path.join(tmpdir, 'savefile-exception.test')

    with pytest.raises(RuntimeError):
        with save_file_atomic(filename, 'w') as f:
            f.write('Some junk\n')
            raise RuntimeError("Something goes wrong")

    assert os.listdir(tmpdir) == []


def test_exception_existing_file(tmpdir):
    filename = os.path.join(tmpdir, 'savefile-existing.test')

    with open(filename, 'w') as f:
        f.write('existing contents\n')

    with pytest.raises(RuntimeError):
        with save_file_atomic(filename, 'w') as f:
            f.write('Some junk\n')
            raise RuntimeError("Something goes wrong")

    assert os.listdir(tmpdir) == ['savefile-existing.test']
    with open(filename) as f:
        assert f.read() == 'existing contents\n'


def test_attributes(tmpdir):
    filename = os.path.join(tmpdir, 'savefile-attributes.test')
    with save_file_atomic(filename, 'w') as f:
        assert f.real_filename == filename
        assert f.name != filename
