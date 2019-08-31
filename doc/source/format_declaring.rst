

Declaring elements
==================


.. _format_basics:

Element basics
--------------
Here is a rather complete example using the autotools element kind and git source kind:

.. code:: yaml

   # Specify the kind of element this is
   kind: autotools

   # Specify some dependencies
   depends:
   - element1.bst
   - element2.bst

   # Specify the source which should be built
   sources:
   - kind: git
     url: upstream:modulename.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Override some variables
   variables:
     sysconfdir: "%{prefix}/etc"

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

   # Specify a user id and group id to use in the build sandbox.
   sandbox:
     build-uid: 0
     build-gid: 0


For most use cases you would not need to specify this much detail, we've provided
details here in order to have a more complete initial example.

Let's break down the above and give a brief explanation of what these attributes mean.


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
   - element1.bst
   - element2.bst

Relationships between elements are specified with the ``depends`` attribute. Elements
may depend on other elements by specifying the :ref:`element path <project_element_path>`
relative filename to the elements they depend on here.

See :ref:`format_dependencies` for more information on the dependency model.


.. _format_build_depends:

Build-Depends
~~~~~~~~~~~~~

.. code:: yaml

   # Specify some build-dependencies
   build-depends:
   - element1.bst
   - element2.bst

Build dependencies between elements can be specified with the ``build-depends`` attribute.
The above code snippet is equivalent to:

.. code:: yaml

   # Specify some build-dependencies
   depends:
   - filename: element1.bst
     type: build
   - filename: element2.bst
     type: build

See :ref:`format_dependencies` for more information on the dependency model.

.. note::

   The ``build-depends`` configuration is available since :ref:`format version 14 <project_format_version>`


.. _format_runtime_depends:

Runtime-Depends
~~~~~~~~~~~~~~~

.. code:: yaml

   # Specify some runtime-dependencies
   runtime-depends:
   - element1.bst
   - element2.bst

Runtime dependencies between elements can be specified with the ``runtime-depends`` attribute.
The above code snippet is equivalent to:

.. code:: yaml

   # Specify some runtime-dependencies
   depends:
   - filename: element1.bst
     type: runtime
   - filename: element2.bst
     type: runtime

See :ref:`format_dependencies` for more information on the dependency model.

.. note::

   The ``runtime-depends`` configuration is available since :ref:`format version 14 <project_format_version>`


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
     ref: 9d4b1147f8cf244b0002ba74bfb0b8dfb3...

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

See :ref:`format_variables` below for a more in depth discussion on variables in BuildStream.


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
element ``kind``, refer to the :ref:`element specific documentation <plugins>`.


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

The public data keys which are recognized under the ``bst`` domain
can be viewed in detail in the :ref:`builtin public data <public_builtin>` section.


.. _format_sandbox:

Sandbox
~~~~~~~
Configuration for the build sandbox (other than :ref:`environment variables <format_environment>`)
can be placed in the ``sandbox`` configuration. The UID and GID used by the user
in the group can be specified, as well as the desired OS and machine
architecture. Possible machine architecture follow the same list as specified in
the :ref:`architecture option <project_options_arch>`.

.. code:: yaml

   # Specify a user id and group id to use in the build sandbox.
   sandbox:
     build-uid: 1003
     build-gid: 1001

BuildStream normally uses uid 0 and gid 0 (root) to perform all
builds. However, the behaviour of certain tools depends on user id,
behaving differently when run as non-root. To support those builds,
you can supply a different uid or gid for the sandbox. Only
bwrap-style sandboxes support custom user IDs at the moment, and hence
this will only work on Linux host platforms.

.. code:: yaml

   # Specify build OS and architecture
   sandbox:
     build-os: AIX
     build-arch: power-isa-be

When building locally, if these don't match the host machine then generally the
build will fail. The exception is when the OS is Linux and the architecture
specifies an ``x86-32`` build on an ``x86-64`` machine, or ``aarch32`` build on
a ``aarch64`` machine, in which case the ``linux32`` command is prepended to the
bubblewrap command.

When building remotely, the OS and architecture are added to the ``Platform``
field in the ``Command`` uploaded. Whether this actually results in a building
the element for the desired OS and architecture is dependent on the server
having implemented these options the same as buildstream.

.. note::

   The ``sandbox`` configuration is available since :ref:`format version 6 <project_format_version>`


.. _format_dependencies:

Dependencies
------------
The dependency model in BuildStream is simplified by treating software distribution
and software building as separate problem spaces. This is to say that one element
can only ever depend on another element but never on a subset of the product which
another element produces.

In this section we'll quickly go over the few features BuildStream offers in its
dependency model.


Expressing dependencies
~~~~~~~~~~~~~~~~~~~~~~~
Dependencies in BuildStream are parameterizable objects, however as demonstrated
in the :ref:`above example <format_depends>`, they can also be expressed as simple
strings as a convenience shorthand in most cases, whenever the default dependency
attributes are suitable.

.. note::

   Note the order in which element dependencies are declared in the ``depends``,
   ``build-depends`` and ``runtime-depends`` lists are not meaningful.

Dependency dictionary:

.. code:: yaml

   # Fully specified dependency
   depends:
   - filename: foo.bst
     type: build
     junction: baseproject.bst
     strict: false

Attributes:

* ``filename``

  The :ref:`element path <project_element_path>` relative filename of the element to
  depend on in the project.

* ``type``

  This attribute is used to express the :ref:`dependency type <format_dependencies_types>`.
  This field is not permitted in :ref:`Build-Depends <format_build_depends>` or
  :ref:`Runtime-Depends <format_runtime_depends>`.

* ``junction``

  This attribute can be used to depend on elements in other projects.

  If a junction is specified, then it must be an :ref:`element path <project_element_path>`
  relative filename of the junction element in the project.

  In the case that a *junction* is specified, the ``filename`` attribute indicates an element
  in the *junctioned project*.

  See :mod:`junction <elements.junction>`.

  .. note::

     The ``junction`` attribute is available since :ref:`format version 1 <project_format_version>`

* ``strict``

  This attribute can be used to specify that this element should
  be rebuilt when the dependency changes, even when
  :ref:`strict mode <user_config_strict_mode>` has been turned off.

  This is appropriate whenever a dependency's output is consumed
  verbatim in the output of the depending element, for instance
  when static linking is in use.


Cross-junction dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~
As mentioned above, cross-junction dependencies can be specified using the
``junction`` attribute. They can also be expressed as simple strings as a
convenience shorthand. You can refer to cross-junction elements using the
syntax ``{junction-name}:{element-name}``.

For example, the following is logically same as the example above:

.. code:: yaml

   build-depends:
     - baseproject.bst:foo.bst

Similarly, you can also refer to cross-junction elements via the ``filename``
attribute, like so:

.. code:: yaml

   depends:
     - filename: baseproject.bst:foo.bst
       type: build

.. note::

   BuildStream does not allow recursice lookups for junction elements. If a
   filename contains more than one ``:`` (colon) character, an error will be
   raised. See :ref:`nested junctions <core_junction_nested>` for more details
   on nested junctions.

.. note::

   This shorthand is available since :ref:`format version 23 <project_format_version>`


.. _format_dependencies_types:

Dependency types
~~~~~~~~~~~~~~~~
The dependency ``type`` attribute defines what the dependency is required for
and is essential to how BuildStream plots a build plan.

There are two types which one can specify for a dependency:

* ``build``

  A ``build`` dependency type states that the given element's product must
  be staged in order to build the depending element. Depending on an element
  which has ``build`` dependencies will not implicitly depend on that element's
  ``build`` dependencies.

* ``runtime``

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

Using variables
---------------
Variables in BuildStream are a way to make your build instructions and
element configurations more dynamic.


Referring to variables
~~~~~~~~~~~~~~~~~~~~~~
Variables are expressed as ``%{...}``, where ``...`` must contain only
alphanumeric characters and the separators ``_`` and ``-``. Further, the
first letter of ``...`` must be an alphabetic character.

.. code:: yaml

   This is release version %{version}


Declaring and overriding variables
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

   This is to say that overriding ``%{version}`` at a higher priority will affect
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


Variables declared by BuildStream
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream declares a set of :ref:`builtin <project_builtin_defaults>`
variables that may be overridden. In addition, the following
read-only variables are also dynamically declared by BuildStream:

* ``element-name``

  The name of the element being processed (e.g base/alpine.bst).

* ``project-name``

  The name of project where BuildStream is being used.

* ``max-jobs``

  Maximum number of parallel build processes within a given
  build, support for this is conditional on the element type
  and the build system used (any element using 'make' can
  implement this).


Naming elements
---------------
When naming the element files, use the following rules:

* The name of the file must have ``.bst`` extension.

* All characters in the name must be printable 7-bit ASCII characters.

* Following characters are reserved and must not be part of the name:

  - ``<`` (less than)
  - ``>`` (greater than)
  - ``:`` (colon)
  - ``"`` (double quote)
  - ``/`` (forward slash)
  - ``\`` (backslash)
  - ``|`` (vertical bar)
  - ``?`` (question mark)
  - ``*`` (asterisk)

BuildStream will attempt to raise warnings when any of these rules are violated
but that may not always be possible.
