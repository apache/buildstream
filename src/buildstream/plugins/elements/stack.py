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
stack - Symbolic Element for dependency grouping
================================================
Stack elements are simply a symbolic element used for representing
a logical group of elements.

All dependencies declared in stack elements must always be both
:ref:`build and runtime dependencies <format_dependencies_types>`.

**Example:**

.. code:: yaml

   kind: stack

   # Declare all of your dependencies in the `depends` list.
   depends:
   - libc.bst
   - coreutils.bst

.. note::

   Unlike other elements, whose cache keys are a unique identifier
   of the contents of the artifacts they produce, stack elements do
   not produce any artifact content. Instead, the cache key of an artifact
   is a unique identifier for the assembly of its own dependencies.


Using intermediate stacks
-------------------------
Using a stack element at intermediate levels of your build graph
allows you to abstract away some parts of your project into logical
subsystems which elements can more conveniently depend on as a whole.

In addition to the added convenience, it will allow you to more
easily change the implementation of a subsystem later on, without needing
to update many reverse dependencies to depend on new elements, or even
allow you to conditionally implement a subsystem with various implementations
depending on what :ref:`project options <project_options>` were specified at
build time.


Using toplevel stacks
---------------------
Stack elements can also be useful as toplevel targets in your build graph
to simply indicate all of the components which need to be built for a given
system to be complete, or for your integration pipeline to be successful.


Checking out and deploying toplevel stacks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In case that your software is built remotely, it is possible to checkout
the built content of a stack on your own machine for the purposes of
inspection or further deployment.

To accomplish this, you will need to know the cache key of the stack element
which was built remotely, possibly by inspecting the remote build log or by
deriving it with an equally configured BuildStream project, and you will
need read access to the artifact cache server which the build was uploaded to,
this should be configured in your :ref:`user configuration file <config_artifact_caches>`.

You can then checkout the remotely built stack using the
:ref:`bst artifact checkout <invoking_artifact_checkout>` command and providing
it with the :ref:`artifact name <artifact_names>`:

**Example:**

.. code:: shell

   bst artifact checkout --deps build --pull --integrate \\
       --directory `pwd`/checkout \\
       project/stack/788da21e7c1b5818b7e7b60f7eb75841057ff7e45d362cc223336c606fe47f27

.. note::

   It is possible to checkout other elements in the same way, however stack
   elements are uniquely suited to this purpose, as they cannot have
   :ref:`runtime only dependencies <format_dependencies_types>`, and consequently
   their cache keys are always a unique representation of their collective
   dependencies.
"""

from buildstream import Element, ElementError
from buildstream.types import _Scope


# Element implementation for the 'stack' kind.
class StackElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # This plugin does not produce any artifacts when built
    BST_ELEMENT_HAS_ARTIFACT = False

    # This element does not allow sources
    BST_FORBID_SOURCES = True

    # Stack elements do not run any commands
    BST_RUN_COMMANDS = False

    def configure(self, node):
        pass

    def preflight(self):

        # Assert that all dependencies are both build and runtime dependencies.
        #
        all_deps = list(self._dependencies(_Scope.ALL, recurse=False))
        run_deps = list(self._dependencies(_Scope.RUN, recurse=False))
        build_deps = list(self._dependencies(_Scope.BUILD, recurse=False))
        if any(dep not in run_deps for dep in all_deps) or any(dep not in build_deps for dep in all_deps):
            # There is no need to specify the `self` provenance here in preflight() errors, as the base class
            # will take care of prefixing these for plugin author convenience.
            raise ElementError(
                "All dependencies of 'stack' elements must be both build and runtime dependencies",
                detail="Make sure you declare all dependencies in the `depends` list, without specifying any `type`.",
                reason="stack-requires-build-and-run",
            )

    def get_unique_key(self):
        # We do not add anything to the build, only our dependencies
        # do, so our unique key is just a constant.
        return 1

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):

        # Just create a dummy empty artifact, its existence is a statement
        # that all this stack's dependencies are built.
        vrootdir = sandbox.get_virtual_directory()
        vrootdir.open_directory("output", create=True)

        # And we're done
        return "/output"


# Plugin entry point
def setup():
    return StackElement
