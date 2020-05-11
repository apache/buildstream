import pytest
import subprocess
from .repo import Repo

from ..site import HAVE_OSTREE_CLI, HAVE_OSTREE


class OSTree(Repo):

    def __init__(self, directory, subdir):
        if not HAVE_OSTREE_CLI or not HAVE_OSTREE:
            pytest.skip("ostree cli is not available")

        super(OSTree, self).__init__(directory, subdir)

    def create(self, directory, *, gpg_sign=None, gpg_homedir=None):
        subprocess.call(['ostree', 'init',
                         '--repo', self.repo,
                         '--mode', 'archive-z2'])

        commit_args = ['ostree', 'commit',
                       '--repo', self.repo,
                       '--branch', 'master',
                       '--subject', 'Initial commit']

        if gpg_sign and gpg_homedir:
            commit_args += [
                '--gpg-sign={}'.format(gpg_sign),
                '--gpg-homedir={}'.format(gpg_homedir)
            ]

        commit_args += [directory]

        subprocess.call(commit_args)

        latest = self.latest_commit()

        return latest

    def source_config(self, ref=None, *, gpg_key=None):
        config = {
            'kind': 'ostree',
            'url': 'file://' + self.repo,
            'track': 'master'
        }
        if ref is not None:
            config['ref'] = ref
        if gpg_key is not None:
            config['gpg-key'] = gpg_key

        return config

    def latest_commit(self):
        output = subprocess.check_output([
            'ostree', 'rev-parse',
            '--repo', self.repo,
            'master'
        ])
        return output.decode('UTF-8').strip()
