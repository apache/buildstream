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
#        Chandan Singh <csingh43@bloomberg.net>
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

"""
patch - apply locally stored patches
====================================

**Host dependencies:**

  * patch

**Usage:**

.. code:: yaml

   # Specify the local source kind
   kind: patch

   # Specify the project relative path to a patch file
   path: files/somefile.diff

   # Optionally specify the strip level, defaults to 1
   strip-level: 1


See `built-in functionality doumentation
<https://docs.buildstream.build/master/buildstream.source.html#core-source-builtins>`_ for
details on common configuration options for sources.
"""

import os
from buildstream import Source, SourceError
from buildstream import utils


class PatchSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    BST_REQUIRES_PREVIOUS_SOURCES_STAGE = True

    def configure(self, node):
        node.validate_keys(["path", "strip-level", *Source.COMMON_CONFIG_KEYS])
        self.path = self.node_get_project_path(node.get_scalar("path"), check_is_file=True)
        self.strip_level = node.get_int("strip-level", default=1)
        self.fullpath = os.path.join(self.get_project_directory(), self.path)

    def preflight(self):
        # Check if patch is installed, get the binary at the same time
        self.host_patch = utils.get_host_tool("patch")

    def get_unique_key(self):
        return [self.path, utils.sha256sum(self.fullpath), self.strip_level]

    def is_resolved(self):
        return True

    def is_cached(self):
        return True

    def load_ref(self, node):
        pass

    def get_ref(self):
        return None  # pragma: nocover

    def set_ref(self, ref, node):
        pass  # pragma: nocover

    def fetch(self):  # pylint: disable=arguments-differ
        # Nothing to do here for a local source
        pass  # pragma: nocover

    def stage(self, directory):
        with self.timed_activity("Applying local patch: {}".format(self.path)):

            # Bail out with a comprehensive message if the target directory is empty
            if not os.listdir(directory):
                raise SourceError(
                    "Nothing to patch in directory '{}'".format(directory),
                    reason="patch-no-files",
                )

            strip_level_option = "-p{}".format(self.strip_level)
            self.call(
                [
                    self.host_patch,
                    strip_level_option,
                    "-i",
                    self.fullpath,
                    "-d",
                    directory,
                ],
                fail="Failed to apply patch {}".format(self.path),
            )


# Plugin entry point
def setup():
    return PatchSource
