import os
import sys
import pytest
import tempfile
from contextlib import ExitStack

from buildstream._sandboxchroot import Mount
from buildstream._platform import Platform
from buildstream import Context, _ostree


@pytest.fixture()
def mount(tmpdir):
    context = Context('x86_64')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context.builddir = os.path.join(str(tmpdir), 'build')
    context._platform = Platform(context)

    return Mount(context._platform)


@pytest.mark.skip(reason="requires root permissions")
def test_bind_mount(mount):
    with ExitStack() as stack:
        src = stack.enter_context(tempfile.TemporaryDirectory())
        target = stack.enter_context(tempfile.TemporaryDirectory())

        with open(os.path.join(src, 'test'), 'a') as test:
            test.write('Test')

        with mount.bind_mount(src, target) as dest:
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


@pytest.mark.skip(reason="requires root permissions")
def test_mount_proc(mount):
    with ExitStack() as stack:
        src = '/proc'
        target = stack.enter_context(tempfile.TemporaryDirectory())

        with mount.mount(src, target, 'proc', ro=True) as dest:
            # Ensure we get the correct path back
            assert dest == target

            # Ensure /proc is actually mounted
            assert os.listdir(src) == os.listdir(target)

        # Ensure /proc is unmounted correctly
        assert os.listdir(target) == []
