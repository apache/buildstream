:orphan:

.. _format:

Element Constructs
==================


.. _format_basics:

Element Basics
--------------
Here is a rather complete example using the autotools element kind and git source kind:

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
     url: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Override some variables
   variables:
     sysconfdir: %{prefix}/etc

   # Tweak the sandbox shell environment
   environment:
     LD_LIBRARY_PATH: /some/custom/path

   # Specify the configuration of the element
   config:

     # Override autotools element default configure-commands
     configure-commands:
     - "%{configure} --enable-fancy-feature"

   # Specify public domain data, visible to other elements.
   public:
     bst:
       integration-commands:
       - /usr/bin/update-fancy-feature-cache

For most use cases you would not need to specify this much detail, we've provided
details here in order to have a more complete initial example.

Let's break down the above and give a brief explanation of what these attributes mean.


.. _format_kind:

Kind
~~~~

.. code:: yaml

   # Specify the kind of element this is
   kind: autotools

The ``kind`` attribute specifies which plugin will be operating on the element's input to
produce its output. Plugins define element types and each of them can be referred to by
name with the ``kind`` attribute.

To refer to a third party plugin, prefix the plugin with its package, for example:

.. code:: yaml

   kind: buildstream-plugins:dpkg_build


.. _format_depends:

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


.. _format_sources:

Sources
~~~~~~~

.. code:: yaml

   # Specify the source which should be built
   sources:
   - kind: git
     url: upstream:modulename.git
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
     url: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Specify the data package we need for build frobnication,
   # we need it to be unpacked in a src/frobdir
   - kind: tarball
     directory: src/frobdir
     url: data:frobs.tgz
     sha256sum: 9d4b1147f8cf244b0002ba74bfb0b8dfb3...

Like Elements, Source types are plugins which are indicated by the ``kind`` attribute.
Asides from the common ``kind`` and ``directory`` attributes which may be applied to all
Sources, refer to the Source specific documentation for meaningful attributes for the
particular Source.

Variables
~~~~~~~~~

.. code:: yaml

   # Override some variables
   variables:
     sysconfdir: "%{prefix}/etc"

Variables can be declared or overridden from an element. Variables can also be
declared and overridden in the :ref:`projectconf`

See `Using Variables`_ below for a more in depth discussion on variables in BuildStream.


.. _format_environment:

Environment
~~~~~~~~~~~

.. code:: yaml

   # Tweak the sandbox shell environment
   environment:
     LD_LIBRARY_PATH: /some/custom/path

Environment variables can be set to literal values here, these environment
variables will be effective in the :mod:`Sandbox <buildstream.sandbox>` where
build instructions are run for this element.


Environment variables can also be declared and overridden in the :ref:`projectconf`


.. _format_config:

Config
~~~~~~

.. code:: yaml

   # Specify the configuration of the element
   config:

     # Override autotools element default configure-commands
     configure-commands:
     - "%{configure} --enable-fancy-feature"

Here we configure the element itself. The autotools element provides sane defaults for
building sources which use autotools. Element default configurations can be overridden
in the ``project.conf`` file and additionally overridden in the declaration of an element.

For meaningful documentation on what can be specified in the ``config`` section for a given
element ``kind``, refer to the element specific documentation. 


.. _format_public:

Public
~~~~~~

.. code:: yaml

   # Specify public domain data, visible to other elements.
   public:
     bst:
       integration-commands:
       - /usr/bin/update-fancy-feature-cache

Metadata declared in the ``public`` section of an element is visible to
any other element which depends on the declaring element in a given pipeline.
BuildStream itself consumes public data from the ``bst`` domain. The ``integration-commands``
demonstrated above for example, describe commands which should be run in an
environment where the given element is installed but before anything should be run.

An element is allowed to read domain data from any element it depends on, and users
may specify additional domains to be understood and processed by their own element
plugins.


.. _format_dependencies:

Dependencies
------------
The dependency model in BuildStream is simplified by treating software distribution
and software building as separate problem spaces. This is to say that one element
can only ever depend on another element but never on a subset of the product which
another element produces.

In this section we'll quickly go over the few features BuildStream offers in its
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
     type: build
     junction: elements/baseproject.bst

The ``type`` attribute can be used to express the dependency type.

The ``junction`` attribute can be used to depend on elements in other projects.
See :mod:`junction <elements.junction>`.


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


.. _format_variables:

Using Variables
---------------
Variables in BuildStream are a way to make your build instructions and
element configurations more dynamic.


Referring to Variables
~~~~~~~~~~~~~~~~~~~~~~
Variables are expressed as ``%{...}``, where ``...`` must contain only
alphanumeric characters and the separators ``_`` and ``-``. Further, the
first letter of ``...`` must be an alphabetic character.

.. code:: yaml

   This is release version %{version}


Declaring and Overriding Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To declare or override a variable, one need only specify a value
in the relevant *variables* section:

.. code:: yaml

   variables:
     hello: Hello World

You can refer to another variable while declaring a variable:

.. code:: yaml

   variables:
     release-text: This is release version %{version}

The order in which you declare variables is arbitrary, so long as there is no cyclic
dependency and that all referenced variables are declared, the following is fine:

.. code:: yaml

   variables:
     release-text: This is release version %{version}
     version: 5.5

.. note::

   It should be noted that variable resolution only happens after all
   :ref:`Element Composition <format_composition>` has already taken place.

   This is to say that overriding ``%{version}`` at a higher priority will effect
   the final result of ``%{release-text}``.


**Example:**

.. code:: yaml

   kind: autotools

   # Declare variable, expect %{version} was already declared
   variables:
     release-text: This is release version %{version}

   config:

     # Customize the installation
     install-commands:
     - |
       %{make-install} RELEASE_TEXT="%{release-text}"
