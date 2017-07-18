import os
import pytest
import tempfile

from buildstream import Context, Project, _yaml
from buildstream.exceptions import _ArtifactError
from buildstream.element import _KeyStrength
from buildstream._artifactcache import ArtifactCache
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
    with pytest.raises(_ArtifactError) as exc:
        pipeline.artifacts.extract(pipeline.target)


def build_commit(pipeline):
    os.makedirs(pipeline.context.builddir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=pipeline.context.builddir) as builddir:
        filesdir = os.path.join(builddir, 'files')
        metadir = os.path.join(builddir, 'meta')
        os.mkdir(filesdir)
        os.mkdir(metadir)

        # create file as mock build output
        bindir = os.path.join(filesdir, 'bin')
        os.mkdir(bindir)
        with open(os.path.join(bindir, 'baz'), 'w') as f:
            f.write('hello, world')

        meta = {
            'keys': {
                'strong': pipeline.target._get_cache_key(_KeyStrength.STRONG),
                'weak': pipeline.target._get_cache_key(_KeyStrength.WEAK),
            }
        }
        _yaml.dump(_yaml.node_sanitize(meta), os.path.join(metadir, 'artifact.yaml'))

        # commit build output to artifact cache
        pipeline.artifacts.commit(pipeline.target, builddir)
        pipeline.target._cached(recalculate=True)


def test_commit_extract(pipeline):
    build_commit(pipeline)
    assert(pipeline.artifacts.contains(pipeline.target))

    # extract artifact and verify the content
    extractdir = pipeline.artifacts.extract(pipeline.target)
    filesdir = os.path.join(extractdir, 'files')
    with open(os.path.join(filesdir, 'bin', 'baz'), 'r') as f:
        content = f.read()
        assert(content == 'hello, world')


def test_push_pull(pipeline, tmpdir):

    pipeline.context.artifact_pull = os.path.join(str(tmpdir), 'share')
    pipeline.context.artifact_push = os.path.join(str(tmpdir), 'share')

    build_commit(pipeline)
    assert(pipeline.artifacts.contains(pipeline.target))

    pipeline.artifacts.push(pipeline.target)

    pipeline.artifacts.remove(pipeline.target)
    assert(not pipeline.artifacts.contains(pipeline.target))

    pipeline.artifacts.pull(pipeline.target)
    assert(pipeline.artifacts.contains(pipeline.target))
