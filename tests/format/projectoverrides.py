# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest
from buildstream import _yaml
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project-overrides")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_prepend_configure_commands(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, "prepend-configure-commands")
    result = cli.run(
        project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", "element.bst"]
    )

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    config_commands = loaded.get_str_list("configure-commands")
    assert len(config_commands) == 3
    assert config_commands[0] == 'echo "Hello World!"'
