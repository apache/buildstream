import os
import io
import pytest
import difflib
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


with open(os.path.join(DATA_DIR, 'elements', 'manual-build-output.txt'), 'r') as f:
    MANUAL_OUTPUT = f.read()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,format,expected", [
    ('import-bin.bst', '%{name}', 'import-bin.bst'),
    ('import-bin.bst', '%{state}', 'buildable'),
    ('compose-all.bst', '%{state}', 'waiting'),
    ('manual-build.bst', '%{script}', MANUAL_OUTPUT)
])
def test_show(cli, datafiles, target, format, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', format,
        target])
    assert result.exit_code == 0

    if result.output.strip() != expected:
        diff = difflib.context_diff(result.output.strip().splitlines(True),
                                    expected.splitlines(True),
                                    fromfile='output', tofile='expected')

        raise AssertionError("Received unexpected output:\n{}\n"
                             .format(''.join(diff)))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,except_,expected", [
    ('target.bst', 'import-bin.bst', ['import-dev.bst', 'compose-all.bst', 'target.bst']),
    ('target.bst', 'import-dev.bst', ['import-bin.bst', 'compose-all.bst', 'target.bst']),
    ('target.bst', 'compose-all.bst', ['import-bin.bst', 'target.bst']),
    ('compose-all.bst', 'import-bin.bst', ['import-dev.bst', 'compose-all.bst'])
])
def test_show_except(cli, datafiles, target, except_, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'all',
        '--format', '%{name}',
        '--except', except_,
        target])

    assert result.exit_code == 0

    results = result.output.strip().splitlines()
    if results != expected:
        raise AssertionError("Expected elements:\n{}\nInstead received elements:\n{}"
                             .format(expected, results))
