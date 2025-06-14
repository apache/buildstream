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



.. _developing_strict_mode:

Strict mode
===========
In this section, we will cover the usage of :ref:`strict vs non-strict <user_config_strict_mode>`
build plans in conjunction with :ref:`workspaces <developing_workspaces>`, and how this
can help to improve your edit/compile/test cycles.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/strict-mode
   <https://github.com/apache/buildstream/tree/master/doc/examples/strict-mode>`_
   subdirectory.


Overview
--------
When working with BuildStream to create integrations, it is typical that you have a
lot of components to build, and you frequently need to modify a component
at various levels of the stack. When developing one or more applications, you might
want to open a workspace and fix a bug in an application, or you might need to
open a workspace on a low level shared library to fix the behavior of one or
more misbehaving applications.

By default, BuildStream will always choose to be deterministic in order to
produce the most correct build results as possible. As such, modifying a low
level library will result in rebuilding all of it's reverse dependencies, but
this can be very time consuming and inconvenient for your edit/compile/test
cycles.

This is when enabling :ref:`non-strict build plans <user_config_strict_mode>`
can be helpful.

To illustrate the facets of how this works, this example will present a project
consisting of an application which is linked both statically and dynamically
linked to a common library.


Project structure
-----------------
This project is mostly based on the :ref:`integration commands <tutorial_integration_commands>`
example, as such we will ignore large parts of this project and only focus
on the elements which are of specific interest.

To illustrate the relationship of these two applications and the library,
let's briefly take a look at the underlying Makefiles which are used in this
project, starting with the library and followed by both Makefiles used to
build the application.


``files/libhello/Makefile``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/strict-mode/files/libhello/Makefile
   :language: Makefile


``files/hello/Makefile.dynamic``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/strict-mode/files/hello/Makefile.dynamic
   :language: Makefile


``files/hello/Makefile.static``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/strict-mode/files/hello/Makefile.static
   :language: Makefile

As we can see, we have a library that is distributed both as the dynamic
library ``libhello.so`` and also as the static archive ``libhello.a``.

Now let's take a look at the two separate elements which build the
application, first the dynamically linked version and then the static one.


``elements/hello-dynamic.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/strict-mode/elements/hello-dynamic.bst
   :language: yaml

Nothing very special to observe about this hello program, just a
:mod:`manual <elements.manual>` element quite similar to the one we've
already seen in the :ref:`running commands <tutorial_running_commands>`
example.


``elements/hello-static.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/strict-mode/elements/hello-static.bst
   :language: yaml

Almost the same as the dynamic element, except here we have declared the
dependency to the ``libhello.bst`` element differently: this time we have enabled
the ``strict`` option in the :ref:`dependency declaration <format_dependencies>`.

The side effect of setting this option is that ``hello-static.bst`` will be
rebuilt any time that ``libhello.bst`` has changed, even when
:ref:`non-strict build plans <user_config_strict_mode>` have been enabled.

.. tip::

   Some element plugins are designed to consume the content of their
   dependencies entirely, and output an artifact without any transient
   runtime dependencies, an example of this is the :mod:`compose <elements.compose>`
   element.

   In cases such as :mod:`compose <elements.compose>`, it is not necessary to
   explicitly annotate their dependencies as ``strict``.

   It is only helpful to set the ``strict`` attribute on a
   :ref:`dependency declaration <format_dependencies>` in the case that the
   specific dependency relationship causes data to be consumed verbatim,
   as is the case with static linking.


Using the project
-----------------
For the sake of brevity, let's assume that you've already built all of the
elements of this project, and that you want to make some changes to the
``libhello.bst`` element, and test how it might effect the hello program.


Everything is already built
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. raw:: html
   :file: ../sessions/strict-mode-show-initial.html


Open a workspace and modify libhello.c
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Now let's open up a workspace on the hello library

.. raw:: html
   :file: ../sessions/strict-mode-workspace-open.html

And go ahead and make a modification like this:

.. literalinclude:: ../../examples/strict-mode/update.patch
    :language: diff


Observing ``hello-dynamic.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Let's take a look at the :ref:`bst show <invoking_show>` output for
the dynamically linked ``hello-dynamic.bst`` element.

.. raw:: html
   :file: ../sessions/strict-mode-show-dynamic-strict.html

As one might expect, the ``libhello.bst`` element is ready to be built
after having been modified, and the ``hello-dynamic.bst`` element is
waiting for ``libhello.bst`` to be built before it can build.

Now let's take a look at the same elements if we pass the ``--no-strict``
option to ``bst``:

.. raw:: html
   :file: ../sessions/strict-mode-show-dynamic-no-strict.html

Note that this time, the ``libhello.bst`` still needs to be built,
but the ``hello-dymamic.bst`` element is showing up as ``cached``.

.. tip::

   The :ref:`bst show <invoking_show>` output will show some cache
   keys dimmed out in the case that they are not entirely deterministic.

   Here we can see that ``hello-dynamic.bst`` is dimmed out because
   it will not be rebuilt against the changed ``libhello.bst`` element,
   and it also has a different cache key because of this.


Observing ``hello-static.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Now let's observe the ``hello-static.bst`` element with strict mode
disabled:

.. raw:: html
   :file: ../sessions/strict-mode-show-static-no-strict.html

Note that in this case the ``hello-strict.bst`` is going to be
rebuilt even in strict mode. This is because we annotated the
declaration of the ``libhello.bst`` dependency with the ``strict``
attribute.

We did this because ``hello-strict.bst`` consumes the input of
``libhello.bst`` verbatim, by way of statically linking to it, instead
of merely being affected by the content of ``libhello.bst`` at runtime,
as would be the case of static linking.


Building and running ``hello-dynamic.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Now let's build ``hello-dynamic.bst`` with strict mode disabled.

.. raw:: html
   :file: ../sessions/strict-mode-build-dynamic-no-strict.html

Note that the :ref:`bst build <invoking_build>` command completed without
having to build ``hello-dynamic.bst`` at all.

And now we can also run ``hello-dynamic.bst``

.. raw:: html
   :file: ../sessions/strict-mode-run-dynamic-no-strict.html

When running ``hello-dynamic.bst`` with no-strict mode, we are
actually reusing the old build of ``hello-dynamic.bst`` staged against
the new build of the modified ``libhello.bst`` element.


Building and running ``hello-static.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Finally, if we build ``hello-static.bst`` with strict mode disabled,
we can see that it will be rebuilt regardless of strict mode being
enabled.

.. raw:: html
   :file: ../sessions/strict-mode-build-static-no-strict.html

This is of course because we declared its dependency on ``libhello.bst``
as a ``strict`` dependency.

And by the same virtue, we can see that when we run the example
it has properly relinked against the changed static archive, and
has the updated text in the greeting:

.. raw:: html
   :file: ../sessions/strict-mode-run-static-no-strict.html


Summary
-------
In this chapter we've explored how to use :ref:`non-strict build plans <user_config_strict_mode>`
in order to avoid rebuilding reverse dependencies of a lower level
element you might be working with in a :ref:`workspace <invoking_workspace_open>`,
consequently improving your edit/compile/test experience.

We've also explained how to ensure your project still works properly
with non-strict build plans when some elements perform static linking
(or other operations which consume data from their dependencies
verbatim), by annotating :ref:`dependency declarations <format_dependencies>`
as ``strict``.
