# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

#
# This test case tests the failure modes of loading a plugin
# after it has already been discovered via it's origin.
#

import os
import shutil
import pytest

from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "loading")


def update_project(project_path, updated_configuration):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf.update(updated_configuration)

    _yaml.roundtrip_dump(project_conf, project_conf_path)


# Sets up the element.bst file so that it requires a source
# or element plugin.
#
def setup_element(project_path, plugin_type, plugin_name):
    element_dir = os.path.join(project_path, "elements")
    element_path = os.path.join(element_dir, "element.bst")
    os.makedirs(element_dir, exist_ok=True)

    if plugin_type == "elements":
        element = {"kind": plugin_name}
    else:
        element = {"kind": "manual", "sources": [{"kind": plugin_name}]}

    _yaml.roundtrip_dump(element, element_path)


# This function is used for pytest skipif() expressions.
#
# Tests which require our plugins in tests/plugins/pip-samples need
# to check if these plugins are installed, they are only guaranteed
# to be installed when running tox, but not when using pytest directly
# to test that BuildStream works when integrated in your system.
#
def pip_sample_packages():
    import pkg_resources

    required = {"sample-plugins"}
    installed = {pkg.key for pkg in pkg_resources.working_set}  # pylint: disable=not-an-iterable
    missing = required - installed

    if missing:
        return False

    return True


SAMPLE_PACKAGES_SKIP_REASON = """
The sample plugins package used to test pip plugin origins is not installed.

This is usually tested automatically with `tox`, if you are running
`pytest` directly then you can install these plugins directly using pip.

The plugins are located in the tests/plugins/sample-plugins directory
of your BuildStream checkout.
"""


####################################################
#                     Tests                        #
####################################################
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_nosetup(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(project, {"plugins": [{"origin": "local", "path": "plugins/nosetup", plugin_type: ["nosetup"]}]})
    setup_element(project, plugin_type, "nosetup")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "missing-setup-function")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_setup_not_function(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {"plugins": [{"origin": "local", "path": "plugins/setupnotfunction", plugin_type: ["setupnotfunction"]}]},
    )
    setup_element(project, plugin_type, "setupnotfunction")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "setup-is-not-function")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_setup_returns_not_type(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {"origin": "local", "path": "plugins/setupreturnsnottype", plugin_type: ["setupreturnsnottype"]}
            ]
        },
    )
    setup_element(project, plugin_type, "setupreturnsnottype")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "setup-returns-not-type")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_setup_returns_bad_type(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {"origin": "local", "path": "plugins/setupreturnsbadtype", plugin_type: ["setupreturnsbadtype"]}
            ]
        },
    )
    setup_element(project, plugin_type, "setupreturnsbadtype")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "setup-returns-bad-type")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_missing_min_version(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "nominversion"),
                    plugin_type: ["nominversion"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "nominversion")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "missing-min-version")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.parametrize("plugin", [("badstring"), ("number"), ("dict"), ("list")])
def test_malformed_min_version(cli, datafiles, plugin_type, plugin):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "malformedminversion"),
                    plugin_type: [plugin],
                }
            ]
        },
    )
    setup_element(project, plugin_type, plugin)

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "malformed-min-version")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_incompatible_major_version(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "incompatiblemajor"),
                    plugin_type: ["incompatiblemajor"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "incompatiblemajor")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "incompatible-major-version")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_incompatible_minor_version(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "incompatibleminor"),
                    plugin_type: ["incompatibleminor"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "incompatibleminor")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "incompatible-minor-version")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_plugin_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)

    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "plugin-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_plugin_found(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "found")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_deprecation_warnings(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "deprecated"),
                    plugin_type: ["deprecated"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "deprecated")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()
    assert "Here is some detail." in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_deprecation_warning_suppressed_by_origin(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "deprecated"),
                    "allow-deprecated": True,
                    plugin_type: ["deprecated"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "deprecated")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()
    assert "Here is some detail." not in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_deprecation_warning_suppressed_specifically(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "deprecated"),
                    plugin_type: [{"kind": "deprecated", "allow-deprecated": True}],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "deprecated")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()
    assert "Here is some detail." not in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_pip_origin_load_success(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project, {"plugins": [{"origin": "pip", "package-name": "sample-plugins", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_pip_origin_with_constraints(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {"origin": "pip", "package-name": "sample-plugins>=1.0,<1.2.5,!=1.1.3", plugin_type: ["sample"],}
            ]
        },
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_pip_origin_package_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project, {"plugins": [{"origin": "pip", "package-name": "not-a-package", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "package-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_pip_origin_plugin_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project, {"plugins": [{"origin": "pip", "package-name": "sample-plugins", plugin_type: ["notfound"],}]},
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "plugin-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_pip_origin_version_conflict(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project, {"plugins": [{"origin": "pip", "package-name": "sample-plugins>=1.4", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "package-version-conflict")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_pip_origin_malformed_constraints(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project, {"plugins": [{"origin": "pip", "package-name": "sample-plugins>1.4,A", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "package-malformed-requirement")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_plugin_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subproject, "plugins"))

    update_project(
        project, {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["found"],}]},
    )
    update_project(
        subproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "found")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_plugin_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subproject, "plugins"))

    # The toplevel says to search for the "notfound" plugin in the subproject
    #
    update_project(
        project,
        {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["notfound"],}]},
    )

    # The subproject only configures the "found" plugin
    #
    update_project(
        subproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "junction-plugin-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_deep_plugin_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")
    subsubproject = os.path.join(subproject, "subsubproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subsubproject, "plugins"))

    update_project(
        project, {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["found"],}]},
    )
    update_project(
        subproject,
        {"plugins": [{"origin": "junction", "junction": "subsubproject-junction.bst", plugin_type: ["found"],}]},
    )
    update_project(
        subsubproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "found")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_deep_plugin_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")
    subsubproject = os.path.join(subproject, "subsubproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subsubproject, "plugins"))

    # The toplevel says to search for the "notfound" plugin in the subproject
    #
    update_project(
        project,
        {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["notfound"],}]},
    )

    # The subproject says to search for the "notfound" plugin in the subproject
    #
    update_project(
        subproject,
        {"plugins": [{"origin": "junction", "junction": "subsubproject-junction.bst", plugin_type: ["notfound"],}]},
    )

    # The subsubproject only configures the "found" plugin
    #
    update_project(
        subsubproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "junction-plugin-load-error")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_junction_pip_plugin_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subproject, "plugins"))

    update_project(
        project,
        {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["sample"],}]},
    )
    update_project(
        subproject, {"plugins": [{"origin": "pip", "package-name": "sample-plugins", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_junction_pip_plugin_version_conflict(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subproject, "plugins"))

    update_project(
        project,
        {"plugins": [{"origin": "junction", "junction": "subproject-junction.bst", plugin_type: ["sample"],}]},
    )
    update_project(
        subproject, {"plugins": [{"origin": "pip", "package-name": "sample-plugins>=1.4", plugin_type: ["sample"],}]},
    )
    setup_element(project, plugin_type, "sample")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "junction-plugin-load-error")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_full_path_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")
    subsubproject = os.path.join(subproject, "subsubproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subsubproject, "plugins"))

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst:subsubproject-junction.bst",
                    plugin_type: ["found"],
                }
            ]
        },
    )
    update_project(
        subsubproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "found")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("plugin_type", [("elements"), ("sources")])
def test_junction_full_path_not_found(cli, datafiles, plugin_type):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")
    subsubproject = os.path.join(subproject, "subsubproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subsubproject, "plugins"))

    # The toplevel says to search for the "notfound" plugin in the subproject
    #
    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst:subsubproject-junction.bst",
                    plugin_type: ["notfound"],
                }
            ]
        },
    )

    # The subsubproject only configures the "found" plugin
    #
    update_project(
        subsubproject,
        {
            "plugins": [
                {"origin": "local", "path": os.path.join("plugins", plugin_type, "found"), plugin_type: ["found"],}
            ]
        },
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "junction-plugin-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "plugin_type,provenance",
    [("elements", "project.conf [line 10 column 2]"), ("sources", "project.conf [line 10 column 2]")],
)
def test_junction_invalid_full_path(cli, datafiles, plugin_type, provenance):
    project = str(datafiles)
    subproject = os.path.join(project, "subproject")
    subsubproject = os.path.join(subproject, "subsubproject")

    shutil.copytree(os.path.join(project, "plugins"), os.path.join(subsubproject, "plugins"))

    # The toplevel says to search for the "notfound" plugin in the subproject
    #
    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst:pony-junction.bst",
                    plugin_type: ["notfound"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
    assert provenance in result.stderr
