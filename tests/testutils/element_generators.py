import os

from buildstream import _yaml


# create_element_size()
#
# This will open a "<name>_data" file for writing and write
# <size> MB of urandom (/dev/urandom) "stuff" into the file.
# A bst import element file is then created: <name>.bst
#
# Args:
#  name: (str) of the element name (e.g. target.bst)
#  path: (str) pathway to the project/elements directory
#  dependencies: A list of strings (can also be an empty list)
#  size: (int) size of the element in bytes
#
# Returns:
#  Nothing (creates a .bst file of specified size)
#
def create_element_size(name, project_dir, elements_path, dependencies, size):
    full_elements_path = os.path.join(project_dir, elements_path)
    os.makedirs(full_elements_path, exist_ok=True)

    # Create a file to be included in this element's artifact
    with open(os.path.join(project_dir, name + '_data'), 'wb+') as f:
        f.write(os.urandom(size))

    # Simplest case: We want this file (of specified size) to just
    # be an import element.
    element = {
        'kind': 'import',
        'sources': [
            {
                'kind': 'local',
                'path': name + '_data'
            }
        ],
        'depends': dependencies
    }
    _yaml.dump(element, os.path.join(project_dir, elements_path, name))
