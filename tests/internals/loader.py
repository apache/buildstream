import os
import pytest

from buildstream._exceptions import LoadError, LoadErrorReason
from buildstream._context import Context
from buildstream._project import Project
from buildstream._loader import MetaElement


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'loader',
)


def dummy_handler(message, context):
    pass


def make_loader(basedir):
    context = Context()
    context.load(config=os.devnull)
    context.set_message_handler(dummy_handler)
    project = Project(basedir, context)
    return project.loader


##############################################################
#  Basics: Test behavior loading the simplest of projects    #
##############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_one_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    element = loader.load(['elements/onefile.bst'])[0]

    assert isinstance(element, MetaElement)
    assert element.kind == 'pony'


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_missing_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        loader.load(['elements/missing.bst'])

    assert exc.value.reason == LoadErrorReason.MISSING_FILE


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_reference(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        loader.load(['elements/badreference.bst'])

    assert exc.value.reason == LoadErrorReason.INVALID_YAML


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_yaml(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        loader.load(['elements/badfile.bst'])

    assert exc.value.reason == LoadErrorReason.INVALID_YAML


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_fail_fullpath_target(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    fullpath = os.path.join(basedir, 'elements', 'onefile.bst')

    with pytest.raises(LoadError) as exc:
        loader = make_loader(basedir)
        loader.load([fullpath])

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_key(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        loader.load(['elements/invalidkey.bst'])

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_directory_load(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        loader.load(['elements/'])

    assert exc.value.reason == LoadErrorReason.LOADING_DIRECTORY
