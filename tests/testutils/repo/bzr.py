import os
import subprocess
import pytest

from buildstream.testing import Repo
from buildstream.testing._utils.site import BZR, BZR_ENV, HAVE_BZR


class Bzr(Repo):

    def __init__(self, directory, subdir):
        if not HAVE_BZR:
            pytest.skip("bzr is not available")
        super(Bzr, self).__init__(directory, subdir)
        self.bzr = BZR

    def create(self, directory):
        branch_dir = os.path.join(self.repo, 'trunk')

        subprocess.call([self.bzr, 'init-repo', self.repo], env=BZR_ENV)
        subprocess.call([self.bzr, 'init', branch_dir], env=BZR_ENV)
        self.copy_directory(directory, branch_dir)
        subprocess.call([self.bzr, 'add', '.'], env=BZR_ENV, cwd=branch_dir)
        subprocess.call([self.bzr, 'commit', '--message="Initial commit"'],
                        env=BZR_ENV, cwd=branch_dir)

        return self.latest_commit()

    def source_config(self, ref=None):
        config = {
            'kind': 'bzr',
            'url': 'file://' + self.repo,
            'track': 'trunk'
        }
        if ref is not None:
            config['ref'] = ref

        return config

    def latest_commit(self):
        return subprocess.check_output([
            self.bzr, 'version-info',
            '--custom', '--template={revno}',
            os.path.join(self.repo, 'trunk')
        ], env=BZR_ENV, universal_newlines=True).strip()
