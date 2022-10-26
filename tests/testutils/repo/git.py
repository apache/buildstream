#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import os
import shutil
import subprocess

import pytest

from buildstream._testing import Repo
from buildstream._testing._utils.site import GIT, GIT_ENV, HAVE_GIT


class Git(Repo):
    def __init__(self, directory, subdir="repo"):
        if not HAVE_GIT:
            pytest.skip("git is not available")

        self.submodules = {}

        super().__init__(directory, subdir)

        self.env = os.environ.copy()
        self.env.update(GIT_ENV)

    def _run_git(self, *args, **kwargs):
        argv = [GIT]
        argv.extend(args)
        if "env" not in kwargs:
            kwargs["env"] = dict(self.env, PWD=self.repo)
        kwargs.setdefault("cwd", self.repo)
        kwargs.setdefault("check", True)
        return subprocess.run(argv, **kwargs)  # pylint: disable=subprocess-run-check

    def create(self, directory):
        self.copy_directory(directory, self.repo)
        self._run_git("init", ".")
        self._run_git("checkout", "-b", "master")
        self._run_git("add", ".")
        self._run_git("commit", "-m", "Initial commit")
        return self.latest_commit()

    def add_tag(self, tag):
        self._run_git("tag", tag)

    def add_annotated_tag(self, tag, message):
        self._run_git("tag", "-a", tag, "-m", message)

    def add_commit(self):
        self._run_git("commit", "--allow-empty", "-m", "Additional commit")
        return self.latest_commit()

    def add_file(self, filename):
        shutil.copy(filename, self.repo)
        self._run_git("add", os.path.basename(filename))
        self._run_git("commit", "-m", "Added {}".format(os.path.basename(filename)))
        return self.latest_commit()

    def modify_file(self, new_file, path):
        shutil.copy(new_file, os.path.join(self.repo, path))
        self._run_git("commit", path, "-m", "Modified {}".format(os.path.basename(path)))
        return self.latest_commit()

    def add_submodule(self, subdir, url=None, checkout=None):
        submodule = {}
        if checkout is not None:
            submodule["checkout"] = checkout
        if url is not None:
            submodule["url"] = url
        self.submodules[subdir] = submodule
        self._run_git("submodule", "add", url, subdir)
        self._run_git("commit", "-m", "Added the submodule")
        return self.latest_commit()

    # This can also be used to a file or a submodule
    def remove_path(self, path):
        self._run_git("rm", path)
        self._run_git("commit", "-m", "Removing {}".format(path))
        return self.latest_commit()

    def source_config(self, ref=None):
        return self.source_config_extra(ref)

    def source_config_extra(self, ref=None, checkout_submodules=None):
        config = {"kind": "git", "url": "file://" + self.repo, "track": "master"}
        if ref is not None:
            config["ref"] = ref
        if checkout_submodules is not None:
            config["checkout-submodules"] = checkout_submodules

        if self.submodules:
            config["submodules"] = dict(self.submodules)

        return config

    def latest_commit(self):
        return self._run_git(
            "rev-parse",
            "HEAD",
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.strip()

    def branch(self, branch_name):
        self._run_git("checkout", "-b", branch_name)

    def delete_tag(self, tag_name):
        self._run_git("tag", "-d", tag_name)

    def checkout(self, commit):
        self._run_git("checkout", commit)

    def merge(self, commit):
        self._run_git("merge", "-m", "Merge", commit)
        return self.latest_commit()

    def rev_parse(self, rev):
        return self._run_git(
            "rev-parse",
            rev,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.strip()
