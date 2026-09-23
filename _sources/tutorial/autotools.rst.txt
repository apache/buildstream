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



.. _tutorial_autotools:

Using the autotools element
===========================
In :ref:`the last chapter <tutorial_running_commands>` we observed how the
:mod:`manual <elements.manual>` element works, allowing one to specify and
run commands manually in the process of constructing an *artifact*.

In this chapter, we'll go over a mostly automated build of a similar
hello world example. We will observe how our configurations of the
:mod:`autotools <elements.autotools>` element translate to configurations
on the :mod:`manual <elements.manual>` element, and observe how
:ref:`variable substitution <format_variables>` works.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/autotools
   <https://github.com/apache/buildstream/tree/master/doc/examples/autotools>`_
   subdirectory.


Overview
--------
Instead of using the :mod:`local <sources.local>` source as we have been using
in the previous examples, we're going to use a :mod:`tar <sources.tar>` source
this time to obtain the ``automake`` release tarball directly from the upstream
hosting.

In this example we're going to build the example program included in the
upstream ``automake`` tarball itself, and we're going to use the automated
:mod:`autotools <elements.autotools>` build element to do so.


Project structure
-----------------


``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/autotools/project.conf
   :language: yaml

Like the :ref:`last project.conf <tutorial_running_commands_project_conf>`, we've
added another :ref:`source alias <project_source_aliases>` for ``gnu``, the location
from which we're going to download the ``automake`` tarball.


``elements/base/alpine.bst`` and ``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The alpine base and base stack element are defined in the
same way as in the last chapter: :ref:`tutorial_running_commands`.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/autotools/elements/hello.bst
   :language: yaml

In this case, we haven't touched the element's ``config`` section
at all, instead we just slightly override the bahavior of the
:mod:`autotools <elements.autotools>` build element by overriding
the :ref:`command-subdir variable <format_variables>`


Looking at variables
''''''''''''''''''''
Let's take a moment and observe how :ref:`element composition
<format_composition>` works with variables.

As :ref:`the documentation <format_composition>` mentions:

* The initial settings of the ``project.conf`` variables are setup
  using BuildStream's :ref:`builtin defaults <project_builtin_defaults>`.

* After this, your local ``project.conf`` may override some variables
  on a project wide basis. Those will in turn be overridden by any
  defaults provided by element classes, such as the variables set in the
  documentation of the :mod:`autotools <elements.autotools>` build element.
  The variables you set in your final ``<element.bst>`` *element declarations*,
  will have the final say on the value of a particular variable.

* Finally, the variables, which may be composed of other variables,
  are resolved after all composition has taken place.

The variable we needed to override was ``command-subdir``, which is an
automatic variable provided by the :mod:`BuildElement <buildstream.buildelement>`
abstract class. This variable simply instructs the :mod:`BuildElement <buildstream.buildelement>`
in which subdirectory of the ``%{build-root}`` to run its commands in.

One can always display the resolved set of variables for a given
element's configuration using :ref:`bst show <invoking_show>`:

.. raw:: html
   :file: ../sessions/autotools-show-variables.html

As an exercise, we suggest that you modify the ``hello.bst``
element to set the prefix like so:

.. code:: yaml

   variables:
     prefix: "/opt"

And rerun the above :ref:`bst show <invoking_show>` command to observe how this
changes the output.

Observe where the variables are declared in the :ref:`builtin defaults
<project_builtin_defaults>` and :mod:`autotools <elements.autotools>` element
documentation, and how overriding these effects the resolved set of variables.


Using the project
-----------------


Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/autotools-build.html


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
We probably know by now what's going to happen, but let's run
the program we've compiled anyway using :ref:`bst shell <invoking_shell>`:

.. raw:: html
   :file: ../sessions/autotools-shell.html


Summary
-------
Now we've used an external :ref:`build element <core_buildelement_builtins>`,
from the ``buildstream-plugins`` package and we've taken a look into
:ref:`how variables work <format_variables>`.

When browsing the :ref:`build elements <core_buildelement_builtins>` in their
respective documentation, we are now equipped with a good idea of what an element
is going to do, based on their default YAML configuration and any configurations
we have in our project. We can also now observe what variables are in effect
for the build of a given element, using :ref:`bst show <invoking_show>`.
