from buildstream import _yaml


# yaml_file_get_provenance()
#
# Load a yaml file and return it's _yaml.Provenance object.
#
# This is useful for checking the provenance in BuildStream output is as
# expected.
#
# Args:
#   path (str): The path to the file to be loaded
#   shortname (str): How the path should appear in the error
#   key (str): Optional key to look up in the loaded file
#   indices (list of indexes): Optional index path, in the case of list values
#
# Returns:
#   The Provenance of the dict, member or list element
#
def yaml_file_get_provenance(path, shortname, key=None, indices=None):
    with open(path) as data:
        element_yaml = _yaml.load_data(
            data,
            _yaml.ProvenanceFile(path, shortname, project=None),
        )
    provenance = _yaml.node_get_provenance(element_yaml, key, indices)
    assert provenance is not None
    return provenance
