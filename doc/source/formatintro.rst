:orphan:

.. _formatintro:


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


Directory Structure
-------------------
A BuildStream project is a directory consisting of:

* A project configuration file
* BuildStream element files
* User defined Plugins

A typical project structure may look like this::

  myproject/project.conf
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

1. BuildStream Default Project Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`builtin defaults <project_builtin_defaults>` provide a set of default values for *variables*
and the *environment*.


2. Project Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

The project wide defaults in ``project.conf`` are now applied on top
of builtin defaults.  If you specify anything in the *variables* or
*environment* sections in your ``project.conf`` then it will override
the builtin defaults.

Note that plugin-specific configuration in ``project.conf`` is not applied
until later.


3. Plugin Defaults
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


4. Project Configuration Overrides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``project.conf`` now gives you another opportunity to override *variables*, *environment*
and *config* sections on a per plugin basis.

Configurations specified in the *elements* or *sources* sections of the ``project.conf``
will override the given plugin's default.

See also :ref:`Source Overrides<project_source_overrides>` and
:ref:`Element Overrides<project_element_overrides>`


5. Plugin Declarations
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
