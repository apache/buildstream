import os
import re
import shutil
import itertools

import pytest
from tests.testutils import cli, create_repo

from buildstream import _yaml
from buildstream._exceptions import LoadError


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


@pytest.mark.parametrize("save", [([True]), ([False])])
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("exceptions,excepted", [
    # Test with no exceptions
    ([], []),

    # Test excepting '2.bst'
    (['2.bst'], ['2.bst', '7.bst']),

    # Test excepting '2.bst' and '3.bst'
    (['2.bst', '3.bst'], [
        '2.bst', '3.bst', '4.bst',
        '5.bst', '6.bst', '7.bst'
    ])
])
@pytest.mark.parametrize("track_targets,tracked", [
    # Test tracking the main target element
    (['0.bst'], [
        '0.bst', '2.bst', '3.bst',
        '4.bst', '5.bst', '6.bst', '7.bst'
    ]),

    # Test tracking a child element
    (['3.bst'], [
        '3.bst', '4.bst', '5.bst',
        '6.bst'
    ]),

    # Test tracking multiple children
    (['2.bst', '3.bst'], [
        '2.bst', '3.bst', '4.bst',
        '5.bst', '6.bst', '7.bst'
    ])
])
def test_build_track(cli, datafiles, tmpdir, track_targets,
                     exceptions, tracked, excepted, save):
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
        # Test the element inconsistency resolution by ensuring that
        # only elements that aren't tracked have refs
        if element in set(tracked) - set(excepted):
            create_element(repo, element, element_path, dependencies)
        else:
            create_element(repo, element, element_path, dependencies, ref=ref)

    args = ['build']
    if save:
        args += ['--track-save']
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track'), track_targets))
    args += itertools.chain.from_iterable(zip(itertools.repeat('--track-except'), exceptions))
    args += ['0.bst']

    result = cli.run(project=project, silent=True, args=args)
    tracked_elements = result.get_tracked_elements()

    assert set(tracked_elements) == set(tracked) - set(excepted)

    for target in set(tracked) - set(excepted):
        cli.remove_artifact_from_cache(project, target)

        # Delete element sources
        source_dir = os.path.join(project, 'cache', 'sources')
        shutil.rmtree(source_dir)

        if not save:
            assert cli.get_element_state(project, target) == 'no reference'
        else:
            assert cli.get_element_state(project, target) == 'fetch needed'


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("exceptions,excepted", [
    # Test with no exceptions
    ([], []),

    # Test excepting '2.bst'
    (['2.bst'], ['2.bst', '7.bst']),

    # Test excepting '2.bst' and '3.bst'
    (['2.bst', '3.bst'], [
        '2.bst', '3.bst', '4.bst',
        '5.bst', '6.bst', '7.bst'
    ])
])
@pytest.mark.parametrize("track_targets,tracked", [
    # Test tracking the main target element
    (['0.bst'], [
        '0.bst', '2.bst', '3.bst',
        '4.bst', '5.bst', '6.bst', '7.bst'
    ]),

    # Test tracking a child element
    (['3.bst'], [
        '3.bst', '4.bst', '5.bst',
        '6.bst'
    ]),

    # Test tracking multiple children
    (['2.bst', '3.bst'], [
        '2.bst', '3.bst', '4.bst',
        '5.bst', '6.bst', '7.bst'
    ])
])
def test_build_track_update(cli, datafiles, tmpdir, track_targets,
                            exceptions, tracked, excepted):
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

    assert set(tracked_elements) == set(tracked) - set(excepted)


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

    result = cli.run(args=args, silent=True)

    assert result.exit_code != 0
    assert isinstance(result.exception, LoadError)


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
    assert result.exit_code == 0

    # Test building 0.bst while tracking 1.bst
    cli.remove_artifact_from_cache(project, '0.bst')

    args = [strict, 'build', '--track', '1.bst', '2.bst']
    result = cli.run(args=args, project=project, silent=True)
    assert result.exit_code == 0

    # Assert that 1.bst successfully tracks before 0.bst builds
    track_messages = re.finditer(r'\[track:1.bst\s*]', result.output)
    build_0 = re.search(r'\[build:0.bst\s*] START', result.output).start()
    assert all(track_message.start() < build_0 for track_message in track_messages)

    # Assert that 2.bst is *only* rebuilt if we are in strict mode
    build_2 = re.search(r'\[build:2.bst\s*] START', result.output)
    if strict == '--strict':
        assert build_2 is not None
    else:
        assert build_2 is None
