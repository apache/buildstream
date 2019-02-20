import pytest
import tempfile
import os
from buildstream.plugintestutils import cli
from buildstream import _yaml
import buildstream.plugins.elements.manual


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)

_DEPRECATION_MESSAGE = "Here is some detail."
_DEPRECATION_WARNING = "Using deprecated plugin deprecated_plugin: {}".format(_DEPRECATION_MESSAGE)


@pytest.mark.datafiles(DATA_DIR)
def test_deprecation_warning_present(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['show', 'deprecated.bst'])
    result.assert_success()
    assert _DEPRECATION_WARNING in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_suppress_deprecation_warning(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['show', 'manual.bst'])

    element_overrides = "elements:\n" \
                        "  deprecated_plugin:\n" \
                        "    suppress-deprecation-warnings : True\n"

    project_conf = os.path.join(project, 'project.conf')
    with open(project_conf, 'a') as f:
        f.write(element_overrides)

    result = cli.run(project=project, args=['show', 'deprecated.bst'])
    result.assert_success()
    assert _DEPRECATION_WARNING not in result.stderr
