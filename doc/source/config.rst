:orphan:

.. _config:


User Configuration
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


Project Specific Value
----------------------
The ``projects`` key can be used to specify project specific configurations,
the supported configurations on a project wide basis are listed here.


Artifact Server
~~~~~~~~~~~~~~~
The artifact server is usually specified by the project you build, but
it can be overridden on a per project basis using the same format
:ref:`described here <project_essentials_artifacts>`.

**Example**

.. code:: yaml

   projects:
     project-name:
       artifacts:
         url: https://artifacts.com/artifacts


Strict Build Plan
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


Default Configuration
---------------------
The default BuildStream configuration is specified here for reference:

  .. literalinclude:: ../../buildstream/data/userconfig.yaml
     :language: yaml
