.. _format:

The BuildStream Format
======================
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
their project directory in any way. For documentation on the format of the project
configuration file, refer to the :mod:`Project <buildstream.project>` documentation.

Simpler projects may choose to place all element definition files at the
root of the project directory while more complex projects may decide to
put stacks in one directory and other floating elements into other directories,
perhaps placing deployment elements in another directory, this is all fine.

The important part to remember is that when you declare dependency relationships,
a project relative path to the element one depends on must be provided.


Element Basics
--------------
Here is a basic example using the autotools element kind and git source kind:

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

The above is a pretty simple example, and for most cases you would not have to specify
explicit configure commands or commands in the integration domain, we've just provided
that here to have a more complete initial example.

Let's break down the above and give a brief explanation of what these attributes mean.


Kind
~~~~

.. code:: yaml

   # Specify the kind of element this is
   kind: autotools

The ``kind`` attribute specifies which plugin will be operating on the element's input to
produce it's output. Plugins define element types and each of them can be referred to by
name with the ``kind`` attribute.


Depends
~~~~~~~

.. code:: yaml

   # Specify some dependencies
   depends:
   - elements/element1.bst
   - elements/element2.bst

Relationships between elements are specified with the ``depends`` attribute. Element
definitions may depend on other elements by specifying the project relative path
to the elements on which they depend here. See `Dependencies`_ for more information
on the dependency model.


Sources
~~~~~~~

.. code:: yaml

   # Specify the source which should be built
   sources:
   - kind: git
     uri: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

Here we specify some input for the element, any number of sources may be specified.
By default the sources will be staged in the root of the element's build directory
in the build sandbox, but sources may specify a ``directory`` attribute to control
where the sources will be staged. The ``directory`` attribute may specify a build
sandbox relative subdirectory.

For example, one might encounter a component which requires a separate data package
in order to build itself, in this case the sources might be listed as:

.. code:: yaml

   sources:

   # Specify the source which should be built
   - kind: git
     uri: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Specify the data package we need for build frobnication,
   # we need it to be unpacked in a src/frobdir
   - kind: tarball
     directory: src/frobdir
     uri: data:frobs.tgz
     sha256sum: 9d4b1147f8cf244b0002ba74bfb0b8dfb3...

Like Elements, Source types are plugins which are indicated by the ``kind`` attribute.
Asides from the common ``kind`` and ``directory`` attributes which may be applied to all
Sources, refer to the Source specific documentation for meaningful attributes for the
particular Source.


Config
~~~~~~

.. code:: yaml

   # Specify the configuration of the element
   config:

     # Override autotools element default configure-commands
     configure-commands:
     - ./configure --enable-fancy-feature

Here we configure the element itself. The autotools element provides sane defaults for
building sources which use autotools. Element default configurations can be overridden
in the ``project.conf`` file and additionally overridden in the declaration of an element.

For meaningful documentation on what can be specified in the ``config`` section for a given
element ``kind``, refer to the element specific documentation. 


Public
~~~~~~

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


Dependencies
------------
The dependency model in BuildStream is simplified by treating software distribution
and software building as separate problem spaces. This is to say that one element
can only ever depend on another element but never on a subset of the product which
another element produces.

In this section we'll quickly go over the few features BuildStream offers in it's
dependency model.


Expressing Dependencies
~~~~~~~~~~~~~~~~~~~~~~~
Dependencies in BuildStream are parameterizable objects, however as demonstrated
in the above example, they can also be expressed as strings as a convenience
shorthand whenever the default dependency attributes are suitable.

Shorthand:

.. code:: yaml

   # Shorthand Dependencies
   depends:
   - elements/foo.bst
   - elements/bar.bst

Dependency dictionary:

.. code:: yaml

   # Fully specified dependency
   depends:
   - filename: elements/foo.bst
     variant: bar
     type: build

The ``variant`` attribute is explained below in `Variant Conditionals`_, and
the ``type`` attribute can be used to express the dependency type.


Dependency Types
~~~~~~~~~~~~~~~~
The dependency ``type`` attribute defines what the dependency is required for
and is essential to how BuildStream plots a build plan.

There are two types which one can specify for a dependency, ``build`` and ``runtime``.

A ``build`` dependency type states that the given element's product must
be staged in order to build the depending element. Depending on an element
which has ``build`` dependencies will not implicitly depend on that element's
``build`` dependencies.

A ``runtime`` dependency type states that the given element's product
must be present for the depending element to function. An element's
``runtime`` dependencies need not be staged in order to build the element.

If ``type`` is not specified, then it is assumed that the dependency is
required both at build time and runtime.

.. note::

   It is assumed that a dependency which is required for building an
   element must run while building the depending element. This means that
   ``build`` depending on a given element implies that that element's
   ``runtime`` dependencies will also be staged for the purpose of building.


Architecture Conditionals
-------------------------
To BuildStream, an architecture is simply an arbitrary name that is associated with
the target architecture and compiler tuning. Conditional YAML segments can be applied
for a given target architecture, like so:

.. code:: yaml

   kind: autotools
   config:
     something: 5
   arches:
     x86_64:
       config:
         something: 6
     x86_32:
       config:
         something: 7

The ``arches`` attribute, if provided, overrides the element for a given architecture
name. It is not considered an error if the element does not provide an architecture
clause for the specific architecture BuildStream was launched to build for.

In the above example we demonstrate that a given ``config`` attribute can be overridden
by an architecture conditional, this can however be done for any segment of the
element such as ``depends``, ``sources`` and ``public`` as well. It is however illegal
to override the element ``kind`` in any conditional.

Further, it should be noted that when applying elements to a list in the element YAML,
the conditional segments are *appended* to the parent list and do not replace the list
entirely.

Consider for example:

.. code:: yaml

   kind: autotools
   depends:
   - elements/foo.bst
   arches:
     x86_64:
       depends:
       - elements/bar.bst

When targetting the ``x86_64`` architecture name, the above element YAML will
expand to the following YAML:

.. code:: yaml

   kind: autotools
   depends:
   - elements/foo.bst
   - elements/bar.bst


Variant Conditionals
--------------------
Variants are a way for a single element to provide multiple features. In contrast
with the architecture conditionals described above, which are resolved once for
the entirety of a pipeline; variant conditionals are selected by way of dependency.


Declaring Variants
~~~~~~~~~~~~~~~~~~
If an element declares any variants, it must declare at least two variants.
One of the variant declarations may be left empty so that they do not override
or effect the base element declaration, but at least two variant names must be
declared.

The first declared variant is the default. It may have whatever name you decide
to give it, but the default variant is what will be selected if all dependencies
on the given element are *ambivalent* of the variant.

Here is an example of how an element declares multiple variants:

.. code:: yaml

   # Unconditionally depend on foo.bst
   kind: autotools
   depends:
   - elements/foo.bst

   variants:

   # The default variant needs to disable flying ponies, or else
   # our configure script bails out if the ponies are not found
   - variant: default
     config:
       configure-commands:
       - ./configure --without-flying-ponies

   # For the flying-ponies variant, we want to pull in the extra
   # ponies so they will be available for flying
   - variant: flying-ponies
     depends:
     - elements/ponies.bst


Depending on Variants
~~~~~~~~~~~~~~~~~~~~~
To depend on a specific variant of a given element, one must simply use
the ``variant`` attribute in a dependency that is expressed as a dictionary:

.. code:: yaml

   # Depend on the flying-ponies variant of the foo element
   depends:
   - filename: elements/foo.bst
     variant: flying-ponies

When depending on an element which advertizes variants without specifying
any particular variant, the dependency is said to be *ambivalent*.


Variant Resolution
~~~~~~~~~~~~~~~~~~
Variants of an element may augment the given element's dependencies, as
such there may be many possible ways in which a pipeline can be constructed.

As a rule, every variant of a given element should be buildable without
presenting any conflict when building the element as your pipeline *target*.

When resolving variants in a complex pipeline however, it is possible that
sibling elements depend on specific variants of common dependencies. BuildStream
will resolve which variants to build deterministically by traversing an
element's variants in the order of declaration, always choosing the first
buildable variant for any *ambivalent* dependency.

If there is no suitable build plan found for the selected variant of the
pipeline *target*, then it is considered a variant disagreement error and
the build will be aborted during the parse phase.
