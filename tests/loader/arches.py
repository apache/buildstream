import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement
from . import make_options

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
    loader = Loader(
        basedir, ['elements/simple-conditional.bst'], make_options(basedir), 'arm', None)

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # Did not provide any arch specific data for 'arm', number remains 5
    assert(number == 5)


@pytest.mark.datafiles(DATA_DIR)
def test_simple_conditional_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, ['elements/simple-conditional.bst'], make_options(basedir), 'x86_64', None)

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # x86_64 arch overrides the number to 6
    assert(number == 6)


@pytest.mark.datafiles(DATA_DIR)
def test_simple_conditional_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, ['elements/simple-conditional.bst'], make_options(basedir), 'x86_32', None)

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # x86_32 arch overrides the number to 7
    assert(number == 7)


##############################################################
#            Test Arch and Host-Arch Conditionals            #
##############################################################


@pytest.mark.datafiles(DATA_DIR)
def test_host_arch_conditional_armv8(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, ['elements/host-arch-conditional.bst'], make_options(basedir), 'armv8', None)

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # armv8 host-arch overrides the number to 88
    assert(number == 88)


@pytest.mark.datafiles(DATA_DIR)
def test_host_arch_conditional_ignores_target_arch(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, ['elements/host-arch-conditional.bst'], make_options(basedir), 'armv8', 'x86_32')

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # The setting a target-arch has no effect on host-arches: the number is
    # still 88
    assert(number == 88)


@pytest.mark.datafiles(DATA_DIR)
def test_host_arch_conditional_overridden(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, ['elements/host-arch-conditional.bst'], make_options(basedir), 'armv8', 'x86_64')

    element = loader.load()[0]
    assert(isinstance(element, MetaElement))
    number = element.config.get('number')

    # The 'arches' conditional follows the target architecture, and overrides
    # anything specified in 'host-arches'.
    assert(number == 6)
