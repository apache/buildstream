import os
import re
import shutil
import itertools

import pytest
from tests.testutils import cli, create_repo, generate_junction

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain

from . import configure_project

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def create_element(repo, name, path, dependencies, ref=None):
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ],
        'depends': dependencies
    }
    _yaml.dump(element, os.path.join(path, name))


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("strict", [True, False], ids=["strict", "no-strict"])
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
@pytest.mark.parametrize("track_targets,exceptions,tracked", [
    # Test with no exceptions
    (['0.bst'], [], ['0.bst', '2.bst', '3.bst', '4.bst', '5.bst', '6.bst', '7.bst']),
    (['3.bst'], [], ['3.bst', '4.bst', '5.bst', '6.bst']),
    (['2.bst', '3.bst'], [], ['2.bst', '3.bst', '4.bst', '5.bst', '6.bst', '7.bst']),

    # Test excepting '2.bst'
    (['0.bst'], ['2.bst'], ['0.bst', '3.bst', '4.bst', '5.bst', '6.bst']),
    (['3.bst'], ['2.bst'], []),
    (['2.bst', '3.bst'], ['2.bst'], ['3.bst', '4.bst', '5.bst', '6.bst']),

    # Test excepting '2.bst' and '3.bst'
    (['0.bst'], ['2.bst', '3.bst'], ['0.bst']),
    (['3.bst'], ['2.bst', '3.bst'], []),
    (['2.bst', '3.bst'], ['2.bst', '3.bst'], [])
])
def test_build_track(cli, datafiles, tmpdir, ref_storage, strict,
                     track_targets, exceptions, tracked):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')

    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    configure_project(project, {
        'ref-storage': ref_storage
    })
    cli.configure({
        'projects': {
            'test': {
                'strict': strict
            }
        }
    })

    create_elements = {
        '0.bst': [
            '2.bst',
            '3.bst'
        ],
        '2.bst': [
            '3.bst',
            '7.bst'
        ],
        '3.bst': [
            '4.bst',
            '5.bst',
            '6.bst'
        ],
        '4.bst': [],
        '5.bst': [],
        '6.bst': [
            '5.bst'
        ],
        '7.bst': []
    }

    initial_project_refs = {}
    for element, dependencies in create_elements.items():
        # Test the element inconsistency resolution by ensuring that
        # only elements that aren't tracked have refs
        if element in set(tracked):
            # Elements which should not have a ref set
            #
            create_element(repo, element, element_path, dependencies)
        elif ref_storage == 'project.refs':
            # Store a ref in project.refs
            #
            create_element(repo, element, element_path, dependencies)
            initial_project_refs[element] = [{'ref': ref}]
        else:
            # Store a ref in the element itself
            #
            create_element(repo, element, element_path, dependencies, ref=ref)

    # Generate initial project.refs
    if ref_storage == 'project.refs':
        project_refs = {
            'projects': {
                'test': initial_project_refs
            }
        }
        _yaml.dump(project_refs, os.path.join(project, 'project.refs'))

    args = ['build']
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track'), track_targets))
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track-except'), exceptions))
    args += ['0.bst']

    result = cli.run(project=project, silent=True, args=args)
    result.assert_success()

    # Assert that the main target 0.bst is cached
    assert cli.get_element_state(project, '0.bst') == 'cached'

    # Assert that we tracked exactly the elements we expected to
    tracked_elements = result.get_tracked_elements()
    assert set(tracked_elements) == set(tracked)

    # Delete element sources
    source_dir = os.path.join(project, 'cache', 'sources')
    shutil.rmtree(source_dir)

    # Delete artifacts one by one and assert element states
    for target in set(tracked):
        cli.remove_artifact_from_cache(project, target)

        # Assert that it's tracked
        assert cli.get_element_state(project, target) == 'fetch needed'

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == 'project.refs':
        assert os.path.exists(os.path.join(project, 'project.refs'))
    else:
        assert not os.path.exists(os.path.join(project, 'project.refs'))


# This tests a very specific scenario:
#
#  o Local cache is empty
#  o Strict mode is disabled
#  o The build target has only build dependencies
#  o The build is launched with --track-all
#
# In this scenario, we have encountered bugs where BuildStream returns
# successfully after tracking completes without ever pulling, fetching or
# building anything.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [True, False], ids=["strict", "no-strict"])
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_build_track_all(cli, tmpdir, datafiles, strict, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    subproject_element_path = os.path.join(project, 'files', 'sub-project', 'elements')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements')
    dev_files_path = os.path.join(project, 'files', 'dev-files')

    configure_project(project, {
        'ref-storage': ref_storage
    })
    cli.configure({
        'projects': {
            'test': {
                'strict': strict
            }
        }
    })

    # We need a repo for real trackable elements
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    # Create a trackable element to depend on the cross junction element,
    # this one has it's ref resolved already
    create_element(repo, 'sub-target.bst', subproject_element_path, ['import-etc.bst'], ref=ref)

    # Create a trackable element to depend on the cross junction element
    create_element(repo, 'target.bst', element_path, [
        {
            'junction': 'junction.bst',
            'filename': 'sub-target.bst'
        }
    ])

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Now create a compose element at the top level
    element = {
        'kind': 'compose',
        'depends': [
            {
                'filename': 'target.bst',
                'type': 'build'
            }
        ]
    }
    _yaml.dump(element, os.path.join(element_path, 'composed.bst'))

    # Track the junction itself first.
    result = cli.run(project=project, args=['track', 'junction.bst'])
    result.assert_success()

    # Build it with --track-all
    result = cli.run(project=project, silent=True, args=['build', '--track-all', 'composed.bst'])
    result.assert_success()

    # Assert that the main target is cached as a result
    assert cli.get_element_state(project, 'composed.bst') == 'cached'


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("track_targets,exceptions,tracked", [
    # Test with no exceptions
    (['0.bst'], [], ['0.bst', '2.bst', '3.bst', '4.bst', '5.bst', '6.bst', '7.bst']),
    (['3.bst'], [], ['3.bst', '4.bst', '5.bst', '6.bst']),
    (['2.bst', '3.bst'], [], ['2.bst', '3.bst', '4.bst', '5.bst', '6.bst', '7.bst']),

    # Test excepting '2.bst'
    (['0.bst'], ['2.bst'], ['0.bst', '3.bst', '4.bst', '5.bst', '6.bst']),
    (['3.bst'], ['2.bst'], []),
    (['2.bst', '3.bst'], ['2.bst'], ['3.bst', '4.bst', '5.bst', '6.bst']),

    # Test excepting '2.bst' and '3.bst'
    (['0.bst'], ['2.bst', '3.bst'], ['0.bst']),
    (['3.bst'], ['2.bst', '3.bst'], []),
    (['2.bst', '3.bst'], ['2.bst', '3.bst'], [])
])
def test_build_track_update(cli, datafiles, tmpdir, track_targets,
                            exceptions, tracked):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')

    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    create_elements = {
        '0.bst': [
            '2.bst',
            '3.bst'
        ],
        '2.bst': [
            '3.bst',
            '7.bst'
        ],
        '3.bst': [
            '4.bst',
            '5.bst',
            '6.bst'
        ],
        '4.bst': [],
        '5.bst': [],
        '6.bst': [
            '5.bst'
        ],
        '7.bst': []
    }
    for element, dependencies in create_elements.items():
        # We set a ref for all elements, so that we ensure that we
        # only track exactly those elements that we want to track,
        # even if others can be tracked
        create_element(repo, element, element_path, dependencies, ref=ref)
        repo.add_commit()

    args = ['build']
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track'), track_targets))
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track-except'), exceptions))
    args += ['0.bst']

    result = cli.run(project=project, silent=True, args=args)
    tracked_elements = result.get_tracked_elements()

    assert set(tracked_elements) == set(tracked)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("track_targets,exceptions", [
    # Test tracking the main target element, but excepting some of its
    # children
    (['0.bst'], ['6.bst']),

    # Test only tracking a child element
    (['3.bst'], []),
])
def test_build_track_inconsistent(cli, datafiles, tmpdir,
                                  track_targets, exceptions):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')

    repo = create_repo('git', str(tmpdir))
    repo.create(dev_files_path)

    create_elements = {
        '0.bst': [
            '2.bst',
            '3.bst'
        ],
        '2.bst': [
            '3.bst',
            '7.bst'
        ],
        '3.bst': [
            '4.bst',
            '5.bst',
            '6.bst'
        ],
        '4.bst': [],
        '5.bst': [],
        '6.bst': [
            '5.bst'
        ],
        '7.bst': []
    }
    for element, dependencies in create_elements.items():
        # We don't add refs so that all elements *have* to be tracked
        create_element(repo, element, element_path, dependencies)

    args = ['build']
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track'), track_targets))
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track-except'), exceptions))
    args += ['0.bst']

    result = cli.run(project=project, args=args, silent=True)
    result.assert_main_error(ErrorDomain.PIPELINE, "inconsistent-pipeline")


# Assert that if a build element has a dependency in the tracking
# queue it does not start building before tracking finishes.
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("strict", ['--strict', '--no-strict'])
def test_build_track_track_first(cli, datafiles, tmpdir, strict):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')

    repo = create_repo('git', str(tmpdir))
    ref = repo.create(dev_files_path)

    create_elements = {
        '0.bst': [
            '1.bst'
        ],
        '1.bst': [],
        '2.bst': [
            '0.bst'
        ]
    }
    for element, dependencies in create_elements.items():
        # We set a ref so that 0.bst can already be built even if
        # 1.bst has not been tracked yet.
        create_element(repo, element, element_path, dependencies, ref=ref)
        repo.add_commit()

    # Build 1.bst and 2.bst first so we have an artifact for them
    args = [strict, 'build', '2.bst']
    result = cli.run(args=args, project=project, silent=True)
    result.assert_success()

    # Test building 0.bst while tracking 1.bst
    cli.remove_artifact_from_cache(project, '0.bst')

    args = [strict, 'build', '--track', '1.bst', '2.bst']
    result = cli.run(args=args, project=project, silent=True)
    result.assert_success()

    # Assert that 1.bst successfully tracks before 0.bst builds
    track_messages = re.finditer(r'\[track:1.bst\s*]', result.stderr)
    build_0 = re.search(r'\[build:0.bst\s*] START', result.stderr).start()
    assert all(track_message.start() < build_0 for track_message in track_messages)

    # Assert that 2.bst is *only* rebuilt if we are in strict mode
    build_2 = re.search(r'\[build:2.bst\s*] START', result.stderr)
    if strict == '--strict':
        assert build_2 is not None
    else:
        assert build_2 is None
