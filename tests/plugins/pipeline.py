import os
import pytest

from buildstream import Context, Project, Scope, PluginError
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'pipeline',
)


def create_pipeline(tmpdir, basedir, target, variant):
    context = Context('x86_64')
    project = Project(basedir, 'x86_64')

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')

    return Pipeline(context, project, target, variant)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customsource'))
def test_customsource(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)
    assert(pipeline.target.get_kind() == "autotools")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customelement'))
def test_customelement(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)
    assert(pipeline.target.get_kind() == "foo")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionsource'))
def test_badversionsource(datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    with pytest.raises(PluginError) as exc:
        pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionelement'))
def test_badversionelement(datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    with pytest.raises(PluginError) as exc:
        pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)
