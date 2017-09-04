import os
import tarfile
import hashlib

from .repo import Repo


class Tar(Repo):

    def create(self, directory):
        tarball = os.path.join(self.repo, 'file.tar.gz')

        old_dir = os.getcwd()
        os.chdir(directory)
        with tarfile.open(tarball, "w:gz") as tar:
            tar.add(".")
        os.chdir(old_dir)

        return sha256sum(tarball)

    def source_config(self, ref=None):
        tarball = os.path.join(self.repo, 'file.tar.gz')
        config = {
            'kind': 'tar',
            'url': 'file://' + tarball,
            'track': 'master',
            'directory': ''
        }
        if ref is not None:
            config['ref'] = ref

        return config


def sha256sum(filename):
    h = hashlib.sha256()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()
