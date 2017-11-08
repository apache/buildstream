import os
import pytest
from tests.testutils.runcli import cli

from buildstream import Scope
from buildstream._context import Context
from buildstream._project import Project
from buildstream._pipeline import Pipeline
from buildstream._platform import Platform

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context([])
    project = Project(basedir, context)

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context._platform = Platform.get_platform()

    return Pipeline(context, project, [target])


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.get_element_config(basedir, 'simple.bst')

    assert(result['configure-commands'][0] == 'pony')


###############################################################
#        Testing Element.dependencies() iteration             #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_all(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='all')

    assert(len(element_list) == 7)

    assert(element_list[0] == "build-build.bst")
    assert(element_list[1] == "run-build.bst")
    assert(element_list[2] == "build.bst")
    assert(element_list[3] == "dep-one.bst")
    assert(element_list[4] == "run.bst")
    assert(element_list[5] == "dep-two.bst")
    assert(element_list[6] == "target.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_run(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='run')

    assert(len(element_list) == 4)

    assert(element_list[0] == "dep-one.bst")
    assert(element_list[1] == "run.bst")
    assert(element_list[2] == "dep-two.bst")
    assert(element_list[3] == "target.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='build')

    assert(len(element_list) == 3)

    assert(element_list[0] == "dep-one.bst")
    assert(element_list[1] == "run.bst")
    assert(element_list[2] == "dep-two.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build_of_child(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='build')

    # First pass, lets check dep-two
    element = element_list[2]

    # Pass two, let's look at these
    element_list = cli.get_pipeline(basedir, [element], scope='build')

    assert(len(element_list) == 2)

    assert(element_list[0] == "run-build.bst")
    assert(element_list[1] == "build.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_no_recurse(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    # We abuse the 'plan' scope here to ensure that we call
    # element.dependencies() with recurse=False - currently, no `bst
    # show` option does this directly.
    element_list = cli.get_pipeline(basedir, elements, scope='plan')

    assert(len(element_list) == 7)

    assert(element_list[0] == 'build-build.bst')
    assert(element_list[1] in ['build.bst', 'run-build.bst'])
    assert(element_list[2] in ['build.bst', 'run-build.bst'])
    assert(element_list[3] in ['dep-one.bst', 'run.bst', 'dep-two.bst'])
    assert(element_list[4] in ['dep-one.bst', 'run.bst', 'dep-two.bst'])
    assert(element_list[5] in ['dep-one.bst', 'run.bst', 'dep-two.bst'])
    assert(element_list[6] == 'target.bst')


###############################################################
#                   Testing element removal                   #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'remove'))
def test_remove_elements(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['build.bst']
    except_ = ['second-level-1.bst']

    # Except second-level-2 and check that the correct dependencies
    # are removed.
    element_list = cli.get_pipeline(basedir, elements, except_=except_, scope='all')

    assert(element_list[0] == 'fourth-level-2.bst')
    assert(element_list[1] == 'third-level-2.bst')
    assert(element_list[2] == 'first-level-1.bst')
    assert(element_list[3] == 'first-level-2.bst')
    assert(element_list[4] == 'build.bst')
