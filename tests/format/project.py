import os
import pytest
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils import cli, filetypegenerator


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_project_conf(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_PROJECT_CONF)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missingname")
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_empty_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "emptyname")
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_invalid_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalidname")
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_default_project(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "default")
    result = cli.run(project=project, args=[
        'show', '--format', '%{env}', 'manual.bst'
    ])
    result.assert_success()

    # Read back some of our project defaults from the env
    env = _yaml.load_data(result.output)
    assert (env['USER'] == "tomjon")
    assert (env['TERM'] == "dumb")


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_project_from_subdir(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'project-from-subdir')
    result = cli.run(
        project=project,
        cwd=os.path.join(project, 'subdirectory'),
        args=['show', '--format', '%{env}', 'manual.bst'])
    result.assert_success()

    # Read back some of our project defaults from the env
    env = _yaml.load_data(result.output)
    assert (env['USER'] == "tomjon")
    assert (env['TERM'] == "dumb")


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_override_project_path(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "overridepath")
    result = cli.run(project=project, args=[
        'show', '--format', '%{env}', 'manual.bst'
    ])
    result.assert_success()

    # Read back the overridden path
    env = _yaml.load_data(result.output)
    assert (env['PATH'] == "/bin:/sbin")


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_project_unsupported(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "unsupported")

    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNSUPPORTED_PROJECT)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'element-path'))
def test_missing_element_path_directory(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'element-path'))
def test_element_path_not_a_directory(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    path = os.path.join(project, 'elements')
    for file_type in filetypegenerator.generate_file_types(path):
        result = cli.run(project=project, args=['workspace', 'list'])
        if not os.path.isdir(path):
            result.assert_main_error(ErrorDomain.LOAD,
                                     LoadErrorReason.PROJ_PATH_INVALID_KIND)
        else:
            result.assert_success()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'local-plugin'))
def test_missing_local_plugin_directory(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['workspace', 'list'])
    result.assert_main_error(ErrorDomain.LOAD,
                             LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'local-plugin'))
def test_local_plugin_not_directory(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    path = os.path.join(project, 'plugins')
    for file_type in filetypegenerator.generate_file_types(path):
        result = cli.run(project=project, args=['workspace', 'list'])
        if not os.path.isdir(path):
            result.assert_main_error(ErrorDomain.LOAD,
                                     LoadErrorReason.PROJ_PATH_INVALID_KIND)
        else:
            result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_project_plugin_load_allowed(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'plugin-allowed')
    result = cli.run(project=project, silent=True, args=[
        'show', 'element.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_project_plugin_load_forbidden(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'plugin-forbidden')
    result = cli.run(project=project, silent=True, args=[
        'show', 'element.bst'])
    result.assert_main_error(ErrorDomain.PLUGIN, None)


@pytest.mark.datafiles(DATA_DIR)
def test_project_conf_duplicate_plugins(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'duplicate-plugins')
    result = cli.run(project=project, silent=True, args=[
        'show', 'element.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_YAML)


# Assert that we get a different cache key for target.bst, depending
# on a conditional statement we have placed in the project.refs file.
#
@pytest.mark.datafiles(DATA_DIR)
def test_project_refs_options(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'refs-options')

    result1 = cli.run(project=project, silent=True, args=[
        '--option', 'test', 'True',
        'show',
        '--deps', 'none',
        '--format', '%{key}',
        'target.bst'])
    result1.assert_success()

    result2 = cli.run(project=project, silent=True, args=[
        '--option', 'test', 'False',
        'show',
        '--deps', 'none',
        '--format', '%{key}',
        'target.bst'])
    result2.assert_success()

    # Assert that the cache keys are different
    assert result1.output != result2.output
