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
    loader = make_loader(basedir, ['elements/onefile.bst'])

    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_missing_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir, ['elements/missing.bst'])

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_reference(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir, ['elements/badreference.bst'])

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_yaml(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir, ['elements/badfile.bst'])

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_fail_fullpath_target(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    fullpath = os.path.join(basedir, 'elements', 'onefile.bst')

    with pytest.raises(LoadError) as exc:
        loader = make_loader(basedir, [fullpath])

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_key(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir, ['elements/invalidkey.bst'])

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)
