import pytest
import subprocess
from .repo import Repo

from ..site import HAVE_OSTREE_CLI, HAVE_OSTREE


class OSTree(Repo):

    def __init__(self, directory, subdir):
        if not HAVE_OSTREE_CLI or not HAVE_OSTREE:
            pytest.skip("ostree cli is not available")

        super(OSTree, self).__init__(directory, subdir)

    def create(self, directory):
        subprocess.call(['ostree', 'init',
                         '--repo', self.repo,
                         '--mode', 'archive-z2'])
        subprocess.call(['ostree', 'commit',
                         '--repo', self.repo,
                         '--branch', 'master',
                         '--subject', 'Initial commit',
                         directory])

        latest = self.latest_commit()

        return latest

    def source_config(self, ref=None):
        config = {
            'kind': 'ostree',
            'url': 'file://' + self.repo,
            'track': 'master'
        }
        if ref is not None:
            config['ref'] = ref

        return config

    def latest_commit(self):
        output = subprocess.check_output([
            'ostree', 'rev-parse',
            '--repo', self.repo,
            'master'
        ])
        return output.decode('UTF-8').strip()
