.. _projectconf:


Project Configuration
=====================
The project configuration file should be named ``project.conf`` and
be located at the project root. It holds information such as Source
aliases relevant for the sources used in the given project as well as
overrides for the configuration of element types used in the project.

Values specified in the project configuration override any of the
default BuildStream project configuration, which is included
:ref:`here <project_defaults>` for reference.


.. _project_essentials:

Essentials
----------


Project Name
~~~~~~~~~~~~
The first thing to setup in your ``project.conf`` should be the name
of your project.

.. code:: yaml

   name: my-project-name

The project name will be used in user configuration and anywhere
that a project needs to be specified.


Element Path
~~~~~~~~~~~~
To allow the user to structure their project nicely, BuildStream
allows the user to specify a project subdirectory where element
``.bst`` files are stored.

.. code:: yaml

   element-path: elements

Note that elements are referred to by their relative paths, whenever
elements are referred to in a ``.bst`` file or on the command line.


Source Aliases
~~~~~~~~~~~~~~
In order to abstract the download location of source code and
any assets which need to be downloaded, and also as a matter of
convenience, BuildStream allows one to create named aliases for
URLs which are to be used in the individual ``.bst`` files.

.. code:: yaml

   aliases:
     foo: git://git.foo.org/
     bar: http://bar.com/downloads/


.. _project_essentials_artifacts:

Artifact Server
~~~~~~~~~~~~~~~
If you have setup an :ref:`artifact server <artifacts>` for your
project then it is convenient to configure this in your ``project.conf``
so that users need not have any additional configuration to communicate
with an artifact share.

.. code:: yaml

  artifacts:

    # A url from which to download prebuilt artifacts
    url: https://foo.com/artifacts


Plugin Origins and Versions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The BuildStream format is guaranteed to be backwards compatible
with any earlier releases. The core YAML format, the format supported
by various plugins, and the overall BuildStream release version are
revisioned separately.

If your project includes any custom *Elements* or *Sources*, then
the origins, names, and minimum version must be defined.
If your project must use a minimum version of a core plugin, this is
also specified here.

Note that elements or plugins with the same name from different origins
are not permitted.

Plugin specification format
'''''''''''''''''''''''''''

.. code:: yaml

   plugins:
   
   # Core is only listed here as a means to allow project.conf
   # authors to specify API versioning requirements
   - origin: core
   
     # Here we CAN specify minimal bound API version for each plugin,
     # if we have such dependencies
     sources:
       git: 2
       local: 1
   
     elements:
       script: 2
   
   # Specify the "pony" plugins found by pip
   - origin: pip
     package-name: pony
   
     # Here we MUST specify a minimal bound API version for each
     # plugin, in order to indicate which plugin is to be discovered
     # from this particular "pip" origin
     sources:
       flying-pony: 0
   
   - origin: pip
     package-name: potato
   
     # Here we have the rotten potato element loaded
     # from the "potato" plugin package loaded via pip,
     # this is a separate origin as the "flying-pony" source
     elements:
       rotten-potato: 0
   
   # Specify the plugins defined locally
   - origin: local
     path: plugins/sources
   
     # Here again we MUST define a minimal bound API version,
     # even though it's immaterial since it's revisioned with
     # the project itself, it informs BuildStream that this
     # source must be loaded in this way
     sources:
       mysource: 0

Project Version Format
''''''''''''''''''''''

The project's minimum required version of buildstream is specified in
``project.conf`` with the ``required-project-version`` field, e.g.

.. code:: yaml

  # The minimum base BuildStream format
  required-project-version: 0

Versioning
~~~~~~~~~~

The ``project.conf`` allows asserting the minimal required core
format version and the minimal required version for individual
plugins.

.. code:: yaml

  required-versions:

    project: 0

    # The minimum version of the autotools element
    elements:
      autotools: 3



.. _project_options:

Options
-------
Options are how BuildStream projects can define parameters which
can be configured by users invoking BuildStream to build your project.

Options are declared in the ``project.conf`` in the main ``options``
dictionary.

.. code:: yaml

   options:
     debug:
       type: bool
       description: Whether to enable debugging
       default: False

Users can configure those options when invoking BuildStream with the
``--option`` argument::

    $ bst --option debug True ...


Common Properties
~~~~~~~~~~~~~~~~~
All option types accept the following common attributes

* ``type``

  Indicates the type of option to declare

* ``description``

  A description of the meaning of the option

* ``variable``

  Optionally indicate a :ref:`variable <format_variables>` name to
  export the option to. A string form of the selected option will
  be used to set the exported value.

  If used, this value will override any existing value for the
  variable declared in ``project.conf``, and will be overridden in
  the regular :ref:`composition order <format_composition>`.


Boolean
~~~~~~~
The ``bool`` option type allows specifying boolean values which
can be cased in conditional expressions.


**Declaring**

.. code:: yaml

   options:
     debug:
       type: bool
       description: Whether to enable debugging
       default: False


**Evaluating**

Boolean options can be tested in expressions with equality tests:

.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - debug == True:
         enable-debug: True

Or simply treated as truthy values:

.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - debug:
         enable-debug: True


**Exporting**

When exporting boolean options as variables, a ``True`` option value
will be exported as ``1`` and a ``False`` option as ``0``


Enumeration
~~~~~~~~~~~
The ``enum`` option type allows specifying a string value
with a restricted set of possible values.


**Declaring**

.. code:: yaml

   options:
     loglevel:
       type: enum
       description: The logging level
       values:
       - debug
       - info
       - warning
       default: info


**Evaluating**

Enumeration options must be tested as strings in conditional
expressions:

.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - loglevel == "debug":
         enable-debug: True


**Exporting**

When exporting enumeration options as variables, the value is
exported as a variable directly, as it is a simple string.


Flags
~~~~~
The ``flags`` option type allows specifying a list of string
values with a restricted set of possible values.

In contrast with the ``enum`` option type, the *default* value
need not be specified and will default to an empty set.


**Declaring**

.. code:: yaml

   options:
     logmask:
       type: flags
       description: The logging mask
       values:
       - debug
       - info
       - warning
       default:
       - info


**Evaluating**

Flags type options can be tested in conditional expressions using
a pythonic *in* syntax to test if an element is present in a set:

.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - ("debug" in logmask):
         enable-debug: True


**Exporting**

When exporting flags options as variables, the value is
exported as a comma separated list of selected value strings.


Architecture
~~~~~~~~~~~~
The ``arch`` type option is special enumeration option which
defaults to the result of `uname -m`, and does not support
assigning any default in the project configuration.

.. code:: yaml

   options:
     machine_arch:
       type: arch
       description: The machine architecture
       values:
       - arm
       - aarch64
       - i386
       - x86_64


Architecture options can be tested with the same expressions
as other Enumeration options.


Element Mask
~~~~~~~~~~~~
The ``element-mask`` option type is a special Flags option
which automatically allows only element names as values.

.. code:: yaml

   options:
     debug_elements:
       type: element-mask
       description: The elements to build in debug mode

This can be convenient for automatically declaring an option
which might apply to any element, and can be tested with the
same syntax as other Flag options.


.. code:: yaml

   variables:
     enable-debug: False
     (?):
     - ("element.bst" in debug_elements):
         enable-debug: True



.. _project_defaults:

Specifying Defaults
--------------------
The ``project.conf`` plays a role in defining elements by
providing default values and also by overriding values declared
by plugins on a plugin wide basis.

See the :ref:`composition <format_composition>` documentation for
more detail on how elements are composed.


Variables
~~~~~~~~~
The defaults for :ref:`Variables <format_variables>` used in your
project is defined here.

.. code:: yaml

   variables:
     prefix: "/usr"


Environment
~~~~~~~~~~~
The defaults environment for the build sandbox is defined here.

.. code:: yaml

   environment:
     PATH: /usr/bin:/bin:/usr/sbin:/sbin

Additionally, the special ``environment-nocache`` list which specifies
which environment variables do not effect build output, and are thus
not considered in the calculation of artifact keys can be defined here.

.. code:: yaml

   environment-nocache:
   - MAXJOBS

Note that the ``environment-nocache`` list only exists so that we can
control parameters such as ``make -j ${MAXJOBS}``, allowing us to control
the number of jobs for a given build without effecting the resulting
cache key.


Split Rules
~~~~~~~~~~~
The project wide :ref:`split rules <public_split_rules>` defaults can
be specified here.

.. code:: yaml

   split-rules:
     devel:
     - |
       %{includedir}
     - |
       %{includedir}/**
     - |
       %{libdir}/lib*.a
     - |
       %{libdir}/lib*.la


Element Overrides
~~~~~~~~~~~~~~~~~
Base attributes declared by element default yaml files can be overridden
on a project wide basis. The elements dictionary can be used to override
variables, environments or plugin specific configuration data as shown below.


.. code:: yaml

   elements:

     # Override default values for all autotools elements
     autotools:

       variables:
         bindir: "%{prefix}/bin"

       config:
         configure-commands: ...

       environment:
         PKG_CONFIG_PATH=%{libdir}/pkgconfig


.. _project_builtin_defaults:

Builtin Defaults
----------------
BuildStream defines some default values for convenience, the default
values overridden by your project's ``project.conf`` are presented here:

  .. literalinclude:: ../../buildstream/data/projectconfig.yaml
     :language: yaml
