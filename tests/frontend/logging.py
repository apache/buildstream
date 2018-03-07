import os
import pytest
import re
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml

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
