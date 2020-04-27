# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream.testing import cli  # pylint: disable=unused-import


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "deprecationwarnings")

_DEPRECATION_MESSAGE = "Here is some detail."
_DEPRECATION_WARNING = "Using deprecated plugin deprecated_plugin: {}".format(_DEPRECATION_MESSAGE)


@pytest.mark.datafiles(DATA_DIR)
def test_deprecation_warning_present(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, args=["show", "deprecated.bst"])
    result.assert_success()
    assert _DEPRECATION_WARNING in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_suppress_deprecation_warning(cli, datafiles):
    project = str(datafiles)
    cli.run(project=project, args=["show", "manual.bst"])

    element_overrides = "elements:\n" "  deprecated_plugin:\n" "    suppress-deprecation-warnings : True\n"

    project_conf = os.path.join(project, "project.conf")
    with open(project_conf, "a") as f:
        f.write(element_overrides)

    result = cli.run(project=project, args=["show", "deprecated.bst"])
    result.assert_success()
    assert _DEPRECATION_WARNING not in result.stderr
