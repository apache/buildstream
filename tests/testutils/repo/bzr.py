import os
import subprocess
import pytest

from .repo import Repo
from ..site import HAVE_BZR

BZR_ENV = {
    "BZR_EMAIL": "Testy McTesterson <testy.mctesterson@example.com>"
}


class Bzr(Repo):

    def __init__(self, directory, subdir):
        if not HAVE_BZR:
            pytest.skip("bzr is not available")
        super(Bzr, self).__init__(directory, subdir)

    def create(self, directory):
        branch_dir = os.path.join(self.repo, 'trunk')

        subprocess.call(['bzr', 'init-repo', self.repo], env=BZR_ENV)
        subprocess.call(['bzr', 'init', branch_dir], env=BZR_ENV)
        self.copy_directory(directory, branch_dir)
        subprocess.call(['bzr', 'add', '.'], env=BZR_ENV, cwd=branch_dir)
        subprocess.call(['bzr', 'commit', '--message="Initial commit"'],
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
        output = subprocess.check_output([
            'bzr', 'version-info',
            '--custom', '--template={revno}',
            os.path.join(self.repo, 'trunk')
        ], env=BZR_ENV)
        return output.decode('UTF-8').strip()
