import string
import pytest
import subprocess
import os
import shutil
from collections import namedtuple

from contextlib import contextmanager

from buildstream import _yaml

from .site import HAVE_OSTREE_CLI


# ArtifactShare()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#    total_space (int): Mock total disk space on artifact server
#    free_space (int): Mock free disk space on artifact server
#
class ArtifactShare():

    def __init__(self, directory, *, total_space=None, free_space=None):

        # We need the ostree CLI for tests which use this
        #
        if not HAVE_OSTREE_CLI:
            pytest.skip("ostree cli is not available")

        # The working directory for the artifact share (in case it
        # needs to do something outside of it's backend's storage folder).
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in.
        #
        # Unless this gets more complicated, just use this directly
        # in tests as a remote artifact push/pull configuration
        #
        self.repo = os.path.join(self.directory, 'repo')

        self.total_space = total_space
        self.free_space = free_space

        os.makedirs(self.repo)

        self.init()

    # init():
    #
    # Initializes the artifact share
    #
    # Returns:
    #    (smth): A new ref corresponding to this commit, which can
    #            be passed as the ref in the Repo.source_config() API.
    #
    def init(self):
        subprocess.call(['ostree', 'init',
                         '--repo', self.repo,
                         '--mode', 'archive-z2'])

        # Optionally mock statvfs
        if self.total_space:
            if self.free_space is None:
                self.free_space = self.total_space
            os.statvfs = self._mock_statvfs

    # has_artifact():
    #
    # Checks whether the artifact is present in the share
    #
    # Args:
    #    project_name (str): The project name
    #    element_name (str): The element name
    #    cache_key (str): The cache key
    #
    # Returns:
    #    (bool): True if the artifact exists in the share, otherwise false.
    def has_artifact(self, project_name, element_name, cache_key):

        # NOTE: This should be kept in line with our ostree
        #       based artifact cache code, the below is the
        #       same algo for creating an artifact reference
        #

        # Chop off the .bst suffix first
        assert element_name.endswith('.bst')
        element_name = element_name[:-4]

        valid_chars = string.digits + string.ascii_letters + '-._'
        element_name = ''.join([
            x if x in valid_chars else '_'
            for x in element_name
        ])
        artifact_key = '{0}/{1}/{2}'.format(project_name, element_name, cache_key)

        if not subprocess.call(['ostree', 'rev-parse',
                                '--repo', self.repo,
                                artifact_key]):
            return True

        return False

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        shutil.rmtree(self.directory)

    def _mock_statvfs(self, path):
        repo_size = 0
        for root, _, files in os.walk(self.repo):
            for filename in files:
                repo_size += os.path.getsize(os.path.join(root, filename))

        return statvfs_result(f_blocks=self.total_space,
                              f_bfree=self.free_space - repo_size,
                              f_bsize=1)


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
@contextmanager
def create_artifact_share(directory, *, total_space=None, free_space=None):
    share = ArtifactShare(directory, total_space=total_space, free_space=free_space)
    try:
        yield share
    finally:
        share.close()


statvfs_result = namedtuple('statvfs_result', 'f_blocks f_bfree f_bsize')
