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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""
script - Run scripts to create output
=====================================
This element allows one to run some commands to mutate the
input and create some output.

.. note::

   Script elements may only specify build dependencies. See
   :ref:`the format documentation <format_dependencies>` for more
   detail on specifying dependencies.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/script.yaml
     :language: yaml
"""

import buildstream


# Element implementation for the 'script' kind.
class ScriptElement(buildstream.ScriptElement):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        node.validate_keys(["commands", "root-read-only"])

        self.add_commands("commands", node.get_str_list("commands"))
        self.set_work_dir()
        self.set_install_root()
        self.set_root_read_only(node.get_bool("root-read-only", default=False))

    def configure_dependencies(self, dependencies):
        for dep in dependencies:

            # Determine the location to stage each element, default is "/"
            location = "/"
            if dep.config:
                dep.config.validate_keys(["location"])
                location = dep.config.get_str("location", location)

            # Add each element to the layout
            self.layout_add(dep.element, dep.path, location)


# Plugin entry point
def setup():
    return ScriptElement
