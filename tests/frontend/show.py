import os
import pytest
import itertools
from tests.testutils import cli

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from . import configure_project, generate_junction

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,format,expected", [
    ('import-bin.bst', '%{name}', 'import-bin.bst'),
    ('import-bin.bst', '%{state}', 'buildable'),
    ('compose-all.bst', '%{state}', 'waiting')
])
def test_show(cli, datafiles, target, format, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', format,
        target])
    result.assert_success()

    if result.output.strip() != expected:
        raise AssertionError("Expected output:\n{}\nInstead received output:\n{}"
                             .format(expected, result.output))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,except_,expected", [
    ('target.bst', 'import-bin.bst', ['import-dev.bst', 'compose-all.bst', 'target.bst']),
    ('target.bst', 'import-dev.bst', ['import-bin.bst', 'compose-all.bst', 'target.bst']),
    ('target.bst', 'compose-all.bst', ['import-bin.bst', 'target.bst']),
    ('compose-all.bst', 'import-bin.bst', ['import-dev.bst', 'compose-all.bst'])
])
def test_show_except(cli, datafiles, target, except_, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'all',
        '--format', '%{name}',
        '--except', except_,
        target])

    result.assert_success()

    results = result.output.strip().splitlines()
    if results != expected:
        raise AssertionError("Expected elements:\n{}\nInstead received elements:\n{}"
                             .format(expected, results))


###############################################################
#                   Testing multiple targets                  #
###############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_parallel_order(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['multiple_targets/order/0.bst',
                'multiple_targets/order/1.bst']

    args = ['show', '-d', 'plan', '-f', '%{name}'] + elements
    result = cli.run(project=project, args=args)

    result.assert_success()

    # Get the planned order
    names = result.output.splitlines()
    names = [name[len('multiple_targets/order/'):] for name in names]

    # Create all possible 'correct' topological orderings
    orderings = itertools.product(
        [('5.bst', '6.bst')],
        itertools.permutations(['4.bst', '7.bst']),
        itertools.permutations(['3.bst', '8.bst']),
        itertools.permutations(['2.bst', '9.bst']),
        itertools.permutations(['0.bst', '1.bst', 'run.bst'])
    )
    orderings = [list(itertools.chain.from_iterable(perm)) for perm in orderings]

    # Ensure that our order is among the correct orderings
    assert names in orderings, "We got: {}".format(", ".join(names))


@pytest.mark.datafiles(DATA_DIR)
def test_target_is_dependency(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    elements = ['multiple_targets/dependency/zebry.bst',
                'multiple_targets/dependency/horsey.bst']

    args = ['show', '-d', 'plan', '-f', '%{name}'] + elements
    result = cli.run(project=project, args=args)

    result.assert_success()

    # Get the planned order
    names = result.output.splitlines()
    names = [name[len('multiple_targets/dependency/'):] for name in names]

    assert names == ['pony.bst', 'horsey.bst', 'zebry.bst']


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_unfetched_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    ref = generate_junction(tmpdir, subproject_path, junction_path, store_ref=(ref_storage == 'inline'))

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # Dump a project.refs if we're using project.refs storage
    #
    if ref_storage == 'project.refs':
        project_refs = {
            'projects': {
                'test': {
                    'junction.bst': [
                        {
                            'ref': ref
                        }
                    ]
                }
            }
        }
        _yaml.dump(project_refs, os.path.join(project, 'project.refs'))

    # Assert the correct error when trying to show the pipeline
    result = cli.run(project=project, silent=True, args=[
        'show', 'junction-dep.bst'])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_FETCH_NEEDED)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # Assert the correct error when trying to show the pipeline
    result = cli.run(project=project, silent=True, args=[
        'show', 'junction-dep.bst'])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)
