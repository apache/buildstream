import os
import pytest

from buildstream import _yaml, utils
from tests.testutils import create_repo, ALL_REPO_KINDS
from tests.testutils import cli_integration as cli


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_test_file(*path, mode=0o644, content='content\n'):
    path = os.path.join(*path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
        os.fchmod(f.fileno(), mode)


def create_test_directory(*path, mode=0o644):
    create_test_file(*path, '.keep', content='')
    path = os.path.join(*path)
    os.chmod(path, mode)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS] + ['local'])
def test_deterministic_source_umask(cli, tmpdir, datafiles, kind, integration_cache):
    project = str(datafiles)
    element_name = 'list'
    element_path = os.path.join(project, 'elements', element_name)
    repodir = os.path.join(str(tmpdir), 'repo')
    sourcedir = os.path.join(project, 'source')

    create_test_file(sourcedir, 'a.txt', mode=0o700)
    create_test_file(sourcedir, 'b.txt', mode=0o755)
    create_test_file(sourcedir, 'c.txt', mode=0o600)
    create_test_file(sourcedir, 'd.txt', mode=0o400)
    create_test_file(sourcedir, 'e.txt', mode=0o644)
    create_test_file(sourcedir, 'f.txt', mode=0o4755)
    create_test_file(sourcedir, 'g.txt', mode=0o2755)
    create_test_file(sourcedir, 'h.txt', mode=0o1755)
    create_test_directory(sourcedir, 'dir-a', mode=0o0700)
    create_test_directory(sourcedir, 'dir-c', mode=0o0755)
    create_test_directory(sourcedir, 'dir-d', mode=0o4755)
    create_test_directory(sourcedir, 'dir-e', mode=0o2755)
    create_test_directory(sourcedir, 'dir-f', mode=0o1755)

    if kind == 'local':
        source = {'kind': 'local',
                  'path': 'source'}
    else:
        repo = create_repo(kind, repodir)
        ref = repo.create(sourcedir)
        source = repo.source_config(ref=ref)
    element = {
        'kind': 'manual',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build'
            }
        ],
        'sources': [
            source
        ],
        'config': {
            'install-commands': [
                'ls -l >"%{install-root}/ls-l"'
            ]
        }
    }
    _yaml.dump(element, element_path)

    def get_value_for_umask(umask):
        checkoutdir = os.path.join(str(tmpdir), 'checkout-{}'.format(umask))

        old_umask = os.umask(umask)

        try:
            result = cli.run(project=project, args=['build', element_name])
            result.assert_success()

            result = cli.run(project=project, args=['checkout', element_name, checkoutdir])
            result.assert_success()

            with open(os.path.join(checkoutdir, 'ls-l'), 'r') as f:
                return f.read()
        finally:
            os.umask(old_umask)
            cache_dir = os.path.join(integration_cache, 'artifacts')
            cli.remove_artifact_from_cache(project, element_name,
                                           cache_dir=cache_dir)

    assert get_value_for_umask(0o022) == get_value_for_umask(0o077)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_deterministic_source_local(cli, tmpdir, datafiles, integration_cache):
    """Only user rights should be considered for local source.
    """
    project = str(datafiles)
    element_name = 'test'
    element_path = os.path.join(project, 'elements', element_name)
    sourcedir = os.path.join(project, 'source')

    element = {
        'kind': 'manual',
        'depends': [
            {
                'filename': 'base.bst',
                'type': 'build'
            }
        ],
        'sources': [
            {
                'kind': 'local',
                'path': 'source'
            }
        ],
        'config': {
            'install-commands': [
                'ls -l >"%{install-root}/ls-l"'
            ]
        }
    }
    _yaml.dump(element, element_path)

    def get_value_for_mask(mask):
        checkoutdir = os.path.join(str(tmpdir), 'checkout-{}'.format(mask))

        create_test_file(sourcedir, 'a.txt', mode=0o644 & mask)
        create_test_file(sourcedir, 'b.txt', mode=0o755 & mask)
        create_test_file(sourcedir, 'c.txt', mode=0o4755 & mask)
        create_test_file(sourcedir, 'd.txt', mode=0o2755 & mask)
        create_test_file(sourcedir, 'e.txt', mode=0o1755 & mask)
        create_test_directory(sourcedir, 'dir-a', mode=0o0755 & mask)
        create_test_directory(sourcedir, 'dir-b', mode=0o4755 & mask)
        create_test_directory(sourcedir, 'dir-c', mode=0o2755 & mask)
        create_test_directory(sourcedir, 'dir-d', mode=0o1755 & mask)
        try:
            result = cli.run(project=project, args=['build', element_name])
            result.assert_success()

            result = cli.run(project=project, args=['checkout', element_name, checkoutdir])
            result.assert_success()

            with open(os.path.join(checkoutdir, 'ls-l'), 'r') as f:
                return f.read()
        finally:
            cache_dir = os.path.join(integration_cache, 'artifacts')
            cli.remove_artifact_from_cache(project, element_name,
                                           cache_dir=cache_dir)

    assert get_value_for_mask(0o7777) == get_value_for_mask(0o0700)
