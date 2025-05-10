..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.



.. _junction_elements:

Junction elements
=================
BuildStream's :mod:`junction <elements.junction>` elements are the mechanism which
allow projects to interact and depend on eachother.

Junction elements represent the BuildStream project you are depending, and behave
much like other elements in the sense that they can be :ref:`fetched <invoking_source_fetch>`
and :ref:`tracked <invoking_source_track>` like other elements, except that regular
elements cannot *depend* on junctions directly, nor can junctions be :ref:`built <invoking_build>`.
Instead, junctions act like a window into another project you depend on, and allow
elements of your project to depend on elements exposed by the project referenced by
the junction.

Projects which are junctioned by your project are referred to as *subprojects*.


A simple example
----------------

.. note::

    This example is distributed with BuildStream in the
    `doc/examples/junctions <https://github.com/apache/buildstream/tree/master/doc/examples/junctions>`_
    subdirectory.

Below is a simple example of bst file for the junction element, which
we have called ``hello-junction.bst`` in this project:

.. literalinclude:: ../../examples/junctions/elements/hello-junction.bst
    :language: yaml

This element imports the autotools example subproject distributed with BuildStream
in the `doc/examples/junctions/autotools <https://github.com/apache/buildstream/tree/master/doc/examples/junctions/autotools>`_
subdirectory.

.. note::

    For the sake of this example we are using a local source in a subdirectory
    of the example project.

    Since junctions allow interoperability of projects, it would be more common
    to use a junction to a remote project under separate revision control, possibly
    using a ``kind: git`` source.

The below bst file describes the element ``callHello.bst``, which depends on the
``hello.bst`` element from the autotools example:

.. literalinclude:: ../../examples/junctions/elements/callHello.bst
    :language: yaml

Note how this element refers to the previously declared ``hello-junction.bst``
junction in its :ref:`dependency dictionary <format_dependencies>`. This dependency
expresses that we are depending on the ``hello.bst`` element in the project
which ``hello-junction.bst`` refers to.

The ``callHello.bst`` element simply imports a ``callHello.sh`` shell script which
calls the hello command provided by ``hello.bst``:

.. literalinclude:: ../../examples/junctions/files/callHello.sh
    :language: shell


Building and running
--------------------
Building the ``callHello.bst`` element which requires an external project
is just a matter of invoking :ref:`bst build <invoking_build>` in the
regular way:

.. raw:: html
   :file: ../sessions/junctions-build.html

You can see that the hello.bst element and its dependencies from the autotools
project have been built as a part of the pipeline for callHello.bst.

We can now invoke :ref:`bst shell <invoking_shell>` and run our ``callHello.sh``
script, which in turn also calls the ``hello`` program installed by the
subproject's ``hello.bst`` element.

.. raw:: html
   :file: ../sessions/junctions-shell.html


Further reading
---------------
For an example of junction elements being used in a real project, take a look
at the `freedesktop-sdk junction
<https://gitlab.gnome.org/GNOME/gnome-build-meta/blob/master/elements/freedesktop-sdk.bst>`_
in the `gnome-build-meta <https://gitlab.gnome.org/GNOME/gnome-build-meta>`_ project.
