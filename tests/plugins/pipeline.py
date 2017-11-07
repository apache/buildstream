import os
import pytest

from buildstream import Context, Project, Scope, PluginError
from buildstream._pipeline import Pipeline
from buildstream._platform import Platform

from tests.testutils.site import HAVE_ROOT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'pipeline',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context([], 'x86_64')
    project = Project(basedir, context)

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context._platform = Platform.get_platform()

    return Pipeline(context, project, [target], [])


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customsource'))
def test_customsource(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst')
    assert(pipeline.targets[0].get_kind() == "autotools")


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customelement'))
def test_customelement(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst')
    assert(pipeline.targets[0].get_kind() == "foo")


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionsource'))
def test_badversionsource(datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    with pytest.raises(PluginError) as exc:
        pipeline = create_pipeline(tmpdir, basedir, 'simple.bst')


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionelement'))
def test_badversionelement(datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    with pytest.raises(PluginError) as exc:
        pipeline = create_pipeline(tmpdir, basedir, 'simple.bst')
