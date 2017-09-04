import shutil
import subprocess
from .repo import Repo

GIT_ENV = {
    'GIT_AUTHOR_DATE': '1320966000 +0200',
    'GIT_AUTHOR_NAME': 'tomjon',
    'GIT_AUTHOR_EMAIL': 'tom@jon.com',
    'GIT_COMMITTER_DATE': '1320966000 +0200',
    'GIT_COMMITTER_NAME': 'tomjon',
    'GIT_COMMITTER_EMAIL': 'tom@jon.com'
}


class Git(Repo):

    def create(self, directory):
        self.copy_directory(directory, self.repo)
        subprocess.call(['git', 'init', '.'], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'add', '.'], env=GIT_ENV, cwd=self.repo)
        subprocess.call(['git', 'commit', '-m', 'Initial commit'], env=GIT_ENV, cwd=self.repo)
        return self.latest_commit()

    def source_config(self, ref=None):
        config = {
            'kind': 'git',
            'url': 'file://' + self.repo,
            'track': 'master'
        }
        if ref is not None:
            config['ref'] = ref

        return config

    def latest_commit(self):
        output = subprocess.check_output([
            'git', 'rev-parse', 'master'
        ], env=GIT_ENV, cwd=self.repo)
        return output.decode('UTF-8').strip()
