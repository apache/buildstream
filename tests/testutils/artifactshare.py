import string
import pytest
import subprocess
import os

from buildstream import _yaml

from .site import HAVE_OSTREE_CLI


# ArtifactShare()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#
class ArtifactShare():

    def __init__(self, directory):

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

        os.makedirs(self.repo)

        self.init()
        self.update_summary()

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

    # update_summary():
    #
    # Ensure that the summary is up to date
    #
    def update_summary(self):
        subprocess.call(['ostree', 'summary',
                         '--update',
                         '--repo', self.repo])

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


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
def create_artifact_share(directory):

    return ArtifactShare(directory)
