import os
import pytest

from buildstream._context import Context
from buildstream._project import Project
from buildstream._exceptions import LoadError, LoadErrorReason
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'pluginloading',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context()
    context.load(config=os.devnull)
    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.casdir = os.path.join(str(tmpdir), 'cas')
    project = Project(basedir, context)

    def dummy_handler(message, is_silenced):
        pass

    context.messenger.set_message_handler(dummy_handler)

    pipeline = Pipeline(context, project, None)
    targets, = pipeline.load([(target,)])
    return targets


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customsource'))
def test_customsource(datafiles, tmpdir):

    basedir = str(datafiles)
    targets = create_pipeline(tmpdir, basedir, 'simple.bst')
    assert targets[0].get_kind() == "autotools"


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customelement'))
def test_customelement(datafiles, tmpdir):

    basedir = str(datafiles)
    targets = create_pipeline(tmpdir, basedir, 'simple.bst')
    assert targets[0].get_kind() == "foo"


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionsource'))
def test_badversionsource(datafiles, tmpdir):
    basedir = str(datafiles)

    with pytest.raises(LoadError) as exc:
        create_pipeline(tmpdir, basedir, 'simple.bst')

    assert exc.value.reason == LoadErrorReason.UNSUPPORTED_PLUGIN


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badversionelement'))
def test_badversionelement(datafiles, tmpdir):
    basedir = str(datafiles)

    with pytest.raises(LoadError) as exc:
        create_pipeline(tmpdir, basedir, 'simple.bst')

    assert exc.value.reason == LoadErrorReason.UNSUPPORTED_PLUGIN
