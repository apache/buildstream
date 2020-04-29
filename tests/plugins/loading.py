# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

#
# This test case tests the failure modes of loading a plugin
# after it has already been discovered via it's origin.
#

import os
import pytest

from buildstream.exceptions import ErrorDomain
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
def test_malformed_min_version(cli, datafiles, plugin_type):
    project = str(datafiles)

    update_project(
        project,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "malformedminversion"),
                    plugin_type: ["malformedminversion"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "malformedminversion")

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
