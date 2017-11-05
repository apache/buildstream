import shutil
import subprocess
import pytest

from .repo import Repo
from ..site import HAVE_GIT

GIT_ENV = {
    'GIT_AUTHOR_DATE': '1320966000 +0200',
    'GIT_AUTHOR_NAME': 'tomjon',
    'GIT_AUTHOR_EMAIL': 'tom@jon.com',
    'GIT_COMMITTER_DATE': '1320966000 +0200',
    'GIT_COMMITTER_NAME': 'tomjon',
    'GIT_COMMITTER_EMAIL': 'tom@jon.com'
}


class Git(Repo):

    def __init__(self, directory, subdir):
        if not HAVE_GIT:
            pytest.skip("git is not available")

        self.submodules = {}

        super(Git, self).__init__(directory, subdir)

    def create(self, directory):
        self.copy_directory(directory, self.repo)
        subprocess.call(['git', 'init', '.'], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'add', '.'], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'commit', '-m', 'Initial commit'], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def add_submodule(self, subdir, url):
        self.submodules[subdir] = url
        subprocess.call(['git', 'submodule', 'add', url, subdir], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'commit', '-m', 'Added the submodule'], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def source_config(self, ref=None):
        config = {
            'kind': 'git',
            'url': 'file://' + self.repo,
            'track': 'master'
        }
        if ref is not None:
            config['ref'] = ref

        if self.submodules:
            config['submodules'] = {}
            for subdir, url in self.submodules.items():
                config['submodules'][subdir] = {'url': url}

        return config

    def latest_commit(self):
        output = subprocess.check_output([
            'git', 'rev-parse', 'master'
        ], env=GIT_ENV, cwd=self.repo)
        return output.decode('UTF-8').strip()
