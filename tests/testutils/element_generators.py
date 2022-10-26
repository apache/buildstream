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

from buildstream import _yaml
from buildstream import utils
from buildstream._testing import create_repo


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
#    (Repo): A repo representing the sized element
#
def create_element_size(name, project_dir, elements_path, dependencies, size):
    full_elements_path = os.path.join(project_dir, elements_path)
    os.makedirs(full_elements_path, exist_ok=True)

    # Create a repo
    repodir = os.path.join(project_dir, "repos")
    repo = create_repo("tar", repodir, subdir=name)

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
