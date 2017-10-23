#!/usr/bin/env python3
#
# Automatically create or update the .expected files in the
# cache key test directory.
#
# Simply run without any arguments, from anywhere, e.g.:
#
#   ./tests/cachekey/update.py
#
# After this, add any files which were newly created and commit
# the result in order to adjust the cache key test to changed
# keys.
#
import os
import tempfile
from tests.testutils.runcli import Cli

# This weird try / except is needed, because this will be imported differently
# when pytest runner imports them vs when you run the updater directly from
# this directory.
try:
    from cachekey import element_filename, parse_output_keys, load_expected_keys
except ImportError:
    from .cachekey import element_filename, parse_output_keys, load_expected_keys

# Project directory
PROJECT_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def write_expected_key(element_name, actual_key):
    expected_file = element_filename(PROJECT_DIR, element_name, 'expected')
    with open(expected_file, 'w') as f:
        f.write(actual_key)


def update_keys():

    with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as tmpdir:
        directory = os.path.join(tmpdir, 'cache')
        os.makedirs(directory)
        cli = Cli(directory, verbose=False)

        # Run bst show
        result = cli.run(project=PROJECT_DIR, silent=True, args=[
            '--no-colors',
            'show', '--format', '%{name}::%{full-key}',
            'target.bst'
        ])

        # Load the actual keys, and the expected ones if they exist
        actual_keys = parse_output_keys(result.output)
        expected_keys = load_expected_keys(PROJECT_DIR, actual_keys, raise_error=False)

        for element_name in actual_keys:
            expected = element_filename(PROJECT_DIR, element_name, 'expected')

            if actual_keys[element_name] != expected_keys[element_name]:
                if not expected_keys[element_name]:
                    print("Creating new expected file: {}".format(expected))
                else:
                    print("Updating expected file: {}".format(expected))

                write_expected_key(element_name, actual_keys[element_name])

if __name__ == '__main__':
    update_keys()
