import os
import time
from unittest.mock import MagicMock

from buildstream._cas.cascache import CASCache
from buildstream._message import MessageType
from buildstream._messenger import Messenger


def test_report_when_cascache_dies_before_asked_to(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/bin/bash\nexit 0")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True)
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.BUG
    assert "0" in message.message
    assert "died" in message.message


def test_report_when_cascache_exist_not_cleanly(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/bin/bash\nwhile :\ndo\nsleep 60\ndone")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True)
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.BUG
    assert "-15" in message.message
    assert "cleanly" in message.message


def test_report_when_cascache_is_forcefully_killed(tmp_path, monkeypatch):
    dummy_buildbox_casd = tmp_path.joinpath("buildbox-casd")
    dummy_buildbox_casd.write_text("#!/bin/bash\ntrap 'echo hello' SIGTERM\nwhile :\ndo\nsleep 60\ndone")
    dummy_buildbox_casd.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)

    messenger = MagicMock(spec_set=Messenger)
    cache = CASCache(str(tmp_path.joinpath("casd")), casd=True)
    time.sleep(1)
    cache.release_resources(messenger)

    assert messenger.message.call_count == 1

    message = messenger.message.call_args[0][0]
    assert message.message_type == MessageType.WARN
    assert "killed" in message.message
