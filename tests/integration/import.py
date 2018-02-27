import os
import pytest

from buildstream import _yaml

from tests.testutils import cli_integration as cli
from tests.testutils.integration import walk_dir


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_import_element(name, path, source, target, source_path):
    element = {
        'kind': 'import',
        'sources': [{
            'kind': 'local',
            'path': source_path
        }],
        'config': {
            'source': source,
            'target': target
        }
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("source,target,path,expected", [
    ('/', '/', 'files/import-source', ['/test.txt', '/subdir',
                                       '/subdir/test.txt']),
    ('/subdir', '/', 'files/import-source', ['/test.txt']),
    ('/', '/', 'files/import-source/subdir', ['/test.txt']),
    ('/', '/output', 'files/import-source', ['/output', '/output/test.txt',
                                             '/output/subdir',
                                             '/output/subdir/test.txt']),
])
def test_import(cli, tmpdir, datafiles, source, target, path, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'import/import.bst'

    create_import_element(element_name, element_path, source, target, path)

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['checkout', element_name, checkout])
    assert res.exit_code == 0

    assert set(walk_dir(checkout)) == set(expected)
