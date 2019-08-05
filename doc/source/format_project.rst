
.. _projectconf:


Project configuration
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


.. _project_format_name:

Project name
~~~~~~~~~~~~
The project name is a unique symbol for your project and will
be used to distinguish your project from others in user preferences,
namspaceing of your project's artifacts in shared artifact caches,
and in any case where BuildStream needs to distinguish between multiple
projects.

The first thing to setup in your ``project.conf`` should be the name
of your project.

.. code:: yaml

   name: my-project-name

.. note::

   The project name may contain alphanumeric characters, dashes and
   underscores, and may not start with a leading digit.


.. _project_format_version:

Format version
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

   External :mod:`Element <buildstream.element>` and :mod:`Source <buildstream.source>`
   plugins also implement their own YAML configuration fragments and as
   such are revisioned separately from the core format. See :ref:`project_plugins`
   for details on specifying a minimum version of a specific plugin.

   Core :mod:`Elements <buildstream.element>` and :mod:`Sources <buildstream.source>`
   which are maintained and distributed as a part of BuildStream are revisioned
   under the same global ``format-version`` described here.


.. _project_element_path:

Element path
~~~~~~~~~~~~
To allow the user to structure their project nicely, BuildStream
allows the user to specify a project subdirectory where element
``.bst`` files are stored.

.. code:: yaml

   element-path: elements

Note that elements are referred to by their relative paths, whenever
elements are referred to in a ``.bst`` file or on the command line.


.. _project_format_ref_storage:

Ref storage
~~~~~~~~~~~
By default, BuildStream expects to read and write source references
directly in the :ref:`source declaration <format_sources>`, but this
can be inconvenient and prohibitive in some workflows.

Alternatively, BuildStream allows source references to be stored
centrally in a :ref:`project.refs file <projectrefs>` in the toplevel
:ref:`project directory <format_structure>`.

This can be controlled with the ``ref-storage`` option, which is
allowed to be configured with the following values:

* ``inline``

  Source references are stored directly in the
  :ref:`source declaration <format_sources>`

* ``project.refs``

  Source references are stored in the ``project.refs`` file, and
  junction source references are stored in the ``junction.refs`` file.

To enable storing of source references in ``project.refs``, add the
following to your ``project.conf``:

.. code:: yaml

  ref-storage: project.refs

.. note::

   The ``ref-storage`` configuration is available since :ref:`format version 8 <project_format_version>`


.. _configurable_warnings:

Configurable Warnings
~~~~~~~~~~~~~~~~~~~~~
Warnings can be configured as fatal using the ``fatal-warnings`` configuration item.
When a warning is configured as fatal, where a warning would usually be thrown instead an error will be thrown
causing the build to fail.

Individual warnings can be configured as fatal by setting ``fatal-warnings`` to a list of warnings.

.. code:: yaml

  fatal-warnings:
  - overlaps
  - ref-not-in-track
  - <plugin>:<warning>

BuildStream provides a collection of :class:`Core Warnings <buildstream.types.CoreWarnings>` which may be raised
by a variety of plugins. Other configurable warnings are plugin specific and should be noted within their individual documentation.

.. note::

  The ``fatal-warnings`` configuration is available since :ref:`format version 16 <project_format_version>`


.. _project_source_aliases:

Source aliases
~~~~~~~~~~~~~~
In order to abstract the download location of source code and
any assets which need to be downloaded, and also as a matter of
convenience, BuildStream allows one to create named aliases for
URLs which are to be used in the individual ``.bst`` files.

.. code:: yaml

   aliases:
     foo: git://git.foo.org/
     bar: http://bar.com/downloads/


Sandbox options
~~~~~~~~~~~~~~~
Sandbox options for the whole project can be supplied in
``project.conf`` in the same way as in an element. See :ref:`element configuration <format_sandbox>`
for more detail.

.. code:: yaml

   # Specify a user id and group id to use in the build sandbox.
   sandbox:
     build-uid: 1003
     build-gid: 1001

.. note::

   The ``sandbox`` configuration is available since :ref:`format version 6 <project_format_version>`


.. _project_essentials_artifacts:

Artifact server
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


.. _project_essentials_mirrors:

Mirrors
~~~~~~~
A list of mirrors can be defined that couple a location to a mapping of aliases to a
list of URIs, e.g.

.. code:: yaml

  mirrors:
  - name: middle-earth
    aliases:
      foo:
      - http://www.middle-earth.com/foo/1
      - http://www.middle-earth.com/foo/2
      bar:
      - http://www.middle-earth.com/bar/1
      - http://www.middle-earth.com/bar/2
  - name: oz
    aliases:
      foo:
      - http://www.oz.com/foo
      bar:
      - http://www.oz.com/bar

The order that the mirrors (and the URIs therein) are consulted is in the order
they are defined when fetching, and in reverse-order when tracking.

A default mirror to consult first can be defined via
:ref:`user config <config_default_mirror>`, or the command-line argument
:ref:`--default-mirror <invoking_bst>`.

.. note::

   The ``mirrors`` field is available since :ref:`format version 11 <project_format_version>`


.. _project_plugins:

External plugins
----------------
If your project makes use of any custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins, then the project must inform BuildStream
of the plugins it means to make use of and the origin from which they can be loaded.

Note that plugins with the same name from different origins are not permitted.


Local plugins
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


Pip plugins
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

.. note::

   The name of the option may contain alphanumeric characters
   underscores, and may not start with a leading digit.


Common properties
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

  .. note::

     The name of the variable to export may contain alphanumeric
     characters, dashes, underscores, and may not start with a leading
     digit.


.. _project_options_bool:

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


.. _project_options_enum:

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


.. _project_options_flags:

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


.. _project_options_arch:

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


.. _project_options_element_mask:

Element mask
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

Element default configuration
-----------------------------
The ``project.conf`` plays a role in defining elements by
providing default values and also by overriding values declared
by plugins on a plugin wide basis.

See the :ref:`composition <format_composition>` documentation for
more detail on how elements are composed.


.. _project_defaults_variables:

Variables
~~~~~~~~~
The defaults for :ref:`Variables <format_variables>` used in your
project is defined here.

.. code:: yaml

   variables:
     prefix: "/usr"


.. _project_defaults_environment:

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


Split rules
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


.. _project_overrides:

Overriding plugin defaults
--------------------------
Base attributes declared by element and source plugins can be overridden
on a project wide basis. This section explains how to make project wide
statements which augment the configuration of an element or source plugin.


.. _project_element_overrides:

Element overrides
~~~~~~~~~~~~~~~~~
The elements dictionary can be used to override variables, environments
or plugin specific configuration data as shown below.


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

Source overrides
~~~~~~~~~~~~~~~~
The sources dictionary can be used to override source plugin
specific configuration data as shown below.


.. code:: yaml

   sources:

     # Override default values for all git sources
     git:

       config:
         checkout-submodules: False

.. note::

   The ``sources`` override is available since :ref:`format version 1 <project_format_version>`


.. _project_shell:

Customizing the shell
---------------------
Since BuildStream cannot know intimate details about your host or about
the nature of the runtime and software that you are building, the shell
environment for debugging and testing applications may need some help.

The ``shell`` section allows some customization of the shell environment.

.. note::

   The ``shell`` section is available since :ref:`format version 1 <project_format_version>`


Interactive shell command
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


Environment assignments
~~~~~~~~~~~~~~~~~~~~~~~
In order to cooperate with your host environment, a debugging shell
sometimes needs to be configured with some extra knowledge inheriting
from your host environment.

This can be achieved by setting up the shell ``environment`` configuration,
which is expressed as a dictionary very similar to the
:ref:`default environment <project_defaults_environment>`, except that it
supports host side environment variable expansion in values.

.. note::

   The ``environment`` configuration is available since :ref:`format version 4 <project_format_version>`

For example, to share your host ``DISPLAY`` and ``DBUS_SESSION_BUS_ADDRESS``
environments with debugging shells for your project, specify the following:

.. code:: yaml

   shell:

     # Share some environment variables from the host environment
     environment:
       DISPLAY: '$DISPLAY'
       DBUS_SESSION_BUS_ADDRESS: '$DBUS_SESSION_BUS_ADDRESS'

Or, a more complex example is how one might share the host pulseaudio
server with a ``bst shell`` environment:

.. code:: yaml

   shell:

     # Set some environment variables explicitly
     environment:
       PULSE_SERVER: 'unix:${XDG_RUNTIME_DIR}/pulse/native'


Host files
~~~~~~~~~~
It can be useful to share some files on the host with a shell so that
it can integrate better with the host environment.

The ``host-files`` configuration allows one to specify files and
directories on the host to be bind mounted into the sandbox.

.. note::

   The ``host-files`` configuration is available since :ref:`format version 4 <project_format_version>`

.. warning::

   One should never mount directories where one expects to
   find data and files which belong to the user, such as ``/home``
   on POSIX platforms.

   This is because the unsuspecting user may corrupt their own
   files accidentally as a result. Instead users can use the
   ``--mount`` option of ``bst shell`` to mount data into the shell.


The ``host-files`` configuration is an ordered list of *mount specifications*.

Members of the list can be *fully specified* as a dictionary, or a simple
string can be used if only the defaults are required.

The fully specified dictionary has the following members:

* ``path``

  The path inside the sandbox. This is the only mandatory
  member of the mount specification.

* ``host_path``

  The host path to mount at ``path`` in the sandbox. This
  will default to ``path`` if left unspecified.

* ``optional``

  Whether the mount should be considered optional. This
  is ``False`` by default.


Here is an example of a *fully specified mount specification*:

.. code:: yaml

   shell:

     # Mount an arbitrary resolv.conf from the host to
     # /etc/resolv.conf in the sandbox, and avoid any
     # warnings if the host resolv.conf doesnt exist.
     host-files:
     - host_path: '/usr/local/work/etc/resolv.conf'
       path: '/etc/resolv.conf'
       optional: True

Here is an example of using *shorthand mount specifications*:

.. code:: yaml

   shell:

     # Specify a list of files to mount in the sandbox
     # directory from the host.
     #
     # If these do not exist on the host, a warning will
     # be issued but the shell will still be launched.
     host-files:
     - '/etc/passwd'
     - '/etc/group'
     - '/etc/resolv.conf'

Host side environment variable expansion is also supported:

.. code:: yaml

   shell:

     # Mount a host side pulseaudio server socket into
     # the shell environment at the same location.
     host-files:
     - '${XDG_RUNTIME_DIR}/pulse/native'


.. _project_builtin_defaults:

Builtin defaults
----------------
BuildStream defines some default values for convenience, the default
values overridden by your project's ``project.conf`` are presented here:

  .. literalinclude:: ../../buildstream/data/projectconfig.yaml
     :language: yaml
