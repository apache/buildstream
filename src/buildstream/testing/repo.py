#
#  Copyright (C) 2016-2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.

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
        """ Copies the content of src to the directory dest

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
