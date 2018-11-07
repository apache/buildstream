
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


Project specific value
----------------------
The ``projects`` key can be used to specify project specific configurations,
the supported configurations on a project wide basis are listed here.

.. _config_artifacts:

Artifact server
~~~~~~~~~~~~~~~
Although project's often specify a :ref:`remote artifact cache <artifacts>` in
their ``project.conf``, you may also want to specify extra caches.

Assuming that your host/server is reachable on the internet as ``artifacts.com``
(for example), there are two ways to declare remote caches in your user
configuration:

1. Adding global caches:

.. code:: yaml

   #
   # Artifacts
   #
   artifacts:
     # Add a cache to pull from
     - url: https://artifacts.com/artifacts:11001
       server-cert: server.crt
     # Add a cache to push/pull to/from
     - url: https://artifacts.com/artifacts:11002
       server-cert: server.crt
       client-cert: client.crt
       client-key: client.key
       push: true
     # Add another cache to pull from
     - url: https://anothercache.com/artifacts:8080
       server-cert: another_server.crt

.. note::

    Caches declared here will be used by **all** BuildStream project's on the user's
    machine and are considered a lower priority than those specified in the project
    configuration.


2. Specifying caches for a specific project within the user configuration:

.. code:: yaml

   projects:
     project-name:
       artifacts:
         # Add a cache to pull from
         - url: https://artifacts.com/artifacts:11001
           server-cert: server.crt
         # Add a cache to push/pull to/from
         - url: https://artifacts.com/artifacts:11002
           server-cert: server.crt
           client-cert: client.crt
           client-key: client.key
           push: true
         # Add another cache to pull from
         - url: https://ourprojectcache.com/artifacts:8080
           server-cert: project_server.crt


.. note::

    Caches listed here will be considered a higher priority than those specified
    by the project. Furthermore, for a given list of URLs, earlier entries will
    have higher priority.


Notice that the use of different ports for the same server distinguishes between
pull only access and push/pull access. For information regarding this and the
server/client certificates and keys, please see:
:ref:`Key pair for the server <server_authentication>`.



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
