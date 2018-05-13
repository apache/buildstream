import string
import pytest
import subprocess
import os
import shutil
import signal

from contextlib import contextmanager
from multiprocessing import Process, Queue
import pytest_cov

from buildstream import _yaml
from buildstream._artifactcache.cascache import CASCache
from buildstream._artifactcache.casserver import create_server
from buildstream._context import Context
from buildstream._exceptions import ArtifactError


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

        # The working directory for the artifact share (in case it
        # needs to do something outside of it's backend's storage folder).
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in.
        #
        # Unless this gets more complicated, just use this directly
        # in tests as a remote artifact push/pull configuration
        #
        self.repodir = os.path.join(self.directory, 'repo')

        os.makedirs(self.repodir)

        context = Context()
        context.artifactdir = self.repodir

        self.cas = CASCache(context)

        q = Queue()

        self.process = Process(target=self.run, args=(q,))
        self.process.start()

        # Retrieve port from server subprocess
        port = q.get()

        self.repo = 'http://localhost:{}'.format(port)

    # run():
    #
    # Run the artifact server.
    #
    def run(self, q):
        pytest_cov.embed.cleanup_on_sigterm()

        server = create_server(self.repodir, enable_push=True)
        port = server.add_insecure_port('localhost:0')

        server.start()

        # Send port to parent
        q.put(port)

        # Sleep until termination by signal
        signal.pause()

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

        # NOTE: This should be kept in line with our
        #       artifact cache code, the below is the
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

        try:
            tree = self.cas.resolve_ref(artifact_key)
            return True
        except ArtifactError:
            return False

    # close():
    #
    # Remove the artifact share.
    #
    def close(self):
        self.process.terminate()
        self.process.join()

        shutil.rmtree(self.directory)


# create_artifact_share()
#
# Create an ArtifactShare for use in a test case
#
@contextmanager
def create_artifact_share(directory):
    share = ArtifactShare(directory)
    try:
        yield share
    finally:
        share.close()
