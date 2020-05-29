
.. _user_config:


User configuration
==================
User configuration and preferences can be specified in a user provided
configuration file, and usually also on the command line.

Values specified in a user provided configuration file override the
defaults, while command line options take precedence over any other
specified configurations.


Configuration file
------------------
Users can provide a configuration file to override parameters in
the default configuration.

Unless a configuration file is explicitly specified on the command line when
invoking ``bst``, an attempt is made to load user specific configuration from
``$XDG_CONFIG_HOME/buildstream.conf``. On most Linux based systems, the location
will be ``~/.config/buildstream.conf``

.. note::

   If you have have multiple major versions of BuildStream installed, you
   can have separate configuration files in your ``${XDG_CONFIG_HOME}``.

   You can do this by naming them according to the major versions of
   BuildStream you have installed. BuildStream 1 will load it's configuration
   from ``$XDG_CONFIG_HOME/buildstream1.conf`` and BuildStream 2 will load
   it's configuration from ``$XDG_CONFIG_HOME/buildstream2.conf``, while
   any version will fallback to ``$XDG_CONFIG_HOME/buildstream.conf``.


Project specific value
----------------------
The ``projects`` key can be used to specify project specific configurations,
the supported configurations on a project wide basis are listed here.

.. _config_artifacts:

Artifact server
~~~~~~~~~~~~~~~
The project you build will often specify a :ref:`remote artifact cache
<artifacts>` already, but you may want to specify extra caches. There are two
ways to do this.  You can add one or more global caches:

**Example**

.. code:: yaml

   artifacts:
     url: https://artifacts.com/artifacts

Caches listed there will be considered lower priority than those specified
by the project configuration.

You can also add project-specific caches:

**Example**

.. code:: yaml

   projects:
     project-name:
       artifacts:
         - url: https://artifacts.com/artifacts1
         - url: ssh://user@artifacts.com/artifacts2
           push: true

Caches listed here will be considered higher priority than those specified
by the project.

If you give a list of URLs, earlier entries in the list will have higher
priority than later ones.

.. _user_config_strict_mode:

Strict build plan
~~~~~~~~~~~~~~~~~
The strict build plan option decides whether you want elements
to rebuild when their dependencies have changed. This is enabled
by default, but recommended to turn off in developer scenarios where
you might want to build a large system and test it quickly after
modifying some low level component.


**Example**

.. code:: yaml

   projects:
     project-name:
       strict: False


.. note::

   It is always possible to override this at invocation time using
   the ``--strict`` and ``--no-strict`` command line options.


.. _config_default_mirror:

Default Mirror
~~~~~~~~~~~~~~
When using :ref:`mirrors <project_essentials_mirrors>`, a default mirror can
be defined to be fetched first.
The default mirror is defined by its name, e.g.

.. code:: yaml

  projects:
    project-name:
      default-mirror: oz


.. note::

   It is possible to override this at invocation time using the
   ``--default-mirror`` command-line option.


Default configuration
---------------------
The default BuildStream configuration is specified here for reference:

  .. literalinclude:: ../../buildstream/data/userconfig.yaml
     :language: yaml
