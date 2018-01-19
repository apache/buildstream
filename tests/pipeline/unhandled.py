import os
import pytest
import re
import subprocess
import sys

from buildstream._exceptions import ErrorDomain
from tests.testutils.runcli import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'unhandled-error',
)


@pytest.mark.datafiles(DATA_DIR)
def test_unhandled_exception(cli, datafiles, tmpdir):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    process = subprocess.Popen(['bst', 'fetch', 'error.bst'],
                               cwd=basedir, stderr=subprocess.PIPE)
    try:
        (stdout, stderr) = process.communicate()
    except TimeoutExpired:
        proc.kill()
        (stdout, stderr) = process.communicate()

    print("stdout:\n{}\n".format(stdout))
    print("stderr:\n{}\n".format(stderr))

    # The process should have caught the exception and explicitly exited with code -1
    assert process.returncode == 255
    assert stderr is not None

    expected_error = "BUG\s+preflighterror: Unsatisfied requirements in preflight, raising this error"

    match = re.search(expected_error, stderr.decode("utf-8"))
    assert match is not None
