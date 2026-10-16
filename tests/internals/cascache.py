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
import time
from unittest.mock import MagicMock

import pytest

from buildstream._cas import casdprocessmanager
from buildstream._exceptions import CASCacheError
from buildstream._messenger import Messenger
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2
from tests.testutils import casd_cache

#
# A dummy CASD script placeholder which supports the --version argument
#
DUMMY_CASD_SCRIPT_FMT = (
    "#!/usr/bin/env sh\n"
    + "\n"
    + 'if test "$1" = "--version"; then\n'
    + '  echo "buildbox-casd 2.0.0"\n'
    + "  exit 0\n"
    + "fi\n"
    + "{}\n"
    + "exit 0\n"
)


def test_report_when_cascache_dies_before_asked_to(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text(DUMMY_CASD_SCRIPT_FMT.format(""))
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    with casd_cache(tmp_path.joinpath("casd"), messenger):
        time.sleep(1)

    assert messenger.bug.call_count == 1

    message = messenger.bug.call_args[0][0]
    assert "0" in message
    assert "died" in message


def test_report_when_cascache_exits_not_cleanly(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text(DUMMY_CASD_SCRIPT_FMT.format("while :\ndo\nsleep 60\ndone"))
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)
    # FIXME: this is a hack, we should instead have a socket be created nicely
    #        on the fake casd script. This whole test suite probably would
    #        need some cleanup
    monkeypatch.setattr(casdprocessmanager, "_CASD_TIMEOUT", 0.1)

    messenger = MagicMock(spec_set=Messenger)
    with casd_cache(tmp_path.joinpath("casd"), messenger):
        time.sleep(1)

    assert messenger.bug.call_count == 1

    message = messenger.bug.call_args[0][0]
    assert "-15" in message
    assert "cleanly" in message


def test_report_when_cascache_is_forcefully_killed(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text(DUMMY_CASD_SCRIPT_FMT.format("trap 'echo hello' TERM\nwhile :\ndo\nsleep 60\ndone"))
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)
    # FIXME: this is a hack, we should instead have a socket be created nicely
    #        on the fake casd script. This whole test suite probably would
    #        need some cleanup
    monkeypatch.setattr(casdprocessmanager, "_CASD_TIMEOUT", 0.1)

    messenger = MagicMock(spec_set=Messenger)
    with casd_cache(tmp_path.joinpath("casd"), messenger):
        time.sleep(1)

    assert messenger.warn.call_count == 1

    message = messenger.warn.call_args[0][0]
    assert "killed" in message


def test_casd_redirects_stderr_to_file_and_rotate(tmp_path, monkeypatch):
    n_max_log_files = 10

    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text(DUMMY_CASD_SCRIPT_FMT.format("printf '%s\n' hello"))
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    casd_files_path = tmp_path.joinpath("casd")
    casd_parent_logs_path = tmp_path.joinpath("logs")
    casd_logs_path = casd_parent_logs_path.joinpath("_casd")

    # Ensure we don't have any files in the log directory
    assert not casd_logs_path.exists()
    existing_log_files = []

    # Let's create the first `n_max_log_files` log files
    for i in range(1, n_max_log_files + 1):
        with casd_cache(casd_files_path):
            time.sleep(0.5)

        existing_log_files = sorted(casd_logs_path.iterdir())
        assert len(existing_log_files) == i
        assert existing_log_files[-1].read_text() == "hello\n"

    # Ensure the oldest log files get removed first
    for _ in range(3):
        evicted_file = existing_log_files.pop(0)

        with casd_cache(casd_files_path):
            time.sleep(0.5)

        existing_log_files = sorted(casd_logs_path.iterdir())
        assert len(existing_log_files) == n_max_log_files
        assert evicted_file not in existing_log_files
        assert existing_log_files[-1].read_text() == "hello\n"


def add_directory(cas, *, files=None, directories=None, symlinks=None):
    directory = remote_execution_pb2.Directory()
    for name, digest in (files or {}).items():
        filenode = directory.files.add()
        filenode.name = name
        filenode.digest.CopyFrom(digest)
    for name, digest in (directories or {}).items():
        dirnode = directory.directories.add()
        dirnode.name = name
        dirnode.digest.CopyFrom(digest)
    for name, target in (symlinks or {}).items():
        symlinknode = directory.symlinks.add()
        symlinknode.name = name
        symlinknode.target = target
    return cas.add_object(buffer=directory.SerializeToString())


# Test that `checkout()` doesn't follow a symlink in the destination
# directory when checking out a subdirectory.
#
@pytest.mark.parametrize("can_link", [False, True], ids=["copy", "link"])
def test_checkout_existing_directory_symlink(tmp_path, can_link):
    dest = tmp_path.joinpath("dest")
    outside = tmp_path.joinpath("outside")
    dest.mkdir()
    outside.mkdir()
    dest.joinpath("subdir").symlink_to(outside)

    with casd_cache(tmp_path.joinpath("cas")) as cas:
        subdir = add_directory(cas, files={"file": cas.add_object(buffer=b"content")}, symlinks={"link": "target"})
        tree = add_directory(cas, directories={"subdir": subdir})

        with pytest.raises(CASCacheError, match="symlink"):
            cas.checkout(str(dest), tree, can_link=can_link)

    assert os.listdir(outside) == []
    assert dest.joinpath("subdir").is_symlink()


# Test that `checkout()` replaces an existing symlink in the destination
# directory with a regular file instead of writing to the symlink target.
#
@pytest.mark.parametrize("can_link", [False, True], ids=["copy", "link"])
def test_checkout_replace_symlink_with_file(tmp_path, can_link):
    dest = tmp_path.joinpath("dest")
    outside = tmp_path.joinpath("outside")
    dest.mkdir()
    outside.write_bytes(b"original")
    dest.joinpath("file").symlink_to(outside)

    with casd_cache(tmp_path.joinpath("cas")) as cas:
        tree = add_directory(cas, files={"file": cas.add_object(buffer=b"content")})
        cas.checkout(str(dest), tree, can_link=can_link)

    assert outside.read_bytes() == b"original"
    assert not dest.joinpath("file").is_symlink()
    assert dest.joinpath("file").read_bytes() == b"content"


# Test that `checkout()` replaces existing files in the destination
# directory with symlinks.
#
@pytest.mark.parametrize("existing", ["file", "symlink", "dangling-symlink"])
def test_checkout_replace_with_symlink(tmp_path, existing):
    dest = tmp_path.joinpath("dest")
    outside = tmp_path.joinpath("outside")
    dest.mkdir()
    outside.write_bytes(b"original")

    if existing == "file":
        dest.joinpath("link").write_bytes(b"existing")
    elif existing == "symlink":
        dest.joinpath("link").symlink_to(outside)
    else:
        dest.joinpath("link").symlink_to(tmp_path.joinpath("does-not-exist"))

    with casd_cache(tmp_path.joinpath("cas")) as cas:
        tree = add_directory(cas, symlinks={"link": "new-target"})
        cas.checkout(str(dest), tree)

    assert os.readlink(dest.joinpath("link")) == "new-target"
    assert outside.read_bytes() == b"original"
