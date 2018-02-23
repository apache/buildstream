:orphan:

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


.. _project_format_version:

Format Version
~~~~~~~~~~~~~~
The BuildStream format is guaranteed to be backwards compatible
with any earlier releases. The project's minimum required format
version of BuildStream can be specified in ``project.conf`` with
the ``format-version`` field, e.g.:

.. code:: yaml

  # The minimum base BuildStream format
  format-version: 0

BuildStream will increment it's core YAML format version at least once
in any given minor point release where the format has been extended
to support a new feature.

.. note::

   :mod:`Element <buildstream.element>` and :mod:`Source <buildstream.source>`
   plugins also implement their own YAML configuration fragments and as
   such are revisioned separately from the core format. See :ref:`project_plugins`
   for details on specifying a minimum version of a specific plugin.


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

You can also specify a list of caches here; earlier entries in the list
will have higher priority than later ones.


Fail on Overlaps
~~~~~~~~~~~~~~~~
When multiple elements are staged, there's a possibility that different
elements will try and stage different versions of the same file.

When ``fail-on-overlap`` is true, if an overlap is detected
that hasn't been allowed by the element's
:ref:`overlap whitelist<public_overlap_whitelist>`,
then an error will be raised and the build will fail.

otherwise, a warning will be raised indicating which files had overlaps,
and the order that the elements were overlapped.

.. code:: yaml

  fail-on-overlap: true


.. _project_shell:

Customizing the shell
---------------------
Since BuildStream cannot know intimate details about your host or about
the nature of the runtime and software that you are building, the shell
environment for debugging and testing applications may need some help.

The ``shell`` section allows some customization of the shell environment.

.. note::

   The ``shell`` section is available since :ref:`format version 1 <project_format_version>`


Interactive Shell Command
~~~~~~~~~~~~~~~~~~~~~~~~~
By default, BuildStream will use ``sh -i`` when running an interactive
shell, unless a specific command is given to the ``bst shell`` command.

BuildStream will automatically set a convenient prompt via the ``PS1``
environment variable for interactive shells; which might be overwritten
depending on the shell you use in your runtime.

If you are using ``bash``, we recommend the following configuration to
ensure that the customized prompt is not overwritten:

.. code:: yaml

   shell:

     # Specify the command to run by default for interactive shells
     command: [ 'bash', '--noprofile', '--norc', '-i' ]


Environment Inheritance
~~~~~~~~~~~~~~~~~~~~~~~
In order to cooperate with your host environment, a debugging shell
sometimes needs to know some of your host environment variables in
order to be more useful.

For example, to share your host ``DISPLAY`` and ``DBUS_SESSION_BUS_ADDRESS``
environments with debugging shells for your project, specify the following:

.. code:: yaml

   shell:

     # Environment variables to inherit from the host environment
     environment-inherit:
     - DISPLAY
     - DBUS_SESSION_BUS_ADDRESS


.. _project_plugins:

External Plugins
----------------
If your project makes use of any custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins, then the project must inform BuildStream
of the plugins it means to make use of and the origin from which it can be loaded.

Note that plugins with the same name from different origins are not permitted.


Core plugins
~~~~~~~~~~~~
Plugins provided by the BuildStream core need not be explicitly specified
here, but you may use this section to specify a minimal format version
to ensure that they provide the features which your project requires.

.. code:: yaml

   plugins:
   - origin: core

     # We require a new feature of the `git` source plugin, and
     # a new feature introduced in version 2 of the `patch` plugin.
     sources:
       git: 1
       patch: 2

     # ... And a new feature of the `script` element, added
     # in version 2 of it's own format version.
     elements:
       script: 2


Local Plugins
~~~~~~~~~~~~~
Local plugins are expected to be found in a subdirectory of the actual
BuildStream project. :mod:`Element <buildstream.element>` and
:mod:`Source <buildstream.source>` plugins should be stored in separate
directories to avoid namespace collisions.

The versions of local plugins are largely immaterial since they are
revisioned along with the project by the user, usually in a VCS like git.
However, for the sake of consistency with other plugin loading origins
we require that you specify a version, this can always be ``0`` for a local
plugin.


.. code:: yaml

   plugins:

   - origin: local
     path: plugins/sources

     # We want to use the `mysource` source plugin located in our
     # project's `plugins/sources` subdirectory.
     sources:
       mysource: 0


Pip Plugins
~~~~~~~~~~~
Plugins loaded from the ``pip`` origin are expected to be installed
separately on the host operating system using python's package management
system.

.. code:: yaml

   plugins:

   - origin: pip

     # Specify the name of the python package containing
     # the plugins we want to load. The name one would use
     # on the `pip install` command line.
     #
     package-name: potato

     # We again must specify a minimal format version for the
     # external plugin, it is allowed to be `0`.
     #
     elements:
       potato: 0


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

Options of type ``flags`` can be tested in conditional expressions using
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
The ``arch`` option type is special enumeration option which
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


.. _project_element_overrides:

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


.. _project_source_overrides:

Source Overrides
~~~~~~~~~~~~~~~~
Default values (overriding built-in defaults) can be set on a project
wide basis. The sources dictionary can be used to override plugin specific
configuration data as shown below.


.. code:: yaml

   sources:

     # Override default values for all git sources
     git:

       config:
         checkout-submodules: False


.. _project_builtin_defaults:

Builtin Defaults
----------------
BuildStream defines some default values for convenience, the default
values overridden by your project's ``project.conf`` are presented here:

  .. literalinclude:: ../../buildstream/data/projectconfig.yaml
     :language: yaml
