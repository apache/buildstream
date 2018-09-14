import os
import pytest
import shutil
import subprocess

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

    def add_commit(self):
        subprocess.call(['git', 'commit', '--allow-empty', '-m', 'Additional commit'],
                        env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def add_file(self, filename):
        shutil.copy(filename, self.repo)
        subprocess.call(['git', 'add', os.path.basename(filename)], env=GIT_ENV, cwd=self.repo)
        subprocess.call([
            'git', 'commit', '-m', 'Added {}'.format(os.path.basename(filename))
        ], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def modify_file(self, new_file, path):
        shutil.copy(new_file, os.path.join(self.repo, path))
        subprocess.call([
            'git', 'commit', path, '-m', 'Modified {}'.format(os.path.basename(path))
        ], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def add_submodule(self, subdir, url=None, checkout=None):
        submodule = {}
        if checkout is not None:
            submodule['checkout'] = checkout
        if url is not None:
            submodule['url'] = url
        self.submodules[subdir] = submodule
        subprocess.call(['git', 'submodule', 'add', url, subdir], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'commit', '-m', 'Added the submodule'], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def source_config(self, ref=None, checkout_submodules=None):
        config = {
            'kind': 'git',
            'url': 'file://' + self.repo,
            'track': 'master'
        }
        if ref is not None:
            config['ref'] = ref
        if checkout_submodules is not None:
            config['checkout-submodules'] = checkout_submodules

        if self.submodules:
            config['submodules'] = dict(self.submodules)

        return config

    def latest_commit(self):
        output = subprocess.check_output([
            'git', 'rev-parse', 'master'
        ], env=GIT_ENV, cwd=self.repo)
        return output.decode('UTF-8').strip()

    def branch(self, branch_name):
        subprocess.call(['git', 'checkout', '-b', branch_name], env=GIT_ENV, cwd=self.repo)
