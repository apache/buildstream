import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement

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
    loader = Loader(basedir, 'elements/onefile.bst', None, None, None, [])

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_missing_file(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/missing.bst', None, None, None, [])

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_reference(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/badreference.bst', None, None, None, [])

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_invalid_yaml(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/badfile.bst', None, None, None, [])

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'onefile'))
def test_fail_fullpath_target(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    fullpath = os.path.join(basedir, 'elements', 'onefile.bst')

    with pytest.raises(LoadError) as exc:
        loader = Loader(basedir, fullpath, None, None, None, [])

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)
