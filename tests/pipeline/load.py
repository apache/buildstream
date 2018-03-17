import os
import pytest
from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils.runcli import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.get_element_config(basedir, 'simple.bst')

    assert(result['configure-commands'][0] == 'pony')


###############################################################
#        Testing Element.dependencies() iteration             #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_all(cli, datafiles):
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
def test_iterate_scope_run(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='run')

    assert(len(element_list) == 4)

    assert(element_list[0] == "dep-one.bst")
    assert(element_list[1] == "run.bst")
    assert(element_list[2] == "dep-two.bst")
    assert(element_list[3] == "target.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['target.bst']

    element_list = cli.get_pipeline(basedir, elements, scope='build')

    assert(len(element_list) == 3)

    assert(element_list[0] == "dep-one.bst")
    assert(element_list[1] == "run.bst")
    assert(element_list[2] == "dep-two.bst")


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'iterate'))
def test_iterate_scope_build_of_child(cli, datafiles):
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
def test_iterate_no_recurse(cli, datafiles):
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


# This test checks various constructions of a pipeline
# with one or more targets and 0 or more exception elements,
# each data set provides the targets, exceptions and expected
# result list.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'exceptions'))
@pytest.mark.parametrize("elements,exceptions,results", [

    # Test without exceptions, lets just see the whole list here
    (['build.bst'], None, [
        'fourth-level-1.bst',
        'third-level-1.bst',
        'fourth-level-2.bst',
        'third-level-2.bst',
        'fourth-level-3.bst',
        'third-level-3.bst',
        'second-level-1.bst',
        'first-level-1.bst',
        'first-level-2.bst',
        'build.bst',
    ]),

    # Test one target and excepting a part of the pipeline, this
    # removes forth-level-1 and third-level-1
    (['build.bst'], ['third-level-1.bst'], [
        'fourth-level-2.bst',
        'third-level-2.bst',
        'fourth-level-3.bst',
        'third-level-3.bst',
        'second-level-1.bst',
        'first-level-1.bst',
        'first-level-2.bst',
        'build.bst',
    ]),

    # Test one target and excepting a part of the pipeline, check that
    # excepted dependencies remain in the pipeline if depended on from
    # outside of the except element
    (['build.bst'], ['second-level-1.bst'], [
        'fourth-level-2.bst',
        'third-level-2.bst',  # first-level-2 depends on this, so not excepted
        'first-level-1.bst',
        'first-level-2.bst',
        'build.bst',
    ]),

    # The same as the above test, but excluding the toplevel build.bst,
    # instead only select the two toplevel dependencies as targets
    (['first-level-1.bst', 'first-level-2.bst'], ['second-level-1.bst'], [
        'fourth-level-2.bst',
        'third-level-2.bst',  # first-level-2 depends on this, so not excepted
        'first-level-1.bst',
        'first-level-2.bst',
    ]),

    # Test one target and excepting an element outisde the pipeline
    (['build.bst'], ['unrelated-1.bst'], [
        'fourth-level-2.bst',
        'third-level-2.bst',  # first-level-2 depends on this, so not excepted
        'first-level-1.bst',
        'first-level-2.bst',
        'build.bst',
    ]),

    # Test one target and excepting two elements
    (['build.bst'], ['unrelated-1.bst', 'unrelated-2.bst'], [
        'first-level-1.bst',
        'build.bst',
    ]),
])
def test_except_elements(cli, datafiles, elements, exceptions, results):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    # Except second-level-2 and check that the correct dependencies
    # are removed.
    element_list = cli.get_pipeline(basedir, elements, except_=exceptions, scope='all')
    assert element_list == results


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'noloadref'))
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_unsupported_load_ref(cli, datafiles, ref_storage):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    # Generate project with access to the noloadref plugin and project.refs enabled
    #
    config = {
        'name': 'test',
        'ref-storage': ref_storage,
        'plugins': [
            {
                'origin': 'local',
                'path': 'plugins',
                'sources': {
                    'noloadref': 0
                }
            }
        ]
    }
    _yaml.dump(config, os.path.join(basedir, 'project.conf'))

    result = cli.run(project=basedir, silent=True, args=['show', 'noloadref.bst'])

    # There is no error if project.refs is not in use, otherwise we
    # assert our graceful failure
    if ref_storage == 'inline':
        result.assert_success()
    else:
        result.assert_main_error(ErrorDomain.SOURCE, 'unsupported-load-ref')
