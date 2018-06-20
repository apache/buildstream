import os
import sys
import shutil
import itertools
import pytest
from tests.testutils import cli, generate_junction

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from . import configure_project

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
@pytest.mark.parametrize("element_name", ['junction-dep.bst', 'junction.bst:import-etc.bst'])
def test_unfetched_junction(cli, tmpdir, datafiles, ref_storage, element_name):
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
        _yaml.dump(project_refs, os.path.join(project, 'junction.refs'))

    # Assert the correct error when trying to show the pipeline
    result = cli.run(project=project, silent=True, args=[
        'show', element_name])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_FETCH_NEEDED)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("element_name", ['junction-dep.bst', 'junction.bst:import-etc.bst'])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage, element_name):
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
        'show', element_name])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("element_name", ['junction-dep.bst', 'junction.bst:import-etc.bst'])
def test_fetched_junction(cli, tmpdir, datafiles, element_name):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

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

    result = cli.run(project=project, silent=True, args=[
        'fetch', 'junction.bst'])

    result.assert_success()

    # Assert the correct error when trying to show the pipeline
    result = cli.run(project=project, silent=True, args=[
        'show', '--format', '%{name}-%{state}', element_name])

    results = result.output.strip().splitlines()
    assert 'junction.bst:import-etc.bst-buildable' in results


###############################################################
#                   Testing recursion depth                   #
###############################################################
@pytest.mark.parametrize("dependency_depth", [100, 500, 1200])
def test_exceed_max_recursion_depth(cli, tmpdir, dependency_depth):
    project_name = "recursion-test"
    path = str(tmpdir)
    project_path = os.path.join(path, project_name)

    def setup_test():
        """
        Creates a bst project with dependencydepth + 1 elements, each of which
        depends of the previous element to be created. Each element created
        is of type import and has an empty source file.
        """
        os.mkdir(project_path)

        result = cli.run(project=project_path, silent=True,
                         args=['init', '--project-name', project_name])
        result.assert_success()

        sourcefiles_path = os.path.join(project_path, "files")
        os.mkdir(sourcefiles_path)

        element_path = os.path.join(project_path, "elements")
        for i in range(0, dependency_depth + 1):
            element = {
                'kind': 'import',
                'sources': [{'kind': 'local',
                             'path': 'files/source{}'.format(str(i))}],
                'depends': ['element{}.bst'.format(str(i - 1))]
            }
            if i == 0:
                del element['depends']
            _yaml.dump(element, os.path.join(element_path, "element{}.bst".format(str(i))))

            source = os.path.join(sourcefiles_path, "source{}".format(str(i)))
            open(source, 'x').close()
            assert os.path.exists(source)

    setup_test()
    result = cli.run(project=project_path, silent=True,
                     args=['show', "element{}.bst".format(str(dependency_depth))])

    recursion_limit = sys.getrecursionlimit()
    if dependency_depth <= recursion_limit:
        result.assert_success()
    else:
        #  Assert exception is thown and handled
        assert not result.unhandled_exception
        assert result.exit_code == -1

    shutil.rmtree(project_path)
