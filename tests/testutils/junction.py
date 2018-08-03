import os
from tests.testutils import create_repo
from buildstream import _yaml


# generate_junction()
#
# Generates a junction element with a git repository
#
# Args:
#    tmpdir: The tmpdir fixture, for storing the generated git repo
#    subproject_path: The path for the subproject, to add to the git repo
#    junction_path: The location to store the generated junction element
#    store_ref: Whether to store the ref in the junction.bst file
#
# Returns:
#    (str): The ref
#
def generate_junction(tmpdir, subproject_path, junction_path, *, store_ref=True):
    # Create a repo to hold the subproject and generate
    # a junction element for it
    #
    repo = create_repo('git', str(tmpdir))
    source_ref = ref = repo.create(subproject_path)
    if not store_ref:
        source_ref = None

    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=source_ref)
        ]
    }
    _yaml.dump(element, junction_path)

    return ref
