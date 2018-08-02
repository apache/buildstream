import os
import pytest

from buildstream._exceptions import LoadError, LoadErrorReason
from buildstream._loader import Loader, MetaElement
from . import make_loader

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'basics',
)


##############################################################
#  Basics: Test behavior loading the simplest of projects    #
##############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_one_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    element = loader.load(['elements/onefile.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_missing_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/missing.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_reference(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/badreference.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_yaml(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/badfile.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_fail_fullpath_target(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    fullpath = os.path.join(basedir, 'elements', 'onefile.bst')

    with pytest.raises(LoadError) as exc:
        loader = make_loader(basedir)
        loader.load([fullpath])

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_key(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/invalidkey.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_directory_load(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/'])[0]

    assert (exc.value.reason == LoadErrorReason.LOADING_DIRECTORY)
