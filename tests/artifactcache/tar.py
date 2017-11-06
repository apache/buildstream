import os
import tarfile
import tempfile
from contextlib import ExitStack

import pytest

from buildstream._artifactcache.tarcache import Tar
from buildstream.utils import get_host_tool
from buildstream._exceptions import ProgramNotFoundError


# Test that it 'works' - this may be equivalent to test_archive_no_tar()
# on some systems.
def test_archive_default():
    with ExitStack() as stack:
        src = stack.enter_context(tempfile.TemporaryDirectory())
        tar_dir = stack.enter_context(tempfile.TemporaryDirectory())
        scratch = stack.enter_context(tempfile.TemporaryDirectory())
        test_file = stack.enter_context(open(os.path.join(src, 'test'), 'a'))
        test_file.write('Test')

        Tar.archive(os.path.join(tar_dir, 'test.tar'), '.', src)

        with tarfile.open(os.path.join(tar_dir, 'test.tar')) as tar:
            tar.extractall(path=scratch)

        assert os.listdir(scratch) == os.listdir(src)


def test_archive_no_tar():
    # Modify the path to exclude 'tar'
    old_path = os.environ.get('PATH')
    os.environ['PATH'] = ''

    # Ensure we can't find 'tar' or 'gtar'
    try:
        for tar in ['gtar', 'tar']:
            with pytest.raises(ProgramNotFoundError):
                get_host_tool(tar)

    # Run the same test as before, this time 'tar' should not be available
        test_archive_default()

    # Reset the environment
    finally:
        os.environ['PATH'] = old_path


# Same thing as test_archive_default()
def test_extract_default():
    with ExitStack() as stack:
        src = stack.enter_context(tempfile.TemporaryDirectory())
        tar_dir = stack.enter_context(tempfile.TemporaryDirectory())
        scratch = stack.enter_context(tempfile.TemporaryDirectory())
        test_file = stack.enter_context(open(os.path.join(src, 'test'), 'a'))
        test_file.write('Test')

        with tarfile.open(os.path.join(tar_dir, 'test.tar'), 'a:') as tar:
            tar.add(src, 'contents')

        Tar.extract(os.path.join(tar_dir, 'test.tar'), scratch)

        assert os.listdir(os.path.join(scratch, 'contents')) == os.listdir(src)


def test_extract_no_tar():
    # Modify the path to exclude 'tar'
    old_path = os.environ.get('PATH')
    os.environ['PATH'] = ''

    # Ensure we can't find 'tar' or 'gtar'
    for tar in ['gtar', 'tar']:
        with pytest.raises(ProgramNotFoundError):
            get_host_tool(tar)

    # Run the same test as before, this time 'tar' should not be available
    try:
        test_extract_default()

    # Reset the environment
    finally:
        os.environ['PATH'] = old_path
