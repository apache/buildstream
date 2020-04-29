# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils import filetypegenerator


# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_project_conf(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_PROJECT_CONF)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missingname")
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_element(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-element")
    result = cli.run(project=project, args=["show", "manual.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "manual.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_missing_junction(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-junction")
    result = cli.run(project=project, args=["show", "manual.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "manual.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_empty_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "emptyname")
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_invalid_project_name(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalidname")
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_SYMBOL_NAME)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_invalid_yaml(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "invalid-yaml")
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_default_project(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "default")
    result = cli.run(project=project, args=["show", "--format", "%{env}", "manual.bst"])
    result.assert_success()

    # Read back some of our project defaults from the env
    env = _yaml.load_data(result.output)
    assert env.get_str("USER") == "tomjon"
    assert env.get_str("TERM") == "dumb"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_project_from_subdir(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "project-from-subdir")
    result = cli.run(
        project=project, cwd=os.path.join(project, "subdirectory"), args=["show", "--format", "%{env}", "manual.bst"]
    )
    result.assert_success()

    # Read back some of our project defaults from the env
    env = _yaml.load_data(result.output)
    assert env.get_str("USER") == "tomjon"
    assert env.get_str("TERM") == "dumb"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_override_project_path(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "overridepath")
    result = cli.run(project=project, args=["show", "--format", "%{env}", "manual.bst"])
    result.assert_success()

    # Read back the overridden path
    env = _yaml.load_data(result.output)
    assert env.get_str("PATH") == "/bin:/sbin"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_project_unsupported(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "unsupported")

    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNSUPPORTED_PROJECT)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "element-path"))
def test_missing_element_path_directory(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "element-path"))
def test_element_path_not_a_directory(cli, datafiles):
    project = str(datafiles)
    path = os.path.join(project, "elements")
    for _file_type in filetypegenerator.generate_file_types(path):
        result = cli.run(project=project, args=["workspace", "list"])
        if not os.path.isdir(path):
            result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID_KIND)
        else:
            result.assert_success()


@pytest.mark.datafiles(os.path.join(DATA_DIR, "local-plugin"))
def test_missing_local_plugin_directory(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["workspace", "list"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "local-plugin"))
def test_local_plugin_not_directory(cli, datafiles):
    project = str(datafiles)
    path = os.path.join(project, "plugins")
    for _file_type in filetypegenerator.generate_file_types(path):
        result = cli.run(project=project, args=["workspace", "list"])
        if not os.path.isdir(path):
            result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.PROJ_PATH_INVALID_KIND)
        else:
            result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
def test_plugin_no_load_ref(cli, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename, "plugin-no-load-ref")

    # Generate project with access to the noloadref plugin and project.refs enabled
    #
    config = {
        "name": "test",
        "min-version": "2.0",
        "ref-storage": ref_storage,
        "plugins": [{"origin": "local", "path": "plugins", "sources": ["noloadref"]}],
    }
    _yaml.roundtrip_dump(config, os.path.join(project, "project.conf"))

    result = cli.run(project=project, silent=True, args=["show", "noloadref.bst"])

    # There is no error if project.refs is not in use, otherwise we
    # assert our graceful failure
    if ref_storage == "inline":
        result.assert_success()
    else:
        result.assert_main_error(ErrorDomain.SOURCE, "unsupported-load-ref")


@pytest.mark.datafiles(DATA_DIR)
def test_plugin_preflight_error(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "plugin-preflight-error")
    result = cli.run(project=project, args=["source", "fetch", "error.bst"])
    result.assert_main_error(ErrorDomain.SOURCE, "the-preflight-error")


@pytest.mark.datafiles(DATA_DIR)
def test_duplicate_plugins(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "duplicate-plugins")
    result = cli.run(project=project, silent=True, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "duplicate-plugin")


# Assert that we get a different cache key for target.bst, depending
# on a conditional statement we have placed in the project.refs file.
#
@pytest.mark.datafiles(DATA_DIR)
def test_project_refs_options(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "refs-options")

    result1 = cli.run(
        project=project,
        silent=True,
        args=["--option", "test", "True", "show", "--deps", "none", "--format", "%{key}", "target.bst"],
    )
    result1.assert_success()

    result2 = cli.run(
        project=project,
        silent=True,
        args=["--option", "test", "False", "show", "--deps", "none", "--format", "%{key}", "target.bst"],
    )
    result2.assert_success()

    # Assert that the cache keys are different
    assert result1.output != result2.output


@pytest.mark.datafiles(os.path.join(DATA_DIR, "element-path"))
def test_element_path_project_path_contains_symlinks(cli, datafiles, tmpdir):
    real_project = str(datafiles)
    linked_project = os.path.join(str(tmpdir), "linked")
    os.symlink(real_project, linked_project)
    os.makedirs(os.path.join(real_project, "elements"), exist_ok=True)
    with open(os.path.join(real_project, "elements", "element.bst"), "w") as f:
        f.write("kind: manual\n")
    result = cli.run(project=linked_project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_empty_depends(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "empty-depends")
    result = cli.run(project=project, args=["show", "manual.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
