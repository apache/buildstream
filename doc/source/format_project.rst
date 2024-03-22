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
namespacing of your project's artifacts in shared artifact caches,
and in any case where BuildStream needs to distinguish between multiple
projects.

The first thing to setup in your ``project.conf`` should be the name
of your project.

.. code:: yaml

   name: my-project-name

The project name may contain alphanumeric characters, dashes and
underscores, and may not start with a leading digit.

.. attention::

   The project name must be specified in the ``project.conf`` and
   cannot be :ref:`included <format_directives_include>` from a separate file.


.. _project_min_version:

Minimum version
~~~~~~~~~~~~~~~
The BuildStream format is guaranteed to be backwards compatible
with any earlier minor point releases, which is to say that
BuildStream 1.4 can read projects written for BuildStream 1.0,
and that BuildStream 2.2 can read projects written for BuildStream 2.0.

Projects are required to specify the minimum version of BuildStream
which it requires, this allows project authors to convey a useful
error message to their users and peers, in the case that a user needs
to get a newer version of BuildStream in order to work with a given
project.

The project's minimum required BuildStream version must be specified
in ``project.conf`` using the ``min-version`` field, e.g.:

.. code:: yaml

  # This project uses features which were added in 2.2
  min-version: 2.2

It is recommended that when using new features, always consult this
documentation and observe which BuildStream version a feature you are
using was added in. If a feature in the BuildStream YAML format is
not documented with a specific *Since* version, you can assume that
it has been there from the beginning.


.. note::

   External :mod:`Element <buildstream.element>` and :mod:`Source <buildstream.source>`
   plugins also implement their own YAML configuration fragments and as
   such are revisioned separately from the core format.

.. attention::

   The ``min-version`` must be specified in the ``project.conf`` and
   cannot be :ref:`included <format_directives_include>` from a separate file.


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

.. attention::

   The ``element-path`` can only be specified in the ``project.conf`` and
   cannot be :ref:`included <format_directives_include>` from a separate file.


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

.. attention::

   **Storing subproject source references in project.refs**

   When using the ``project.refs`` file, it is possible to override the
   references in subprojects by editing the ``project.refs`` file directly
   or by using :ref:`bst source track --cross-junctions <invoking_source_track>`,
   this can be practical to try out fresher versions of components which
   are maintained in a subproject.

   It should be noted however that overridden subproject source references listed
   in your ``project.refs`` file will be ignored by projects which use your project
   as a subproject.


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

If you want this project's alias definitions to also be used for subprojects,
see :ref:`Mapping source aliases of subprojects <project_junctions_source_aliases>`.


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


.. _project_artifact_cache:

Artifact server
~~~~~~~~~~~~~~~
When maintaining a BuildStream project, it can be convenient to downstream users
of your project to provide access to a :ref:`cache server <cache_servers>` you maintain.

The project can provide *recommended* artifact cache servers through project configuration
using the same semantics as one normally uses in the ``servers`` list of the
:ref:`cache server user configuration <config_cache_servers>`:

.. code:: yaml

  #
  # A remote cache from which to download prebuilt artifacts
  #
  artifacts:
  - url: https://foo.com:11001
    auth:
      server-cert: server.crt

.. attention::

   Unlike user configuration, the filenames provided in the :ref:`auth <config_remote_auth>`
   configuration block are relative to the :ref:`project directory <format_structure>`.

   It is recommended to include public keys such as the ``server-cert`` along with your
   project so that downstream users can have automatic read access to your project.

   To provide write access to downstream users, it is recommended that the required
   private keys such as the ``client-key`` be provided to users out of band,
   and require that users configure write access separately in their own
   :ref:`user configuration <config_cache_servers>`.


.. _project_source_cache:

Source cache server
~~~~~~~~~~~~~~~~~~~
In the same way as artifact cache servers, the project can provide *recommended* source cache
servers through project configuration using the same semantics as one normally uses in the
``servers`` list of the :ref:`cache server user configuration <config_cache_servers>`:

.. code:: yaml

  #
  # A remote cache from which to download prestaged sources
  #
  source-caches:
  - url: https://foo.com:11001
    auth:
      server-cert: server.crt

.. attention::

   Unlike user configuration, the filenames provided in the :ref:`auth <config_remote_auth>`
   configuration block are relative to the :ref:`project directory <format_structure>`.

   It is recommended to include public keys such as the ``server-cert`` along with your
   project so that downstream users can have automatic read access to your project.

   To provide write access to downstream users, it is recommended that the required
   private keys such as the ``client-key`` be provided to users out of band,
   and require that users configure write access separately in their own
   :ref:`user configuration <config_cache_servers>`.


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

The mirrors can be overridden on a per project basis using
:ref:`user configuration <config_mirrors>`. One can also specify which mirror should
be used first in the :ref:`user configuration <config_default_mirror>`, or using
the  :ref:`--default-mirror <invoking_bst>` command-line argument.

If you want this project's mirrors to also be used for subprojects,
see :ref:`Mapping source aliases of subprojects <project_junctions_source_aliases>`.


.. _project_plugins:

Loading plugins
---------------
If your project makes use of any custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins, then the project must inform BuildStream
of the plugins it means to make use of and the origin from which they can be loaded.

Note that plugins with the same name from different origins are not permitted.

.. attention::

   The plugins can only be specified in the ``project.conf`` and cannot be
   :ref:`included <format_directives_include>` from a separate file.


.. _project_plugins_local:

Local plugins
~~~~~~~~~~~~~
Local plugins are expected to be found in a subdirectory of the actual
BuildStream project. :mod:`Element <buildstream.element>` and
:mod:`Source <buildstream.source>` plugins should be stored in separate
directories to avoid namespace collisions, you can achieve this by
specifying a separate *origin* for sources and elements.

.. code:: yaml

   plugins:

   - origin: local
     path: plugins/sources

     # We want to use the `mysource` source plugin located in our
     # project's `plugins/sources` subdirectory.
     sources:
     - mysource

There is no strict versioning policy for plugins loaded from the local
origin because the plugin is provided with the project data and as such,
it is considered to be completely deterministic.

Usually your project will be managed by a VCS like git, and any changes
to your local plugins may have an impact on your project, such as changes
to the artifact cache keys produced by elements which use these plugins.
Changes to plugins might provide new YAML configuration options, changes
in the semantics of existing configurations or even removal of existing
YAML configurations.


.. _project_plugins_pip:

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

     # We again must specify specifically which plugins we
     # want loaded from this origin.
     #
     elements:
     - starch

Unlike local plugins, plugins loaded from the ``pip`` origin are
loaded from the active *python environment*, and as such you do not
usually have full control over the plugins your project uses unless
one uses strict :ref:`version constraints <project_plugins_pip_version_constraints>`.

The official plugin packages maintained by the BuildStream community are
guaranteed to be fully API stable. If one chooses to load these plugins
from the ``pip`` origin, then it is recommended to use *minimal bound dependency*
:ref:`constraints <project_plugins_pip_version_constraints>` when using
official plugin packages so as to be sure that you have access to all the
features you intend to use in your project.


.. _project_plugins_pip_version_constraints:

Versioning constraints
''''''''''''''''''''''
When loading plugins from the ``pip`` plugin origin, it is possible to
specify constraints on the versions of packages you want to load
your plugins from.

The syntax for specifying versioning constraints is the same format supported by
the ``pip`` package manager.

.. note::

   In order to be certain that versioning constraints work properly, plugin
   packages should be careful to adhere to `PEP 440, Version Identification and Dependency
   Specification <https://www.python.org/dev/peps/pep-0440/>`_.

Here are a couple of examples:

**Specifying minimal bound dependencies**:

.. code:: yaml

   plugins:

   - origin: pip

     # This project uses the API stable potato project and
     # requires features from at least version 1.2
     #
     package-name: potato>=1.2

**Specifying exact versions**:

.. code:: yaml

   plugins:

   - origin: pip

     # This project requires plugins from the potato
     # project at exactly version 1.2.3
     #
     package-name: potato==1.2.3

**Specifying version constraints**:

.. code:: yaml

   plugins:

   - origin: pip

     # This project requires plugins from the potato
     # project from version 1.2.3 onward until 1.3.
     #
     package-name: potato>=1.2.3,<1.3

.. important::

   **Unstable plugin packages**

   When using unstable plugins loaded from the ``pip`` origin, the installed
   plugins can sometimes be incompatible with your project.

   **Use virtual environments**

   Your operating system's default python environment can only have one
   version of a given package installed at a time, if you work on multiple
   BuildStream projects on the same host, they may not agree on which versions
   of plugins to use.

   In order to guarantee that you can use a specific version of a plugin,
   you may need to install BuildStream into a `virtual environment
   <https://docs.python.org/3/tutorial/venv.html>`_ in order to control which
   python package versions are available when using your project.

   Follow `these instructions
   <https://buildstream.build/source_install.html#installing-in-virtual-environments>`_
   to install BuildStream in a virtual environment.

   **Possible junction conflicts**

   If you have multiple projects which are connected through
   :mod:`junction <elements.junction>` elements, these projects can disagree
   on which version of a plugin is needed from the ``pip`` origin.

   Since only one version of a given plugin *package* can be installed
   at a time in a given *python environment*, you must ensure that all
   projects connected through :mod:`junction <elements.junction>` elements
   agree on which versions of API unstable plugin packages to use.


.. _project_plugins_junction:

Junction plugins
~~~~~~~~~~~~~~~~
Junction plugins are loaded from another project which your project has a
:mod:`junction <elements.junction>` declaration for. Plugins are loaded directly
from the referenced project, the source and element plugins listed will simply
be loaded from the subproject regardless of how they were defined in that project.

Plugins loaded from a junction might even come from another junction and
be *deeply nested*.

.. code:: yaml

   plugins:

   - origin: junction

     # Specify the local junction name declared in your
     # project as the origin from where to load plugins from.
     #
     junction: subproject-junction.bst

     # Here we want to get the `frobnicate` element
     # from the subproject and use it in our project.
     #
     elements:
     - frobnicate

Plugins loaded across junction boundaries will be loaded in the
context of your project, and any default values set in the ``project.conf``
of the junctioned project will be ignored when resolving the
defaults provided with element plugins.

It is recommended to use :ref:`include directives <format_directives_include>`
in the case that the referenced plugins from junctioned projects depend
on variables defined in the project they come from, in this way you can include
variables needed by your plugins into your own ``project.conf``.

.. tip::

   **Distributing plugins as projects**

   It is encouraged that people use BuildStream projects to distribute plugins
   which are intended to be shared among projects, especially when these plugins
   are not guaranteed to be completely API stable. This can still be done while
   also distributing your plugins as :ref:`pip packages <project_plugins_pip>` at
   the same time.

   This can be achieved by simply creating a repository or tarball which
   contains only the plugins you want to distribute, along with a ``project.conf``
   file declaring these plugins as :ref:`local plugins <project_plugins_local>`.

   Using plugins which are distributed as local plugins in a BuildStream project
   ensures that you always have full control over which exact plugin your
   project is using at all times, without needing to store the plugin as a
   :ref:`local plugin <project_plugins_local>` in your own project.


.. _project_plugins_deprecation:

Suppressing deprecation warnings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Plugins can be deprecated over time, and using deprecated plugins will
trigger a warning when loading elements and sources which use
deprecated plugin kinds.

These deprecation warnings can be suppressed for the entire plugin
origin or on a per plugin kind basis.

To suppress all deprecation warnings from the origin, set the
``allow-deprecated`` flag for the origin as follows:

.. code:: yaml

   plugins:

   - origin: local
     path: plugins/sources

     # Suppress deprecation warnings for any plugins loaded here
     allow-deprecated: True

     sources:
     - mysource


In order to suppress deprecation warnings for a single element or
source kind within an origin, you will have to use a dictionary
to declare the specific plugin kind and set the ``allow-deprecated`` flag
on that dictionary as follows:

.. code:: yaml

   plugins:

   - origin: pip
     package-name: potato

     # Here we use a dictionary to declare the "starch"
     # element kind, and specify that it is allowed to
     # be deprecated.
     #
     elements:
     - kind: starch
       allow-deprecated: True


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

Project options can be specified on the command line using
:ref:`bst --option ... <invoking_bst>`

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
The ``arch`` option type is a special enumeration option which defaults via
`uname -m` results to the following list.

* aarch32
* aarch64
* aarch64-be
* power-isa-be
* power-isa-le
* sparc-v9
* x86-32
* x86-64

The reason for this, opposed to using just `uname -m`, is that we want an
OS-independent list, as well as several results mapping to the same architecture
(e.g. i386, i486 etc. are all x86-32). It does not support assigning any default
in the project configuration.

.. code:: yaml

   options:
     machine_arch:
       type: arch
       description: The machine architecture
       values:
       - aarch32
       - aarch64
       - x86-32
       - x86-64


Architecture options can be tested with the same expressions
as other Enumeration options.


.. _project_options_os:

OS
~~

The ``os`` option type is a special enumeration option, which defaults to the
results of `uname -s`. It does not support assigning any default in the project
configuration.

.. code:: yaml

    options:
      machine_os:
        type: os
        description: The machine OS
        values:
        - Linux
        - SunOS
        - Darwin
        - FreeBSD

Os options can be tested with the same expressions as other Enumeration options.


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


.. _project_junctions:

Junctions
---------
In this section of ``project.conf``, we can define the relationship a project
has with :mod:`junction <elements.junction>` elements in the same project, or
even in subprojects.

Sometimes when your project has multiple :mod:`junction <elements.junction>` elements,
a situation can arise where you have multiple instances of the same project loaded
at the same time. In most cases, you will want to reconcile this conflict by ensuring
that your projects share the same junction. In order to reconcile conflicts by
ensuring nested junctions to the same project are shared, please refer to
:ref:`the documentation on nested junctions <core_junction_nested>`.

In some exceptional cases, it is entirely intentional and appropriate to use
the same project more than once in the same build pipeline. The attributes
in the ``junctions`` group here in ``project.conf`` provide some tools you can
use to explicitly allow the coexistence of the same project multiple times.


Duplicate junctions
~~~~~~~~~~~~~~~~~~~
In the case that you are faced with an error due to subprojects sharing
a common sub-subproject, you can use the ``duplicates`` configuration
in order to allow the said project to be loaded twice.

**Example**:

.. code:: yaml

   junctions:

     duplicates:

       # Here we use the packaging tooling completely separately from
       # the payload that we are packaging, they are never staged to
       # the same location in a given sandbox, and as such we would
       # prefer to allow the 'runtime' project to be loaded separately.
       #
       # This statement will ensure that loading the 'runtime' project
       # from these two locations will not produce any errors.
       #
       runtime:
       - payload.bst:runtime.bst
       - packaging.bst:runtime.bst

When considering duplicated projects in the same pipeline, all instances
of the said project need to be marked as ``duplicates`` in order to avoid
a *conflicting junction error* at load time.

.. tip::

   The declaration of ``duplicates`` is inherited by any dependant projects
   which may later decide to depend on your project.

   If you depend on a project which itself has ``duplicates``, and you need
   to duplicate it again, then you only need to declare the new duplicate,
   you do not need to redeclare duplicates redundantly.


Internal junctions
~~~~~~~~~~~~~~~~~~
Another way to avoid *conflicting junction errors* when you know that your
subproject should not conflict with other instances of the same subproject,
is to declare the said subproject as *internal*.

**Example**:

.. code:: yaml

   junctions:

     # Declare this subproject as "internal" because we know
     # that we only use it for build dependencies, and as such
     # we know that it cannot collide with elements in dependant
     # projects.
     #
     internal:
     - special-compiler.bst

When compared to *duplicates* above, *internal* projects have the advantage
of never producing any *conflicting junction errors* in dependant projects
(reverse dependency projects).

This approach is preferrable in cases where you know for sure that dependant
projects will not be depending directly on elements from your internal
subproject.

.. attention::

   Declaring a junction as *internal* is a promise that dependant projects
   will not accrue runtime dependencies on elements in your *internal* subproject.


.. _project_junctions_source_aliases:

Mapping source aliases of subprojects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:mod:`junction <elements.junction>` elements allow source aliases of subprojects
to be mapped to aliases of the parent project. This makes it possible to control
the translation of aliases to URLs including mirror configuration across multiple
project levels.

To ensure that there are mappings for all aliases of all subprojects, you can set the
``disallow-subproject-uris`` flag in the ``junctions`` group here in ``project.conf``.

top-level

.. code:: yaml

   junctions:
     disallow-subproject-uris: True

This will raise an error if an alias without a mapping is encountered. This flag
is applied recursively across all junctions.

It also configures ``unaliased-url`` as a fatal warning in all subprojects to
ensure that the current project is in full control over all source URLs.
As the fatal warning configuration contributes to the cache key, this flag will
affect the cache key of subprojects that haven't already configured
``unaliased-url`` as a fatal warning.


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
which environment variables do not affect build output, and are thus
not considered in the calculation of artifact keys can be defined here.

.. code:: yaml

   environment-nocache:
   - MAXJOBS

Note that the ``environment-nocache`` list only exists so that we can
control parameters such as ``make -j ${MAXJOBS}``, allowing us to control
the number of jobs for a given build without affecting the resulting
cache key.


.. _project_split_rules:

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


.. _project_shell:

Customizing the shell
---------------------
Since BuildStream cannot know intimate details about your host or about
the nature of the runtime and software that you are building, the shell
environment for debugging and testing applications may need some help.

The ``shell`` section allows some customization of the shell environment.


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


.. _project_default_targets:

Default targets
---------------
When running BuildStream commands from a project directory or subdirectory
without specifying any target elements on the command line, the default targets
of the project will be used.  The default targets can be configured in the
``defaults`` section as follows:

.. code:: yaml

   defaults:

     # List of default target elements
     targets:
     - app.bst

If no default targets are configured in ``project.conf``, BuildStream commands
will default to all ``.bst`` files in the configured element path.

Commands that cannot support junctions as target elements (``bst build``,
``bst artifact push``, and ``bst artifact pull``) ignore junctions in the list
of default targets.

When running BuildStream commands from a workspace directory (that is not a
BuildStream project directory), project default targets are not used and the
workspace element will be used as the default target instead.

``bst artifact checkout``, ``bst source checkout``, and ``bst shell`` are
currently limited to a single target element and due to this, they currently
do not use project default targets.  However, they still use the workspace
element as default target when run from a workspace directory.


.. _project_builtin_defaults:

Builtin defaults
----------------
BuildStream defines some default values for convenience, the default
values overridden by your project's ``project.conf`` are presented here:

  .. literalinclude:: ../../src/buildstream/data/projectconfig.yaml
     :language: yaml
