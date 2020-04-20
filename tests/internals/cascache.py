import os
import time
from unittest.mock import MagicMock

from buildstream._cas.cascache import CASCache
from buildstream._message import MessageType
from buildstream._messenger import Messenger


def test_report_when_cascache_dies_before_asked_to(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/usr/bin/env sh\nexit 0")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.BUG
    assert "0" in message.message
    assert "died" in message.message


def test_report_when_cascache_exits_not_cleanly(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/usr/bin/env sh\nwhile :\ndo\nsleep 60\ndone")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.BUG
    assert "-15" in message.message
    assert "cleanly" in message.message


def test_report_when_cascache_is_forcefully_killed(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/usr/bin/env sh\ntrap 'echo hello' TERM\nwhile :\ndo\nsleep 60\ndone")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True, log_directory=str(tmp_path.joinpath("logs")))
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.WARN
    assert "killed" in message.message


def test_casd_redirects_stderr_to_file_and_rotate(tmp_path, monkeypatch):
    n_max_log_files = 10

    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/usr/bin/env sh\nprintf '%s\n' hello")
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
