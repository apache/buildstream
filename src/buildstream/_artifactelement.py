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
#  Authors:
#        James Ennis <james.ennis@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

from typing import TYPE_CHECKING, Optional, Dict
from contextlib import suppress

from . import Element
from . import _cachekey
from ._artifactproject import ArtifactProject
from ._exceptions import ArtifactElementError
from ._loader import LoadElement
from .node import Node

if TYPE_CHECKING:
    from ._context import Context
    from ._state import Task


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
    __instantiated_artifacts: Dict[str, "ArtifactElement"] = {}

    def __init__(self, context, ref):
        project_name, element_name, key = verify_artifact_ref(ref)

        project = ArtifactProject(project_name, context)
        load_element = LoadElement(Node.from_dict({}), element_name, project.loader)  # NOTE element has no .bst suffix

        super().__init__(context, project, load_element, None, artifact_key=key)

    ########################################################
    #                      Public API                      #
    ########################################################

    # new_from_artifact_name():
    #
    # Recursively instantiate a new ArtifactElement instance, and its
    # dependencies from an artifact name
    #
    # Args:
    #    artifact_name: The artifact name
    #    context: The Context object
    #    task: A task object to report progress to
    #
    # Returns:
    #    (ArtifactElement): A newly created Element instance
    #
    @classmethod
    def new_from_artifact_name(cls, artifact_name: str, context: "Context", task: Optional["Task"] = None):

        # Initial lookup for already loaded artifact.
        with suppress(KeyError):
            return cls.__instantiated_artifacts[artifact_name]

        # Instantiate the element, this can result in having a different
        # artifact name, if we loaded the artifact by it's weak key then
        # we will have the artifact loaded via it's strong key.
        element = ArtifactElement(context, artifact_name)
        artifact_name = element.get_artifact_name()

        # Perform a second lookup, avoid loading the same artifact
        # twice, even if we've loaded it both with weak and strong keys.
        with suppress(KeyError):
            return cls.__instantiated_artifacts[artifact_name]

        # Now cache the loaded artifact
        cls.__instantiated_artifacts[artifact_name] = element

        # Walk the dependencies and load recursively
        artifact = element._get_artifact()
        for dep_artifact_name in artifact.get_dependency_artifact_names():
            dependency = ArtifactElement.new_from_artifact_name(dep_artifact_name, context, task)
            element._add_build_dependency(dependency)

        return element

    # clear_artifact_name_cache()
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
    def clear_artifact_name_cache(cls):
        cls.__instantiated_artifacts = {}

    ########################################################
    #         Override internal Element methods            #
    ########################################################

    def _load_artifact(self, *, pull, strict=None):  # pylint: disable=useless-super-delegation
        # Always operate in strict mode as artifact key has been specified explicitly.
        return super()._load_artifact(pull=pull, strict=True)

    # Once we've finished loading an artifact, we assume the
    # state of the loaded artifact. This is also used if the
    # artifact is loaded after pulling.
    #
    def _load_artifact_done(self):
        self._mimic_artifact()
        super()._load_artifact_done()

    ########################################################
    #         Implement Element abstract methods           #
    ########################################################
    def configure(self, node):
        pass

    def preflight(self):
        pass

    def configure_sandbox(self, sandbox):
        install_root = self.get_variable("install-root")

        # Tell the sandbox to mount the build root and install root
        sandbox.mark_directory(install_root)


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
