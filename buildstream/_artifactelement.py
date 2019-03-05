#
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
#
#  Authors:
#        James Ennis <james.ennis@codethink.co.uk>
from . import Element
from . import _cachekey
from ._exceptions import ArtifactElementError
from ._loader.metaelement import MetaElement


# ArtifactElement()
#
# Object to be used for directly processing an artifact
#
# Args:
#    context (Context): The Context object
#    ref (str): The artifact ref
#
class ArtifactElement(Element):
    def __init__(self, context, ref):
        _, element, key = verify_artifact_ref(ref)

        self._ref = ref
        self._key = key

        project = context.get_toplevel_project()
        meta = MetaElement(project, element)  # NOTE element has no .bst suffix
        plugin_conf = None

        super().__init__(context, project, meta, plugin_conf)

    # Override Element.get_artifact_name()
    def get_artifact_name(self, key=None):
        return self._ref

    # Dummy configure method
    def configure(self, node):
        pass

    # Dummy preflight method
    def preflight(self):
        pass

    # Override Element._calculate_cache_key
    def _calculate_cache_key(self, dependencies=None):
        return self._key

    # Override Element._get_cache_key()
    def _get_cache_key(self, strength=None):
        return self._key


# verify_artifact_ref()
#
# Verify that a ref string matches the format of an artifact
#
# Args:
#    ref (str): The artifact ref
#
# Returns:
#    project (str): The project's name
#    element (str): The element's name
#    key (str): The cache key
#
# Raises:
#    ArtifactElementError if the ref string does not match
#    the expected format
#
def verify_artifact_ref(ref):
    try:
        project, element, key = ref.split('/', 2)  # This will raise a Value error if unable to split
        # Explicitly raise a ValueError if the key lenght is not as expected
        if len(key) != len(_cachekey.generate_key({})):
            raise ValueError
    except ValueError:
        raise ArtifactElementError("Artifact: {} is not of the expected format".format(ref))

    return project, element, key
