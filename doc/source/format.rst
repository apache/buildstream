.. _format:

Introduction to the BuildStream Format
======================================
This page should tell you everything you need to know about the base YAML format
which BuildStream uses.

This will not cover the configurations needed for various plugins, plugin configurations
are documented in the plugins themselves.


The Project Directory
---------------------
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
their project directory in any way.

Simpler projects may choose to place all element definition files at the
root of the project directory while more complex projects may decide to
put stacks in one directory and other floating elements into other directories,
perhaps placing deployment elements in another directory, this is all fine.

The important part to remember is that when you declare dependency relationships,
a project relative path to the element one depends on must be provided.


Element Basics
--------------
Here is a basic example using the autotools element kind:

.. code:: yaml

   # Specify the kind of element this is
   kind: autotools

   # Specify some dependencies
   depends:
   - elements/element1.bst
   - elements/element2.bst

   # Specify the source which should be built
   sources:
   - kind: git
     uri: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Specify the configuration of the element
   config:

     # Override autotools element default configure-commands
     configure-commands:
     - ./configure --enable-fancy-feature

   # Specify public domain visible to other elements.
   public:
   - domain: integration
     commands:
     - /usr/bin/update-fancy-feature-cache

The above is a pretty simple example, and for most cases you would
not have to specify explicit configure commands or commands in the
integration domain, we've just provided that here to have a more complete
initial example.

Let's break down the above an give a brief explanation of what these
directives do.

.. code:: yaml

   # Specify the kind of element this is
   kind: autotools

Specifying the ``kind`` of the element specifies which plugin will
be operating on the element's input to produce it's output. Plugins
define element types and each of them can be referred to by name
with the ``kind`` attribute.

.. code:: yaml

   # Specify some dependencies
   depends:
   - elements/element1.bst
   - elements/element2.bst

Relationships between elements are specified with the ``depends``
attribute. Element definitions may depend on another elements
by specifying the project relative path to the elements on which
they depend here.

.. code:: yaml

   # Specify the source which should be built
   sources:
   - kind: git
     uri: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

Here we specify some input for the element, any number of
sources may be specified. By default the sources will be
staged in the root of the element's build directory in the
build sandbox, but sources may specify a ``directory`` attribute
to control where the sources will be staged. The ``directory``
attribute may specify a build sandbox relative subdirectory.

.. code:: yaml

   # Specify the configuration of the element
   config:

     # Override autotools element default configure-commands
     configure-commands:
     - ./configure --enable-fancy-feature

Here we configure the element itself. The autotools element provides
sane defaults for building sources which use autotools. Element default
configurations can be overridden in the ``project.conf`` file and
additionally overridden in the declaration of an element.

.. code:: yaml

   # Specify public domain visible to other elements.
   public:
   - domain: integration
     commands:
     - /usr/bin/update-fancy-feature-cache

Metadata declared in the ``public`` section of an element is visible to
any other element which depends on the declaring element in a given pipeline.
BuildStream itself supports some built-in domains, for instance the ``integration``
domain demonstrated above describes commands which should be run in an environment
where the given element is installed.

That said, users may add their own domain names which are understood by their
own element plugins. This allows one to use custom domain data on their project
to provide additional context for any custom element plugins one wants to use.
