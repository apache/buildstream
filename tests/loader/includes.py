import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'includes',
)

##############################################################
#              Test Basic Include Functionality              #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_basic_include(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/target.bst', None, None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Assert that the stuff from the include got into the element data
    assert(element.config.get('pony') == 'Someone rides their pony')

    thelist = element.config.get('list', None)
    assert(isinstance(thelist, list))
    assert(thelist[0] == 'Element 1')
    assert(thelist[1] == 'Element 2')

@pytest.mark.datafiles(DATA_DIR)
def test_invalid_type_include(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/invalidinclude.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.ILLEGAL_COMPOSITE)

@pytest.mark.datafiles(DATA_DIR)
def test_overwrite_kind_include(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/overwriting.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.ILLEGAL_COMPOSITE)

@pytest.mark.datafiles(DATA_DIR)
def test_missing_include(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/missing.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)
