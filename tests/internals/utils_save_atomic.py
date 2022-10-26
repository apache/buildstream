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
import os
import pytest

from buildstream.utils import save_file_atomic


def test_save_new_file(tmpdir):
    filename = os.path.join(str(tmpdir), "savefile-success.test")
    with save_file_atomic(filename, "w") as f:
        f.write("foo\n")

    assert os.listdir(str(tmpdir)) == ["savefile-success.test"]
    with open(filename, encoding="utf-8") as f:
        assert f.read() == "foo\n"


def test_save_over_existing_file(tmpdir):
    filename = os.path.join(str(tmpdir), "savefile-overwrite.test")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("existing contents\n")

    with save_file_atomic(filename, "w") as f:
        f.write("overwritten contents\n")

    assert os.listdir(str(tmpdir)) == ["savefile-overwrite.test"]
    with open(filename, encoding="utf-8") as f:
        assert f.read() == "overwritten contents\n"


def test_exception_new_file(tmpdir):
    filename = os.path.join(str(tmpdir), "savefile-exception.test")

    with pytest.raises(RuntimeError):
        with save_file_atomic(filename, "w") as f:
            f.write("Some junk\n")
            raise RuntimeError("Something goes wrong")

    assert os.listdir(str(tmpdir)) == []


def test_exception_existing_file(tmpdir):
    filename = os.path.join(str(tmpdir), "savefile-existing.test")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("existing contents\n")

    with pytest.raises(RuntimeError):
        with save_file_atomic(filename, "w") as f:
            f.write("Some junk\n")
            raise RuntimeError("Something goes wrong")

    assert os.listdir(str(tmpdir)) == ["savefile-existing.test"]
    with open(filename, encoding="utf-8") as f:
        assert f.read() == "existing contents\n"


def test_attributes(tmpdir):
    filename = os.path.join(str(tmpdir), "savefile-attributes.test")
    with save_file_atomic(filename, "w") as f:
        assert f.real_filename == filename
        assert f.name != filename
