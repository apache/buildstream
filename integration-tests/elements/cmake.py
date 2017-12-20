import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.integration import format_files, assert_contains


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.datafiles(DATA_DIR)
def test_cmake_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'cmake/step7.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['checkout', element_name, checkout])
    assert result.exit_code == 0

    assert_contains(checkout, ['/usr', '/usr/bin', '/usr/include',
                               '/usr/lib', '/usr/bin/libMathFunctions.a',
                               '/usr/bin/Tutorial',
                               '/usr/include/MathFunctions.h',
                               '/usr/include/TutorialConfig.h',
                               '/usr/lib/debug',
                               '/usr/lib/debug/Tutorial'])


@pytest.mark.datafiles(DATA_DIR)
def test_cmake_run(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    element_name = 'cmake/step7.bst'

    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=['shell', element_name, '/usr/bin/Tutorial', '9'])
    assert result.exit_code == 0

    assert result.output == """Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
Computing sqrt of 9 to be 3
The square root of 9 is 3
"""
