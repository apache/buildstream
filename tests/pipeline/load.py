import os
import pytest

from buildstream import Context, Project, Scope
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


def create_pipeline(tmpdir, basedir, target, variant):
    context = Context('x86_64')
    project = Project(basedir)

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')

    return Pipeline(context, project, target, variant)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')


###############################################################
#        Testing Element.dependencies() iteration             #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_all(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst', None)

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.ALL)
    element_list = list(element_list)
    assert(len(element_list) == 7)

    assert(element_list[0].name == "build-build")
    assert(element_list[1].name == "run-build")
    assert(element_list[2].name == "build")
    assert(element_list[3].name == "dep-one")
    assert(element_list[4].name == "run")
    assert(element_list[5].name == "dep-two")
    assert(element_list[6].name == "target")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_run(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst', None)

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.RUN)
    element_list = list(element_list)
    assert(len(element_list) == 4)

    assert(element_list[0].name == "dep-one")
    assert(element_list[1].name == "run")
    assert(element_list[2].name == "dep-two")
    assert(element_list[3].name == "target")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst', None)

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')

    element_list = pipeline.target.dependencies(Scope.BUILD)
    element_list = list(element_list)

    assert(len(element_list) == 3)

    assert(element_list[0].name == "dep-one")
    assert(element_list[1].name == "run")
    assert(element_list[2].name == "dep-two")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build_of_child(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'target.bst', None)

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

    assert(element_list[0].name == "run-build")
    assert(element_list[1].name == "build")
