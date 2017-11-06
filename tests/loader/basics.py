import os
import pytest

from buildstream._exceptions import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement
from . import make_options

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
    loader = Loader(basedir, ['elements/onefile.bst'], make_options(basedir))

    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_missing_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/missing.bst'], make_options(basedir))

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_reference(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/badreference.bst'], make_options(basedir))

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_yaml(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/badfile.bst'], make_options(basedir))

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_fail_fullpath_target(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    fullpath = os.path.join(basedir, 'elements', 'onefile.bst')

    with pytest.raises(LoadError) as exc:
        loader = Loader(basedir, [fullpath], make_options(basedir))

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_key(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/invalidkey.bst'], make_options(basedir))

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)
