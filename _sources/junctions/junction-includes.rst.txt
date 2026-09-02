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



.. _advanced_junction_includes:

Subproject includes
===================
We've already discussed how we can add optionality to projects and
explored how we can perform conditional statements and include fragments
of BuildStream YAML in the earlier :ref:`chapter about optionality and
directives <tutorial_directives>`.

In this chapter we're going to explore how we can use :ref:`include directives
<format_directives_include>` to include YAML fragments from a subproject
referred to by a :mod:`junction <elements.junction>` element, and how
:ref:`project options <project_options>` can be specified in the configuration
of your :mod:`junction <elements.junction>`.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/junction-includes
   <https://github.com/apache/buildstream/tree/master/doc/examples/junction-includes>`_
   subdirectory.


Overview
--------
It is a goal of BuildStream to provide developers and integrators with the tools
they need to maintain software stacks which depend on eachother with least friction
as possible, such that one can integrate upgrades of projects one depends on
via :mod:`junction <elements.junction>` elements regularly and with the least
hassle as possible.

:ref:`Project options <project_options>` and :ref:`include directives
<format_directives_include>` combined form the basis on which projects can
maximize on code sharing effectively, and the basis on which BuildStream
projects can form reliable APIs.


Project options
~~~~~~~~~~~~~~~
The :ref:`options <project_options>` which a project exposes is a fairly
limited API surface, it allows one to configure a limited set of options
advertized by the project maintainers, and the options will affect what
kind of artifacts will be produced by the project.

This kind of optionality however does not allow consumers to entirely
redefine how artifacts are produced and how elements are configured.

On the one hand, this limitation can be frustrating, as one constantly
finds themselves requiring a feature that their subproject does not
support *right now*. On the other hand, the limitation of features which
a given project chooses to support is what guards downstream project
consumers against consuming artifacts which are not supported by the upstream.

Project options are designed to enforce a *separation of concerns*,
where we expect that downstreams will either fork a project in order
to support a new feature, or convince the upstream to start supporting
a new feature. Furthermore, limited API surfaces for interdependent
projects offers a possibility of API stability of projects, such
that you can upgrade your dependencies with limited friction.


Includes
~~~~~~~~
The :ref:`includes <format_directives_include>` which a project might advertize
as *"public"*, form the output of the API exchange between a project and
its subproject(s).

Cross-project include files allow a project to *inherit configuration* from
a subproject. Include files can be used to define anything from the
:ref:`variables <format_variables>` one needs to have in context in order to
build into or link into alternative system prefixes, what special compiler flags
to use when building for a specific machine architecture, to customized
:ref:`shell configurations <project_shell>` to use when testing out applications
in :ref:`bst shell <invoking_shell>`.

This chapter will provide an example of the *mechanics* of cross project
includes when combined with project optionality.


Project structure
-----------------


Project options
~~~~~~~~~~~~~~~
This example is comprised of two separate projects, both of which offer
some project options. This is intended to emphasize how your toplevel project
options can be used to select and configure options to use in the subprojects
you depend on.

For convenience, the subproject is stored in the subdirectory of
the toplevel project, while in the real world the subproject is probably
hosted elsewhere.

First let's take a look at the options declared in the respective
``project.conf`` files.


Toplevel ``project.conf``
'''''''''''''''''''''''''

.. literalinclude:: ../../examples/junction-includes/project.conf
   :language: yaml



Subproject ``project.conf``
'''''''''''''''''''''''''''

.. literalinclude:: ../../examples/junction-includes/subproject/project.conf
   :language: yaml


As we can see, these two projects both offer some arbitrarily named options.


Conditional configuration of subproject
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The toplevel project here does some conditional configuration of the
subproject.


Toplevel ``elements/subproject-junction.bst``
'''''''''''''''''''''''''''''''''''''''''''''

.. literalinclude:: ../../examples/junction-includes/elements/subproject-junction.bst
   :language: yaml

Here we can see that projects can use
:ref:`conditional statements <format_directives_conditional>` to make
decisions about subproject configuration based on their own configuration.

In this example, if the toplevel project is ``funky``, then it will
configure its subproject with ``color`` set to ``blue``, otherwise it
will use the ``red`` variant of the subproject ``color``.


Including configuration from a subproject
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Here there are a couple of aspects to observe, namely how the
toplevel project includes files across a junction boundary,
and how that include file might be implemented.


Toplevel ``elements/hello.bst``
'''''''''''''''''''''''''''''''

.. literalinclude:: ../../examples/junction-includes/elements/hello.bst
   :language: yaml

Here we can see the same element which we discussed in the
:ref:`autotools example <tutorial_autotools>`, except that we're including
a file from the subproject. As explained in the :ref:`reference manual <format_directives_include>`,
this is done by prefixing the include path with the local :mod:`junction <elements.junction>`
element name and then a colon.

Note that in this case, the API contract is simply that ``hello.bst`` is
including ``paths.bst``, and has the expectation that ``paths.bst`` will
in some way influence the ``variables``, nothing more.

It can be that an include file is expected to create new variables, and
it can be that the subproject might declare things differently depending
on the subproject's own configuration, as we will observe next.


Subproject ``include/paths.bst``
''''''''''''''''''''''''''''''''

.. literalinclude:: ../../examples/junction-includes/subproject/include/paths.bst
   :language: yaml

Here, we can see the include file *itself* is making a
:ref:`conditional statement <format_directives_conditional>`, in turn
deciding what values to use depending on how the project was configured.

This decision will provide valuable context for any file including ``paths.bst``,
whether it be an element, a ``project.conf`` which applies the variable as
a default for the entire project, whether it is being included by files
in the local project, or whether it is being included by a downstream
project which junctions this project, as is the case in this example.


Using the project
-----------------
At this stage, you have probably already reasoned out what would happen
if we tried to build and run the project.

Nevertheless, we will still present the outputs here for observation.


Building the project normally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Here we build the project without any special arguments.

.. raw:: html
   :file: ../sessions/junction-includes-build-normal.html


Building the project in funky mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Now let's see what happens when we build the project in funky mode

.. raw:: html
   :file: ../sessions/junction-includes-build-funky.html

As we can see, this time we've built the project into the ``/opt``
system prefix instead of the standard ``/usr`` prefix.

Let's just take a step back now and summarize the process which
went into this decision:

* The toplevel ``project.conf`` exposes the boolean ``funky`` option

* The toplevel junction ``subproject-junction.bst`` chooses to set the
  subproject ``color`` to ``blue`` when the toplevel project is ``funky``

* The subproject ``include/paths.bst`` include file decides to set the
  ``prefix`` to ``/opt`` in the case that the subproject is ``blue``

* The ``hello.bst`` includes the ``include/paths.bst`` file, in order
  to inherit its path configuration from the subproject


Running the project in both modes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. raw:: html
   :file: ../sessions/junction-includes-shell-normal.html

.. raw:: html
   :file: ../sessions/junction-includes-shell-funky.html

As expected, the ``funky`` variant of the toplevel project installs
the hello world program in the ``/opt`` prefix, and as such we
need to call it from there.


Summary
-------
In this chapter we've discussed how :ref:`conditional statements <format_directives_conditional>`
and :ref:`include files <format_directives_include>` play an essential role
in the API surface of a project, and help to provide some configurability
while preserving encapsulation of the API which a project exposes.

We've also gone over the mechanics of how these concepts interact and
presented an example which shows how project options can be used in
a recursive context, and how includes can help not only to share code,
but to provide context to dependent projects about how their subprojects
are configured.
