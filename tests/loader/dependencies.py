import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement
from . import make_options

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'dependencies',
)


##############################################################
#  Basics: Test behavior loading projects with dependencies  #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_two_files(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/target.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'thefirstdep')


@pytest.mark.datafiles(DATA_DIR)
def test_shared_dependency(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/shareddeptarget.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    # Toplevel is 'pony' with 2 dependencies
    #
    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')
    assert(len(element.dependencies) == 2)

    # The first specified dependency is 'thefirstdep'
    #
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'thefirstdep')
    assert(len(firstdep.dependencies) == 0)

    # The second specified dependency is 'shareddep'
    #
    shareddep = element.dependencies[1]
    assert(isinstance(shareddep, MetaElement))
    assert(shareddep.kind == 'shareddep')
    assert(len(shareddep.dependencies) == 1)

    # The element which shareddep depends on is
    # the same element in memory as firstdep
    #
    shareddepdep = shareddep.dependencies[0]
    assert(isinstance(shareddepdep, MetaElement))

    # Assert they are in fact the same LoadElement
    #
    # Note we must use 'is' to test that both variables
    # refer to the same object in memory, not a regular
    # equality test with '==' which is one of those operator
    # overridable thingies.
    #
    assert(shareddepdep is firstdep)


@pytest.mark.datafiles(DATA_DIR)
def test_dependency_dict(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/target-depdict.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'thefirstdep')


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_declaration(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/invaliddep.bst'], make_options(basedir), None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_circular_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/circulartarget.bst'], make_options(basedir), None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.CIRCULAR_DEPENDENCY)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_type(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/invaliddeptype.bst'], make_options(basedir), None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_build_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/builddep.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.build_dependencies) == 1)
    firstdep = element.build_dependencies[0]
    assert(isinstance(firstdep, MetaElement))

    assert(len(element.dependencies) == 0)


@pytest.mark.datafiles(DATA_DIR)
def test_runtime_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/runtimedep.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))

    assert(len(element.build_dependencies) == 0)


@pytest.mark.datafiles(DATA_DIR)
def test_build_runtime_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/target.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    assert(len(element.build_dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    firstbuilddep = element.build_dependencies[0]
    assert(firstdep == firstbuilddep)


@pytest.mark.datafiles(DATA_DIR)
def test_all_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, ['elements/alldep.bst'], make_options(basedir), None, None)
    element = loader.load()[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    assert(len(element.build_dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    firstbuilddep = element.build_dependencies[0]
    assert(firstdep == firstbuilddep)
