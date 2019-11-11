import os
import zipfile

from buildstream.utils import sha256sum

from buildstream.testing import Repo


class Zip(Repo):
    def create(self, directory):
        archive = os.path.join(self.repo, "file.zip")

        old_dir = os.getcwd()
        os.chdir(directory)
        with zipfile.ZipFile(archive, "w") as zipfp:
            for root, dirs, files in os.walk("."):
                names = dirs + files
                names = [os.path.join(root, name) for name in names]

                for name in names:
                    zipfp.write(name)

        os.chdir(old_dir)

        return sha256sum(archive)

    def source_config(self, ref=None):
        archive = os.path.join(self.repo, "file.zip")
        config = {"kind": "zip", "url": "file://" + archive, "directory": "", "base-dir": ""}
        if ref is not None:
            config["ref"] = ref

        return config
