import os
import pytest

from buildstream._exceptions import LoadError, LoadErrorReason
from buildstream._loader import Loader, MetaElement
from tests.testutils import cli
from . import make_loader

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
    loader = make_loader(basedir)
    element = loader.load(['elements/target.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'manual')


@pytest.mark.datafiles(DATA_DIR)
def test_shared_dependency(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)
    element = loader.load(['elements/shareddeptarget.bst'])[0]

    # Toplevel is 'pony' with 2 dependencies
    #
    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')
    assert(len(element.dependencies) == 2)

    # The first specified dependency is 'thefirstdep'
    #
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'manual')
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
    loader = make_loader(basedir)
    element = loader.load(['elements/target-depdict.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    assert(firstdep.kind == 'manual')


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_declaration(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/invaliddep.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_circular_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/circulartarget.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.CIRCULAR_DEPENDENCY)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_dependency_type(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/invaliddeptype.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_strict_dependency(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/invalidstrict.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_non_strict_dependency(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)

    with pytest.raises(LoadError) as exc:
        element = loader.load(['elements/invalidnonstrict.bst'])[0]

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_build_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)
    element = loader.load(['elements/builddep.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.build_dependencies) == 1)
    firstdep = element.build_dependencies[0]
    assert(isinstance(firstdep, MetaElement))

    assert(len(element.dependencies) == 0)


@pytest.mark.datafiles(DATA_DIR)
def test_runtime_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)
    element = loader.load(['elements/runtimedep.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))

    assert(len(element.build_dependencies) == 0)


@pytest.mark.datafiles(DATA_DIR)
def test_build_runtime_dependency(datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = make_loader(basedir)
    element = loader.load(['elements/target.bst'])[0]

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
    loader = make_loader(basedir)
    element = loader.load(['elements/alldep.bst'])[0]

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    assert(len(element.dependencies) == 1)
    assert(len(element.build_dependencies) == 1)
    firstdep = element.dependencies[0]
    assert(isinstance(firstdep, MetaElement))
    firstbuilddep = element.build_dependencies[0]
    assert(firstdep == firstbuilddep)


@pytest.mark.datafiles(DATA_DIR)
def test_list_build_dependency(cli, datafiles):
    project = str(datafiles)

    # Check that the pipeline includes the build dependency
    deps = cli.get_pipeline(project, ['elements/builddep-list.bst'], scope="build")
    assert "elements/firstdep.bst" in deps


@pytest.mark.datafiles(DATA_DIR)
def test_list_runtime_dependency(cli, datafiles):
    project = str(datafiles)

    # Check that the pipeline includes the runtime dependency
    deps = cli.get_pipeline(project, ['elements/runtimedep-list.bst'], scope="run")
    assert "elements/firstdep.bst" in deps


@pytest.mark.datafiles(DATA_DIR)
def test_list_dependencies_combined(cli, datafiles):
    project = str(datafiles)

    # Check that runtime deps get combined
    rundeps = cli.get_pipeline(project, ['elements/list-combine.bst'], scope="run")
    assert "elements/firstdep.bst" not in rundeps
    assert "elements/seconddep.bst" in rundeps
    assert "elements/thirddep.bst" in rundeps

    # Check that build deps get combined
    builddeps = cli.get_pipeline(project, ['elements/list-combine.bst'], scope="build")
    assert "elements/firstdep.bst" in builddeps
    assert "elements/seconddep.bst" not in builddeps
    assert "elements/thirddep.bst" in builddeps


@pytest.mark.datafiles(DATA_DIR)
def test_list_overlap(cli, datafiles):
    project = str(datafiles)

    # Check that dependencies get merged
    rundeps = cli.get_pipeline(project, ['elements/list-overlap.bst'], scope="run")
    assert "elements/firstdep.bst" in rundeps
    builddeps = cli.get_pipeline(project, ['elements/list-overlap.bst'], scope="build")
    assert "elements/firstdep.bst" in builddeps
