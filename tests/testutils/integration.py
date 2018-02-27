import os

from buildstream import _yaml


# Return a list of files relative to the given directory
def walk_dir(root):
    for dirname, dirnames, filenames in os.walk(root):
        # print path to all subdirectories first.
        for subdirname in dirnames:
            yield os.path.join(dirname, subdirname)[len(root):]

        # print path to all filenames.
        for filename in filenames:
            yield os.path.join(dirname, filename)[len(root):]


# Ensure that a directory contains the given filenames.
def assert_contains(directory, expected):
    missing = set(expected)
    missing.difference_update(walk_dir(directory))
    if len(missing) > 0:
        raise AssertionError("Missing {} expected elements from list: {}"
                             .format(len(missing), missing))
