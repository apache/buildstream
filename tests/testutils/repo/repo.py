import os
import shutil


# Repo()
#
# Abstract class providing scaffolding for
# generating data to be used with various sources
#
# Args:
#    directory (str): The base temp directory for the test
#    subdir (str): The subdir for the repo, in case there is more than one
#
class Repo():

    def __init__(self, directory, subdir='repo'):

        # The working directory for the repo object
        #
        self.directory = os.path.abspath(directory)

        # The directory the actual repo will be stored in
        self.repo = os.path.join(self.directory, subdir)

        os.makedirs(self.repo)

    # create():
    #
    # Create a repository in self.directory and add the initial content
    #
    # Args:
    #    directory: A directory with content to commit
    #
    # Returns:
    #    (smth): A new ref corresponding to this commit, which can
    #            be passed as the ref in the Repo.source_config() API.
    #
    def create(self, directory):
        pass

    # source_config()
    #
    # Args:
    #    ref (smth): An optional abstract ref object, usually a string.
    #
    # Returns:
    #    (dict): A configuration which can be serialized as a
    #            source when generating an element file on the fly
    #
    def source_config(self, ref=None):
        pass

    # copy_directory():
    #
    # Copies the content of src to the directory dest
    #
    # Like shutil.copytree(), except dest is expected
    # to exist.
    #
    # Args:
    #    src (str): The source directory
    #    dest (str): The destination directory
    #
    def copy_directory(self, src, dest):
        for filename in os.listdir(src):
            src_path = os.path.join(src, filename)
            dest_path = os.path.join(dest, filename)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)
