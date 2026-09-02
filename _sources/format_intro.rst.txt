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



Introduction
============
At the core of BuildStream is a data model of :mod:`Elements <buildstream.element>` which
are parsed from ``.bst`` files in a project directory and configured from a few different
sources.

When BuildStream loads your project, various levels of composition occur, allowing
configuration on various levels with different priority.

This page provides an introduction to the project directory structure, explains the
basic *directives* supported inherently throughout the format, and outlines how composition
occurs and what configurations are considered in which order.

The meaning of the various constructs expressed in the BuildStream format are covered
in other sections of the documentation.

.. _format_structure:


Directory structure
-------------------
A BuildStream project is a directory consisting of:

* A project configuration file
* BuildStream element files
* Optional user defined plugins
* An optional project.refs file

A typical project structure may look like this::

  myproject/project.conf
  myproject/project.refs
  myproject/elements/element1.bst
  myproject/elements/element2.bst
  myproject/elements/...
  myproject/plugins/customelement.py
  myproject/plugins/customelement.yaml
  myproject/plugins/...


Except for the project configuration file, the user is allowed to structure
their project directory in any way. For documentation on the format of the project
configuration file, refer to the :ref:`projectconf` documentation.

Simpler projects may choose to place all element definition files at the
root of the project directory while more complex projects may decide to
put stacks in one directory and other floating elements into other directories,
perhaps placing deployment elements in another directory, this is all fine.

The important part to remember is that when you declare dependency relationships,
a project relative path to the element one depends on must be provided.


.. _format_composition:

Composition
-----------
Below are the various sources of configuration which go into an element or source in the
order in which they are applied. Configurations which are applied later have a higher
priority and override configurations which precede them.


1. Builtin defaults
~~~~~~~~~~~~~~~~~~~
The :ref:`builtin defaults <project_builtin_defaults>` provide a set of builtin
default default values for ``project.conf``.

The project wide defaults defined in the builtin project configuration, such as the
*variables* or *environment* sections, form the base configuration of all elements.


2. Project configuration
~~~~~~~~~~~~~~~~~~~~~~~~
The :ref:`project wide defaults <project_defaults>` specified in your
``project.conf`` are now applied on top of builtin defaults.

Defaults such as the :ref:`variables <project_defaults_variables>` or
:ref:`environment <project_defaults_environment>` which are specified in
your ``project.conf`` override the builtin defaults for elements.

Note that :ref:`plugin type specific configuration <project_overrides>`
in ``project.conf`` is not applied until later.


3. Plugin defaults
~~~~~~~~~~~~~~~~~~
Elements and Sources are all implemented as plugins.

Each Element plugin installs a ``.yaml`` file along side their plugin to
define the default *variables*, *environment* and *config*.  The *config*
is element specific and as such this is the first place where defaults
can be set on the *config* section.

The *variables* and *environment* specified in the declaring plugin's
defaults here override the project configuration defaults for the given
element ``kind``.

Source plugins do not have a ``.yaml`` file, and do not have *variables* or
*environment*.


4. Project configuration overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``project.conf`` now gives you :ref:`another opportunity <project_overrides>` to
override configuration on a per plugin basis.

Configurations specified in the :ref:`elements <project_element_overrides>` or
:ref:`sources <project_source_overrides>` sections of the ``project.conf``
will override the given plugin's defaults.

In this phase, it is possible to override any configurations of a given plugin,
including configuration in element specific *config* sections.

See also :ref:`project_overrides`


5. Plugin declarations
~~~~~~~~~~~~~~~~~~~~~~~
Finally, after having resolved any :ref:`conditionals <format_directives_conditional>`
in the parsing phase of loading element declarations; the configurations specified in a
``.bst`` file have the last word on any configuration in the data model.


.. _format_directives:

Directives
----------

.. _format_directives_conditional:

(?) Conditionals
~~~~~~~~~~~~~~~~
The ``(?)`` directive allows expression of conditional statements which
test :ref:`project option <project_options>` values.

The ``(?)`` directive may appear as a key in any dictionary expressed
in YAML, and its value is a list of conditional expressions. Each conditional
expression must be a single key dictionary, where the key is the conditional
expression itself, and the value is a dictionary to be composited into the
parent dictionary containing the ``(?)`` directive if the expression evaluates
to a truthy value.

**Example:**

.. code:: yaml

   variables:
     prefix: "/usr"
     enable-debug: False
     (?):
     - relocate == True:
         prefix: "/opt"
     - debug == True:
         enable-debug: True


Expressions are evaluated in the specified order, and each time an expression
evaluates to a truthy value, its value will be composited to the parent dictionary
in advance of processing other elements, allowing for logically overriding previous
decisions in the condition list.

Nesting of conditional statements is also supported.

**Example:**

.. code:: yaml

   variables:
     enable-logging: False
     enable-debug: False
     (?):
     - logging == True:
         enable-logging: True
         (?):
	 - debugging == True:
             enable-debug: True


Conditionals are expressed in a pythonic syntax, the specifics for
testing the individually supported option types are described in
their :ref:`respective documentation <project_options>`.

Compound conditionals are also allowed.

**Example:**

.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - (logging == True and debugging == True):
         enable-debug: True

.. important::

   Conditional statements are guaranteed to always be resolved in the
   context of the project where the conditional statement is *declared*.

   When :ref:`including a file <format_directives_include>` from a
   subproject, any conditionals expressed in that file will already be
   resolved in the context of the subproject which the file was included
   from.


.. _format_directives_assertion:

(!) Assertions
~~~~~~~~~~~~~~
Assertions allow the project author to abort processing and present
a custom error message to the user building their project.

This is only useful when used with conditionals, allowing the project
author to assert some invalid configurations.


**Example:**

.. code:: yaml

   variables:
     (?):
     - (logging == False and debugging == True):

         (!): |

           Impossible to print any debugging information when
	   logging is disabled.


.. _format_directives_list_prepend:

(<) List Prepend
~~~~~~~~~~~~~~~~
Indicates that the list should be prepended to the target list,
instead of the default behavior which is to replace the target list.

**Example:**

.. code:: yaml

   config:
     configure-commands:
       # Before configuring, lets make sure we're using
       # the latest config.sub & config.guess
       (<):
       - cp %{datadir}/automake-*/config.{sub,guess} .


.. _format_directives_list_append:

(>) List Append
~~~~~~~~~~~~~~~
Indicates that the list should be appended to the target list, instead
of the default behavior which is to replace the target list.

**Example:**

.. code:: yaml

   public:
     bst:
       split-rules:
         devel:
	   # This element also adds some extra stubs which
	   # need to be included in the devel domain
	   (>):
           - "%{libdir}/*.stub"


.. _format_directives_list_overwrite:

(=) List Overwrite
~~~~~~~~~~~~~~~~~~
Indicates that the list should be overwritten completely.

This exists mostly for completeness, and we recommend using literal
lists most of the time instead of list overwrite directives when the
intent is to overwrite a list.

This has the same behavior as a literal list, except that an
error will be triggered in the case that there is no underlying
list to overwrite; whereas a literal list will simply create a new
list.

The added error protection can be useful when intentionally
overwriting a list in an element's *public data*, which is mostly
free form and not validated.


**Example:**

.. code:: yaml

   config:
     install-commands:
       # This element's `make install` is broken, replace it.
       (=):
       - cp src/program %{bindir}


.. _format_directives_include:

(@) Include
~~~~~~~~~~~
Indicates that content should be loaded from files.

The include directive expects a string, or a list of strings when
including multiple files. Each of these strings represent a project
relative filename to include. Files can be included from subprojects
by prefixing the string with the locally defined :mod:`junction
element <elements.junction>` and colon (':').

The include directive can be used in any dictionary declared in the
:ref:`project.conf <projectconf>`, in any :ref:`.bst file
<format_basics>`, or recursively included in another include file.

The including YAML fragment has priority over the files it includes,
and overrides any values introduced by the includes. When including
multiple files, files are included in the order they are declared in
the include list, and each subsequent include file takes priority over
the previous one.

**Example:**

.. code:: yaml

   environment:
     (@): junction.bst:includes/environment.bst

.. important::

   Files included across a junction cannot be used to inform the
   declaration of a :mod:`junction element <elements.junction>`, as
   this can present a circular dependency.

   Any :ref:`variables <format_variables>`, :ref:`element
   overrides <project_element_overrides>`, :ref:`source
   overrides <project_source_overrides>` or :ref:`mirrors
   <project_essentials_mirrors>` used in the declaration of a junction
   must be declared in the :ref:`project.conf <projectconf>` or in
   included files which are local to the project declaring the
   junction itself.
