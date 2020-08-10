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

from typing import TYPE_CHECKING

from . import Element
from . import _cachekey
from ._exceptions import ArtifactElementError
from ._loader import LoadElement
from .node import Node
from .types import Scope

if TYPE_CHECKING:
    from typing import Dict


# ArtifactElement()
#
# Object to be used for directly processing an artifact
#
# Args:
#    context (Context): The Context object
#    ref (str): The artifact ref
#
class ArtifactElement(Element):

    # A hash of ArtifactElement by ref
    __instantiated_artifacts = {}  # type: Dict[str, ArtifactElement]

    def __init__(self, context, ref):
        _, element, key = verify_artifact_ref(ref)

        self._ref = ref
        self._key = key

        project = context.get_toplevel_project()
        load_element = LoadElement(Node.from_dict({}), element, project.loader)  # NOTE element has no .bst suffix

        super().__init__(context, project, load_element, None)

    # _new_from_artifact_ref():
    #
    # Recursively instantiate a new ArtifactElement instance, and its
    # dependencies from an artifact ref
    #
    # Args:
    #    ref (String): The artifact ref
    #    context (Context): The Context object
    #    task (Task): A task object to report progress to
    #
    # Returns:
    #    (ArtifactElement): A newly created Element instance
    #
    @classmethod
    def _new_from_artifact_ref(cls, ref, context, task=None):

        if ref in cls.__instantiated_artifacts:
            return cls.__instantiated_artifacts[ref]

        artifact_element = ArtifactElement(context, ref)
        # XXX: We need to call initialize_state as it is responsible for
        # initialising an Element/ArtifactElement's Artifact (__artifact)
        artifact_element._initialize_state()
        cls.__instantiated_artifacts[ref] = artifact_element

        for dep_ref in artifact_element.get_dependency_refs(Scope.BUILD):
            dependency = ArtifactElement._new_from_artifact_ref(dep_ref, context, task)
            artifact_element._add_build_dependency(dependency)

        return artifact_element

    # _clear_artifact_refs_cache()
    #
    # Clear the internal artifact refs cache
    #
    # When loading ArtifactElements from artifact refs, we cache already
    # instantiated ArtifactElements in order to not have to load the same
    # ArtifactElements twice. This clears the cache.
    #
    # It should be called whenever we are done loading all artifacts in order
    # to save memory.
    #
    @classmethod
    def _clear_artifact_refs_cache(cls):
        cls.__instantiated_artifacts = {}

    # Override Element.get_artifact_name()
    def get_artifact_name(self, key=None):
        return self._ref

    # Dummy configure method
    def configure(self, node):
        pass

    # Dummy preflight method
    def preflight(self):
        pass

    # get_dependency_refs()
    #
    # Obtain the refs of a particular scope of dependencies
    #
    # Args:
    #   scope (Scope): The scope of dependencies for which we want to obtain the refs
    #
    # Returns:
    #   (list [str]): A list of artifact refs
    #
    def get_dependency_refs(self, scope=Scope.BUILD):
        artifact = self._get_artifact()
        return artifact.get_dependency_refs(deps=scope)

    # configure_sandbox()
    #
    # Configure a sandbox for installing artifacts into
    #
    # Args:
    #    sandbox (Sandbox)
    #
    def configure_sandbox(self, sandbox):
        install_root = self.get_variable("install-root")

        # Tell the sandbox to mount the build root and install root
        sandbox.mark_directory(install_root)

        # Tell sandbox which directory is preserved in the finished artifact
        sandbox.set_output_directory(install_root)

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
        project, element, key = ref.split("/", 2)  # This will raise a Value error if unable to split
        # Explicitly raise a ValueError if the key length is not as expected
        if not _cachekey.is_key(key):
            raise ValueError
    except ValueError:
        raise ArtifactElementError("Artifact: {} is not of the expected format".format(ref))

    return project, element, key
