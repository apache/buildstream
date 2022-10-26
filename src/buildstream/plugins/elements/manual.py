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

"""
manual - Manual build element
=============================
The most basic build element does nothing but allows users to
add custom build commands to the array understood by the :mod:`BuildElement <buildstream.buildelement>`

The empty configuration is as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/manual.yaml
     :language: yaml

See :ref:`built-in functionality documentation <core_buildelement_builtins>` for
details on common configuration options for build elements.
"""

from buildstream import BuildElement


# Element implementation for the 'manual' kind.
class ManualElement(BuildElement):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"


# Plugin entry point
def setup():
    return ManualElement
