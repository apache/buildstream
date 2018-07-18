import os
import pytest
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils import cli, generate_junction, create_repo


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'include'
)


@pytest.mark.datafiles(DATA_DIR)
def test_include_project_file(cli, datafiles):
    project = os.path.join(str(datafiles), 'file')
    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['included'] == 'True'


@pytest.mark.datafiles(DATA_DIR)
def test_include_junction_file(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'junction')

    generate_junction(tmpdir,
                      os.path.join(project, 'subproject'),
                      os.path.join(project, 'junction.bst'),
                      store_ref=True)

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['included'] == 'True'


@pytest.mark.datafiles(DATA_DIR)
def test_include_junction_options(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options')

    result = cli.run(project=project, args=[
        '-o', 'build_arch', 'x86_64',
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['build_arch'] == 'x86_64'


@pytest.mark.datafiles(DATA_DIR)
def test_junction_element_partial_project_project(cli, tmpdir, datafiles):
    """
    Junction elements never depend on fully include processed project.
    """

    project = os.path.join(str(datafiles), 'junction')

    subproject_path = os.path.join(project, 'subproject')
    junction_path = os.path.join(project, 'junction.bst')

    repo = create_repo('git', str(tmpdir))

    ref = repo.create(subproject_path)

    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, junction_path)

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'junction.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'included' not in loaded


@pytest.mark.datafiles(DATA_DIR)
def test_junction_element_not_partial_project_file(cli, tmpdir, datafiles):
    """
    Junction elements never depend on fully include processed project.
    """

    project = os.path.join(str(datafiles), 'file_with_subproject')

    subproject_path = os.path.join(project, 'subproject')
    junction_path = os.path.join(project, 'junction.bst')

    repo = create_repo('git', str(tmpdir))

    ref = repo.create(subproject_path)

    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, junction_path)

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'junction.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'included' in loaded


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'overrides')

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'manual_main_override' in loaded
    assert 'manual_included_override' in loaded


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides_composition(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'overrides')

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{config}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'build-commands' in loaded
    assert loaded['build-commands'] == ['first', 'second']


@pytest.mark.datafiles(DATA_DIR)
def test_include_element_overrides_sub_include(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'sub-include')

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'included' in loaded


@pytest.mark.datafiles(DATA_DIR)
def test_junction_do_not_use_included_overrides(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'overrides-junction')

    generate_junction(tmpdir,
                      os.path.join(project, 'subproject'),
                      os.path.join(project, 'junction.bst'),
                      store_ref=True)

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'junction.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'main_override' in loaded
    assert 'included_override' not in loaded


@pytest.mark.datafiles(DATA_DIR)
def test_conditional_in_fragment(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'conditional')

    result = cli.run(project=project, args=[
        '-o', 'build_arch', 'x86_64',
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert 'size' in loaded
    assert loaded['size'] == '8'


@pytest.mark.datafiles(DATA_DIR)
def test_inner(cli, datafiles):
    project = os.path.join(str(datafiles), 'inner')
    result = cli.run(project=project, args=[
        '-o', 'build_arch', 'x86_64',
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['build_arch'] == 'x86_64'


@pytest.mark.datafiles(DATA_DIR)
def test_recusive_include(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'recursive')

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.RECURSIVE_INCLUDE)


@pytest.mark.datafiles(DATA_DIR)
def test_local_to_junction(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'local_to_junction')

    generate_junction(tmpdir,
                      os.path.join(project, 'subproject'),
                      os.path.join(project, 'junction.bst'),
                      store_ref=True)

    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['included'] == 'True'


@pytest.mark.datafiles(DATA_DIR)
def test_include_project_file(cli, datafiles):
    project = os.path.join(str(datafiles), 'string')
    result = cli.run(project=project, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['included'] == 'True'
