import os
import pytest
import re
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
def test_default_logging(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'fetch-test-git.bst'

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Now try to fetch it
    result = cli.run(project=project, args=['fetch', element_name])
    result.assert_success()

    m = re.search("\[\d\d:\d\d:\d\d\]\[\]\[\] SUCCESS Checking sources", result.stderr)
    assert(m is not None)


@pytest.mark.datafiles(DATA_DIR)
def test_custom_logging(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'fetch-test-git.bst'

    custom_log_format = '%{elapsed},%{elapsed-us},%{wallclock},%{key},%{element},%{action},%{message}'
    user_config = {'logging': {'message-format': custom_log_format}}
    user_config_file = str(tmpdir.join('buildstream.conf'))
    _yaml.dump(_yaml.node_sanitize(user_config), filename=user_config_file)

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Now try to fetch it
    result = cli.run(project=project, args=['-c', user_config_file, 'fetch', element_name])
    result.assert_success()

    m = re.search("\d\d:\d\d:\d\d,\d\d:\d\d:\d\d.\d{6},\d\d:\d\d:\d\d,,,SUCCESS,Checking sources", result.stderr)
    assert(m is not None)


@pytest.mark.datafiles(DATA_DIR)
def test_failed_build_listing(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_names = []
    for i in range(3):
        element_name = 'testfail-{}.bst'.format(i)
        element_path = os.path.join('elements', element_name)
        element = {
            'kind': 'script',
            'config': {
                'commands': [
                    'false'
                ]
            }
        }
        _yaml.dump(element, os.path.join(project, element_path))
        element_names.append(element_name)
    result = cli.run(project=project, args=['--on-error=continue', 'build'] + element_names)
    result.assert_main_error(ErrorDomain.STREAM, None)

    failure_heading_pos = re.search(r'^Failure Summary$', result.stderr, re.MULTILINE).start()
    pipeline_heading_pos = re.search(r'^Pipeline Summary$', result.stderr, re.MULTILINE).start()
    failure_summary_range = range(failure_heading_pos, pipeline_heading_pos)
    assert all(m.start() in failure_summary_range and m.end() in failure_summary_range
               for m in re.finditer(r'^\s+testfail-.\.bst.+?\s+Log file', result.stderr, re.MULTILINE))
