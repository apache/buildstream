import os
import pytest
import tempfile

from buildstream import Context, Project
from buildstream._artifactcache import ArtifactCache, ArtifactError
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'basics',
)


@pytest.fixture()
def pipeline(tmpdir):
    context = Context('x86_64')
    project = Project(DATA_DIR, 'x86_64')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context.builddir = os.path.join(str(tmpdir), 'build')

    return Pipeline(context, project, "simple.bst", None)


def test_empty_contains(pipeline):
    assert(not pipeline.artifacts.contains(pipeline.target))


# Test that we get an ArtifactError when trying to extract a nonexistent artifact
def test_empty_extract(pipeline):
    with pytest.raises(ArtifactError) as exc:
        pipeline.artifacts.extract(pipeline.target)


def test_commit_extract(pipeline):
    os.makedirs(pipeline.context.builddir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=pipeline.context.builddir) as builddir:
        # create file as mock build output
        bindir = os.path.join(builddir, 'bin')
        os.mkdir(bindir)
        with open(os.path.join(bindir, 'baz'), 'w') as f:
            f.write('hello, world')

        # commit build output to artifact cache
        pipeline.artifacts.commit(pipeline.target, builddir)

    assert(pipeline.artifacts.contains(pipeline.target))

    # extract artifact and verify the content
    extractdir = pipeline.artifacts.extract(pipeline.target)
    with open(os.path.join(extractdir, 'bin', 'baz'), 'r') as f:
        content = f.read()
        assert(content == 'hello, world')
