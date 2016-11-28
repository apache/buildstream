import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'arches',
)

##############################################################
#                Test Simple Arch Conditionals               #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_simple_conditional_nomatch(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/simple-conditional.bst', None, 'arm')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # Did not provide any arch specific data for 'arm', number remains 5
    assert(number == 5)

@pytest.mark.datafiles(DATA_DIR)
def test_simple_conditional_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/simple-conditional.bst', None, 'x86_64')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # x86_64 arch overrides the number to 6
    assert(number == 6)

@pytest.mark.datafiles(DATA_DIR)
def test_simple_conditional_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/simple-conditional.bst', None, 'x86_32')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # x86_32 arch overrides the number to 7
    assert(number == 7)

##############################################################
#            Test Arch Conditionals inside Variants          #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', None, 'arm')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # The default "pink" variant sets number to 6
    assert(number == 6)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_default_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', None, 'x86_64')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 7)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_default_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', None, 'x86_32')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 8)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_pink_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'pink', 'arm')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # The default "pink" variant sets number to 6
    assert(number == 6)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_pink_pony_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'pink', 'x86_64')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 7)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_pink_pony_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'pink', 'x86_32')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 8)



@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_blue_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'blue', 'arm')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # The "blue" variant sets number to 4
    assert(number == 4)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_blue_pony_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'blue', 'x86_64')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 3)

@pytest.mark.datafiles(DATA_DIR)
def test_variant_arch_blue_pony_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-arch-conditional.bst', 'blue', 'x86_32')

    element = loader.load()
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    assert(number == 2)
