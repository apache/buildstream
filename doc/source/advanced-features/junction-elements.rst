

.. _junction_elements:

Junction elements
=================
BuildStream's junction elements are used to import other BuildStream
projects. This allows you to depend on elements that are part of an
upstream project.


A simple example
----------------

.. note::

    This example is distributed with BuildStream in the
    `doc/examples/junctions <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/junctions>`_
    subdirectory.

Below is a simple example of bst file for a junction element:

.. literalinclude:: ../../examples/junctions/elements/hello-junction.bst
    :language: yaml

This element imports the autotools example subproject found in the
BuildStream doc/examples/junctions/autotools subdirectory.

.. note::

    While for this example we're using a local source, another common use-case,
    for junction elements is including a remote, version contolled project,
    having a source type such as `-kind: git`.

The below bst file describes an element which depends on the hello.bst element
from the autotools example:

.. literalinclude:: ../../examples/junctions/elements/callHello.bst
    :language: yaml

This element consists of a script which calls hello.bst's hello command.

Building callHello.bst,

.. raw:: html
   :file: ../sessions/junctions-build.html

You can see that the hello.bst element and its dependencies from the autotools
project have been build as part of the pipeline for callHello.bst.

We can now invoke `bst shell`

.. raw:: html
   :file: ../sessions/junctions-shell.html

This runs the script files/callHello.sh which will makes use of the hello command from the hello.bst element in the autotools project.


Cross-junction workspaces
-------------------------
You can open workspaces for elements in the project refered to by the junction
using the syntax `bst open ${junction-name}:{element-name}`. In this example,

.. raw:: html
   :file: ../sessions/junctions-workspace-open.html

This has opened a workspace for the hello.bst element from the autotools project.
This workspace can now be used as normal.


Further reading
---------------
For an example of junction elements being used in a real project, take a look
at the `freedesktop-sdk junction
<https://gitlab.gnome.org/GNOME/gnome-build-meta/blob/master/elements/freedesktop-sdk.bst>`_
in the `gnome-build-meta <https://gitlab.gnome.org/GNOME/gnome-build-meta>`_ project.
