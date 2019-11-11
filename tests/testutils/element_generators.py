import os

from buildstream import _yaml
from buildstream import utils
from buildstream.testing import create_repo


# create_element_size()
#
# Creates an import element with a git repo, using random
# data to create a file in that repo of the specified size,
# such that building it will add an artifact of the specified
# size to the artifact cache.
#
# Args:
#    name: (str) of the element name (e.g. target.bst)
#    project_dir (str): The path to the project
#    element_path (str): The element path within the project
#    dependencies: A list of strings (can also be an empty list)
#    size: (int) size of the element in bytes
#
# Returns:
#    (Repo): A git repo which can be used to introduce trackable changes
#            by using the update_element_size() function below.
#
def create_element_size(name, project_dir, elements_path, dependencies, size):
    full_elements_path = os.path.join(project_dir, elements_path)
    os.makedirs(full_elements_path, exist_ok=True)

    # Create a git repo
    repodir = os.path.join(project_dir, "repos")
    repo = create_repo("git", repodir, subdir=name)

    with utils._tempdir(dir=project_dir) as tmp:

        # We use a data/ subdir in the git repo we create,
        # and we set the import element to only extract that
        # part; this ensures we never include a .git/ directory
        # in the cached artifacts for these sized elements.
        #
        datadir = os.path.join(tmp, "data")
        os.makedirs(datadir)

        # Use /dev/urandom to create the sized file in the datadir
        with open(os.path.join(datadir, name), "wb+") as f:
            f.write(os.urandom(size))

        # Create the git repo from the temp directory
        ref = repo.create(tmp)

    element = {
        "kind": "import",
        "sources": [repo.source_config(ref=ref)],
        "config": {
            # Extract only the data directory
            "source": "data"
        },
        "depends": dependencies,
    }
    _yaml.roundtrip_dump(element, os.path.join(project_dir, elements_path, name))

    # Return the repo, so that it can later be used to add commits
    return repo


# update_element_size()
#
# Updates a repo returned by create_element_size() such that
# the newly added commit is completely changed, and has the newly
# specified size.
#
# The name and project_dir arguments must match the arguments
# previously given to create_element_size()
#
# Args:
#    name: (str) of the element name (e.g. target.bst)
#    project_dir (str): The path to the project
#    repo: (Repo) The Repo returned by create_element_size()
#    size: (int) The new size which the element generates, in bytes
#
# Returns:
#    (Repo): A git repo which can be used to introduce trackable changes
#            by using the update_element_size() function below.
#
def update_element_size(name, project_dir, repo, size):

    with utils._tempdir(dir=project_dir) as tmp:

        new_file = os.path.join(tmp, name)

        # Use /dev/urandom to create the sized file in the datadir
        with open(new_file, "wb+") as f:
            f.write(os.urandom(size))

        # Modify the git repo with a new commit to the same path,
        # replacing the original file with a new one.
        repo.modify_file(new_file, os.path.join("data", name))
