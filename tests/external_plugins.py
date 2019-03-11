import glob
import os
import subprocess
import sys

import pytest


# An ExternalPluginRepo represents a git repository containing a plugin
# with tests that we wish to use as part of our test suite.
#
# Args:
#    name (str): The name of the repository. This is used for impormational purposes
#    url (str): The location from which therepository can be cloned
#    ref (str): A known git ref that we wish to test against
#    test_match_patterns (list[str]): A list of shell style globs which may be
#          used to specify a subset of test files from the repository to run.
#          These must be specified relative to the root of the repository.
class ExternalPluginRepo():
    def __init__(self, name, url, ref, test_match_patterns=None):
        self.name = name
        self.url = url
        self.ref = ref

        if test_match_patterns is None:
            test_match_patterns = ["tests"]

        self._test_match_patterns = test_match_patterns
        self._clone_location = None

    def clone(self, location):
        self._clone_location = os.path.join(location, self.name)
        subprocess.run(['git', 'clone',
                        '--single-branch',
                        '--branch', self.ref,
                        '--depth', '1',
                        self.url,
                        self._clone_location,
                        ])
        return self._clone_location

    def install(self):
        subprocess.run(['pip3', 'install', self._clone_location])

    def test(self, pytest_args):
        test_files = self._match_test_patterns()
        return pytest.main(pytest_args + test_files)

    def _match_test_patterns(self):
        match_list = []
        for pattern in self._test_match_patterns:
            abs_pattern = os.path.join(self._clone_location, pattern)
            print("matching pattern: ", abs_pattern)
            matches = glob.glob(abs_pattern)
            match_list.extend(matches)

        if not match_list:
            raise ValueError("No matches found for patterns {}".format(self._test_match_patterns))
        return match_list


def run_repo_tests(repo, tmpdir, pytest_args):
    print("Cloning repo {} to {}...".format(repo.name, tmpdir))
    repo.clone(tmpdir)

    print("Installing {}...".format(repo.name))
    repo.install()

    print("Testing {}...".format(repo.name))
    return repo.test(pytest_args)


if __name__ == "__main__":
    # Args:
    #    tmpdir: The directory in which this script will clone external
    #            repositories and use pytest's tmpdir.
    #    pytest_args: any remaining arguments to this script will be passed
    #                 directly to it's pytest invocations
    _, tmpdir, *pytest_args = sys.argv

    ALL_EXTERNAL_PLUGINS = [
        ExternalPluginRepo(
            name='bst-plugins-template',
            url='https://gitlab.com/BuildStream/bst-plugins-template.git',
            ref='master'
        ),
    ]

    exit_code = 0
    for plugin in ALL_EXTERNAL_PLUGINS:
        exit_code = run_repo_tests(plugin, tmpdir, pytest_args)
        if exit_code != 0:
            sys.exit(exit_code)
