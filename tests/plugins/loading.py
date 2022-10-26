#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

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
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from buildstream import _yaml

from tests.testutils.repo.git import Git
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON


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
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
        project,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins",
                    plugin_type: ["sample"],
                }
            ]
        },
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
                {
                    "origin": "pip",
                    "package-name": "sample-plugins>=1.0,<1.2.5,!=1.1.3",
                    plugin_type: ["sample"],
                }
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
        project,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "not-a-package",
                    plugin_type: ["sample"],
                }
            ]
        },
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
        project,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins",
                    plugin_type: ["notfound"],
                }
            ]
        },
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
        project,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins>=1.4",
                    plugin_type: ["sample"],
                }
            ]
        },
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
        project,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins>1.4,A",
                    plugin_type: ["sample"],
                }
            ]
        },
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
        project,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["found"],
                }
            ]
        },
    )
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["notfound"],
                }
            ]
        },
    )

    # The subproject only configures the "found" plugin
    #
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
        project,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["found"],
                }
            ]
        },
    )
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subsubproject-junction.bst",
                    plugin_type: ["found"],
                }
            ]
        },
    )
    update_project(
        subsubproject,
        {
            "plugins": [
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["notfound"],
                }
            ]
        },
    )

    # The subproject says to search for the "notfound" plugin in the subproject
    #
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subsubproject-junction.bst",
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
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["sample"],
                }
            ]
        },
    )
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins",
                    plugin_type: ["sample"],
                }
            ]
        },
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
        {
            "plugins": [
                {
                    "origin": "junction",
                    "junction": "subproject-junction.bst",
                    plugin_type: ["sample"],
                }
            ]
        },
    )
    update_project(
        subproject,
        {
            "plugins": [
                {
                    "origin": "pip",
                    "package-name": "sample-plugins>=1.4",
                    plugin_type: ["sample"],
                }
            ]
        },
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
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
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
                {
                    "origin": "local",
                    "path": os.path.join("plugins", plugin_type, "found"),
                    plugin_type: ["found"],
                }
            ]
        },
    )
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.PLUGIN, "junction-plugin-not-found")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "plugin_type,provenance",
    [("elements", "project.conf [line 12 column 2]"), ("sources", "project.conf [line 12 column 2]")],
)
def test_junction_invalid_full_path(cli, datafiles, plugin_type, provenance):
    project = str(datafiles)

    shutil.copy(os.path.join(project, "not-found-{}.conf".format(plugin_type)), os.path.join(project, "project.conf"))
    setup_element(project, plugin_type, "notfound")

    result = cli.run(project=project, args=["show", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
    assert provenance in result.stderr


# Test scenario for junction plugin origins
# =========================================
#
# This is a regression test which ensures that cross junction includes
# at the project.conf level continues to work even in conjunction with
# complex cross junction plugin loading scenarios.
#
#         main project
#         /           \
#        |             |
#  junction (tar)      |
#        |             | include a file across this junction
#        |             |
#        /             |
#  git plugin           \
#                        \
#                  junction (git)
#                         |
#                         |
#                     subproject
#
#
# `bst source track subproject.bst`
#
#
JUNCTION_DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)))


@pytest.mark.datafiles(JUNCTION_DATA_DIR)
def test_load_junction_via_junctioned_plugin(cli, datafiles, tmpdir):
    sample_plugins_dir = os.path.join(str(datafiles), "sample-plugins")
    project = os.path.join(str(datafiles), "junction-with-junction")
    subproject = os.path.join(str(datafiles), "junction-with-junction", "subproject")

    # Create a tar repo containing the sample plugins
    #
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(sample_plugins_dir)

    # Generate the junction to the sample plugins
    #
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "sample-plugins.bst"))

    # Create a git repo containing the subproject
    #
    subproject_repo = Git(str(tmpdir))
    subproject_repo.create(subproject)

    # Generate the subproject junction pointing to the git repo with the subproject
    #
    element = {"kind": "junction", "sources": [subproject_repo.source_config()]}
    _yaml.roundtrip_dump(element, os.path.join(project, "subproject.bst"))

    # Track the subproject
    #
    result = cli.run(project=project, args=["source", "track", "subproject.bst"])
    result.assert_success()

    # Check the included variable resolves in the element
    #
    result = cli.run(
        project=project,
        silent=True,
        args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"],
    )
    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded.get_str("animal") == "pony"

    # Try a subproject element access on the command line, as this project
    # has the potential to make this break.
    #
    result = cli.run(project=project, args=["show", "subproject.bst:target.bst"])
    result.assert_success()
