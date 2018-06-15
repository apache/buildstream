.. _examples_alpine_autotools:

Alpine Demo
===========
This is a simple example using Buildstream to build a sandbox from a tarball containing a minimal
`Alpine <https://alpinelinux.org/>`_ image as the base runtime. The example will use autotools to
build the hello world example from `automake
<https://www.gnu.org/software/automake/manual/automake.html#Hello-World>`_
and install it in the sandbox.

.. note::

    This example is distributed with Buildstream in the
    `doc/examples/alpine-demo
    <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/alpine-demo>`_
    subdirectory.

Project structure
-----------------

project.conf
~~~~~~~~~~~~
Bellow is a basic :ref:`project <projectconf>` definition:

..  literalinclude:: ../../examples/alpine-autotools/project.conf
    :language: yaml

This specifies the name of the project, and the location where the project's
elements are stored.

For convenience, aliases are defined for Automake and Alpine Linux source
locations.

base.bst
~~~~~~~~
This is the :mod:`import <elements.import>` element used to provide the sandbox
runtime for this project. As a :mod:`tar <sources.tar>` element, it imports a source tarball found at the given url. This
tarball will be automatically extracted into the root directory of the project's sandbox. In general, the extraction location of a tar source can be specified with the base-dir attribute.

..  literalinclude:: ../../examples/alpine-autotools/elements/base.bst
    :language: yaml

amhello.bst
~~~~~~~~~~~
This :mod:`autotools <elements.autotools>` element is the hello world example from
GNU autotools.

..  literalinclude:: ../../examples/alpine-autotools/elements/amhello.bst
    :language: yaml

The command-subdir variable specifies the working directory in the sandbox for
this element.

Using the project
-----------------
The instructions here assume you are in the alpine-demo root directory (the
directory containing project.conf).

Running *bst show* will show the pipeline that needs to be built in order to use the amhello.bst
element. This includes the element's dependencies, in this case only base.bst.

.. raw:: html
    :file: ../sessions/alpine-autotools-show.html

To build this pipeline, use the `bst build` command. For the purpose of this
example, we will :ref:`track <invoking_track>` all the elements in the pipeline this tells buildstream to use the most recent reference for each element

.. raw:: html
    :file: ../sessions/alpine-autotools-build.html

After building, it is now possible to :ref:`shell <invoking_shell>` into the sandbox with
the *bst shell* command. The hello world example will be installed in the sandbox.

.. raw:: html
    :file: ../sessions/alpine-autotools-shell.html

Running *bst show* again will show that both base.bst and amhello.bst have been cached with associated
:ref:`keys <cachekeys>`. Running `bst build` again will only rebuild cached elements
if the key generated from the current state of an element does not match the
cached key.
