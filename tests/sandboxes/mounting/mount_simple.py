import os
import tempfile
from contextlib import ExitStack

import pytest

from buildstream.sandbox._mounter import Mounter


@pytest.mark.skipif(not os.geteuid() == 0, reason="requires root permissions")
def test_bind_mount():
    with ExitStack() as stack:
        src = stack.enter_context(tempfile.TemporaryDirectory())
        target = stack.enter_context(tempfile.TemporaryDirectory())

        with open(os.path.join(src, 'test'), 'a') as test:
            test.write('Test')

        with Mounter.bind_mount(target, src) as dest:
            # Ensure we get the correct path back
            assert dest == target

            # Ensure we can access files from src from target
            with open(os.path.join(target, 'test'), 'r') as test:
                assert test.read() == 'Test'

        # Ensure the files from src are gone from target
        with pytest.raises(FileNotFoundError):
            with open(os.path.join(target, 'test'), 'r') as test:
                # Actual contents don't matter
                pass

        # Ensure the files in src are still in src
        with open(os.path.join(src, 'test'), 'r') as test:
            assert test.read() == 'Test'


@pytest.mark.skipif(not os.geteuid() == 0, reason="requires root permissions")
def test_mount_proc():
    with ExitStack() as stack:
        src = '/proc'
        target = stack.enter_context(tempfile.TemporaryDirectory())

        with Mounter.mount(target, src, mount_type='proc', ro=True) as dest:
            # Ensure we get the correct path back
            assert dest == target

            # Ensure /proc is actually mounted
            assert os.listdir(src) == os.listdir(target)

        # Ensure /proc is unmounted correctly
        assert os.listdir(target) == []
