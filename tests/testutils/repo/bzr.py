import os
import subprocess
import pytest

from buildstream.testing import Repo
from buildstream.testing._utils.site import BZR, BZR_ENV, HAVE_BZR


class Bzr(Repo):
    def __init__(self, directory, subdir):
        if not HAVE_BZR:
            pytest.skip("bzr is not available")
        super().__init__(directory, subdir)
        self.bzr = BZR

        self.env = os.environ.copy()
        self.env.update(BZR_ENV)

    def create(self, directory):
        # Work around race condition in bzr's creation of ~/.bazaar in
        # ensure_config_dir_exists() when running tests in parallel.
        bazaar_config_dir = os.path.expanduser("~/.bazaar")
        os.makedirs(bazaar_config_dir, exist_ok=True)

        branch_dir = os.path.join(self.repo, "trunk")

        subprocess.call([self.bzr, "init-repo", self.repo], env=self.env)
        subprocess.call([self.bzr, "init", branch_dir], env=self.env)
        self.copy_directory(directory, branch_dir)
        subprocess.call([self.bzr, "add", "."], env=self.env, cwd=branch_dir)
        subprocess.call([self.bzr, "commit", '--message="Initial commit"'], env=self.env, cwd=branch_dir)

        return self.latest_commit()

    def source_config(self, ref=None):
        config = {"kind": "bzr", "url": "file://" + self.repo, "track": "trunk"}
        if ref is not None:
            config["ref"] = ref

        return config

    def latest_commit(self):
        return subprocess.check_output(
            [self.bzr, "version-info", "--custom", "--template={revno}", os.path.join(self.repo, "trunk")],
            env=self.env,
            universal_newlines=True,
        ).strip()
