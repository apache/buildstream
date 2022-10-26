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

"""
Repo - Utility class for testing source plugins
===============================================


"""
import os
import shutil


class Repo:
    """Repo()

    Abstract class providing scaffolding for generating data to be
    used with various sources. Subclasses of Repo may be registered to
    run through the suite of generic source plugin tests provided in
    buildstream.testing.

    Args:
    directory (str): The base temp directory for the test
    subdir (str): The subdir for the repo, in case there is more than one

    """

    def __init__(self, directory, subdir="repo"):

        # The working directory for the repo object
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in
        self.repo = os.path.join(self.directory, subdir)

        os.makedirs(self.repo, exist_ok=True)

    def create(self, directory):
        """Create a repository in self.directory and add the initial content

        Args:
            directory: A directory with content to commit

        Returns:
            (smth): A new ref corresponding to this commit, which can
                    be passed as the ref in the Repo.source_config() API.
        """
        raise NotImplementedError("create method has not been implemeted")

    def source_config(self, ref=None):
        """
        Args:
            ref (smth): An optional abstract ref object, usually a string.

        Returns:
            (dict): A configuration which can be serialized as a
                    source when generating an element file on the fly

        """
        raise NotImplementedError("source_config method has not been implemeted")

    def copy_directory(self, src, dest):
        """Copies the content of src to the directory dest

        Like shutil.copytree(), except dest is expected
        to exist.

        Args:
            src (str): The source directory
            dest (str): The destination directory
        """
        for filename in os.listdir(src):
            src_path = os.path.join(src, filename)
            dest_path = os.path.join(dest, filename)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)

    def copy(self, dest):
        """Creates a copy of this repository in the specified destination.

        Args:
        dest (str): The destination directory

        Returns:
        (Repo): A Repo object for the new repository.
        """
        subdir = self.repo[len(self.directory) :].lstrip(os.sep)
        new_dir = os.path.join(dest, subdir)
        os.makedirs(new_dir, exist_ok=True)
        self.copy_directory(self.repo, new_dir)
        repo_type = type(self)
        new_repo = repo_type(dest, subdir)
        return new_repo
