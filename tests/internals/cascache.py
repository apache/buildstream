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

from buildstream._cas.cascache import CASCache
from buildstream._cas import casdprocessmanager
from buildstream._messenger import Messenger


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
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

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
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

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
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

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
        cache = CASCache(str(casd_files_path), casd=True, log_directory=str(casd_parent_logs_path))
        time.sleep(0.5)
        cache.release_resources()

        existing_log_files = sorted(casd_logs_path.iterdir())
        assert len(existing_log_files) == i
        assert existing_log_files[-1].read_text() == "hello\n"

    # Ensure the oldest log files get removed first
    for _ in range(3):
        evicted_file = existing_log_files.pop(0)

        cache = CASCache(str(casd_files_path), casd=True, log_directory=str(casd_parent_logs_path))
        time.sleep(0.5)
        cache.release_resources()

        existing_log_files = sorted(casd_logs_path.iterdir())
        assert len(existing_log_files) == n_max_log_files
        assert evicted_file not in existing_log_files
        assert existing_log_files[-1].read_text() == "hello\n"
