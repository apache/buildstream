import os
import pytest

from buildstream import Context, Project, Scope
from buildstream._pipeline import Pipeline
from buildstream._platform import Platform

from tests.testutils.site import HAVE_ROOT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context([], 'x86_64')
    project = Project(basedir, context)

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context._platform = Platform.get_platform()

    return Pipeline(context, project, target)


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst')

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')


###############################################################
#        Testing Element.dependencies() iteration             #
###############################################################
@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_all(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst')

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.ALL)
    element_list = list(element_list)
    assert(len(element_list) == 7)

    assert(element_list[0].name == "build-build.bst")
    assert(element_list[1].name == "run-build.bst")
    assert(element_list[2].name == "build.bst")
    assert(element_list[3].name == "dep-one.bst")
    assert(element_list[4].name == "run.bst")
    assert(element_list[5].name == "dep-two.bst")
    assert(element_list[6].name == "target.bst")


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_run(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst')

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.RUN)
    element_list = list(element_list)
    assert(len(element_list) == 4)

    assert(element_list[0].name == "dep-one.bst")
    assert(element_list[1].name == "run.bst")
    assert(element_list[2].name == "dep-two.bst")
    assert(element_list[3].name == "target.bst")


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst')

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.BUILD)
    element_list = list(element_list)

    assert(len(element_list) == 3)

    assert(element_list[0].name == "dep-one.bst")
    assert(element_list[1].name == "run.bst")
    assert(element_list[2].name == "dep-two.bst")


@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build_of_child(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst')

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    # First pass, lets check dep-two
    element_list = pipeline.target.dependencies(Scope.BUILD)
    element_list = list(element_list)
    element = element_list[2]

    # Pass two, let's look at these
    element_list = element.dependencies(Scope.BUILD)
    element_list = list(element_list)

    assert(len(element_list) == 2)

    assert(element_list[0].name == "run-build.bst")
    assert(element_list[1].name == "build.bst")


###############################################################
#                   Testing element removal                   #
###############################################################
@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'remove'))
def test_remove_elements(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'build.bst')

    # Remove second-level-2 and check that the correct dependencies
    # are removed.
    element_list = pipeline.target.dependencies(Scope.ALL)
    element_list = pipeline.remove_elements(element_list, ['second-level-1.bst'])

    assert(set(e.name for e in element_list) ==
           set(['build.bst', 'third-level-2.bst', 'fourth-level-2.bst',
                'first-level-1.bst', 'first-level-2.bst']))
