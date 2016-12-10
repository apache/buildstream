import os
import pytest
import tempfile

from buildstream import Context
from buildstream._artifactcache import ArtifactCache


@pytest.fixture()
def context(tmpdir):
    context = Context('x86_64')
    context.load()

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')

    return context


@pytest.fixture()
def artifactcache(context):
    return ArtifactCache(context)


def test_empty_contains(context, artifactcache):
    assert(not artifactcache.contains('foo', 'bar', 'a1b2c3'))


@pytest.mark.xfail()
def test_empty_extract(context, artifactcache):
    artifactcache.extract('foo', 'bar', 'a1b2c3')


def test_commit_extract(context, artifactcache):
    os.makedirs(context.deploydir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=context.deploydir) as deploydir:
        # create file as mock build output
        bindir = os.path.join(deploydir, 'bin')
        os.mkdir(bindir)
        with open(os.path.join(bindir, 'baz'), 'w') as f:
            f.write('hello, world')

        # commit build output to artifact cache
        artifactcache.commit('foo', 'bar', 'a1b2c3', deploydir)

    assert(artifactcache.contains('foo', 'bar', 'a1b2c3'))

    # extract artifact and verify the content
    extractdir = artifactcache.extract('foo', 'bar', 'a1b2c3')
    with open(os.path.join(extractdir, 'bin', 'baz'), 'r') as f:
        content = f.read()
        assert(content == 'hello, world')
