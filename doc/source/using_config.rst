
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
Although project's often specify a :ref:`remote artifact cache <cache_servers>`
in their ``project.conf``, you may also want to specify extra caches.

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

.. _config_sources:

Source cache server
~~~~~~~~~~~~~~~~~~~
Similarly global and project specific source caches servers can be specified in
the user configuration.

1. Global source caches

.. code:: yaml

   #
   # Source caches
   #
   source-caches:
     # Add a cache to pull from
     - url: https://cache.com/sources:11001
       server-cert: server.crt
     # Add a cache to push/pull to/from
     - url: https://cache.com/sources:11002
       server-cert: server.crt
       client-cert: client.crt
       client-key: client.key
       push: true
     # Add another cache to pull from
     - url: https://anothercache.com/sources:8080
       server-cert: another_server.crt

2. Project specific source caches

.. code:: yaml

   projects:
     project-name:
       artifacts:
         # Add a cache to pull from
         - url: https://cache.com/sources:11001
           server-cert: server.crt
         # Add a cache to push/pull to/from
         - url: https://cache.com/sources:11002
           server-cert: server.crt
           client-cert: client.crt
           client-key: client.key
           push: true
         # Add another cache to pull from
         - url: https://ourprojectcache.com/sources:8080
           server-cert: project_server.crt

.. _user_config_remote_execution:

Remote execution
~~~~~~~~~~~~~~~~

The configuration for :ref:`remote execution <project_remote_execution>`
in ``project.conf`` can be provided in the user configuation. The global
configuration also has a ``pull-artifact-files`` option, which specifies when
remote execution is being performed whether to pull file blobs of artifacts, or
just the directory trees required to perform remote builds.

There is only one remote execution configuration used per project.

The project overrides will be taken in priority. The global
configuration will be used as fallback.

1. Global remote execution fallback:

.. code:: yaml

  remote-execution:
    execution-service:
      url: http://execution.fallback.example.com:50051
      instance-name: main
    storage-service:
      url: https://storage.fallback.example.com:11002
      server-cert: /keys/server.crt
      client-cert: /keys/client.crt
      client-key: /keys/client.key
      instance-name: main
    action-cache-service:
      url: http://cache.flalback.example.com:50052
      instance-name: main
    pull-artifact-files: True

2. Project override:

.. code:: yaml

  projects:
    some_project:
      remote-execution:
        execution-service:
          url: http://execution.some_project.example.com:50051
          instance-name: main
        storage-service:
          url: http://storage.some_project.example.com:11002
          instance-name: main
        action-cache-service:
          url: http://cache.some_project.example.com:50052
          instance-name: main


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


.. _config_local_cache:

Local cache expiry
~~~~~~~~~~~~~~~~~~
BuildStream locally caches artifacts, build trees, log files and sources within a
cache located at ``~/.cache/buildstream`` (unless a $XDG_CACHE_HOME environment
variable exists). When building large projects, this cache can get very large,
thus BuildStream will attempt to clean up the cache automatically by expiring the least
recently *used* artifacts.

By default, cache expiry will begin once the file system which contains the cache
approaches maximum usage. However, it is also possible to impose a quota on the local
cache in the user configuration. This can be done in two ways:

1. By restricting the maximum size of the cache directory itself.

For example, to ensure that BuildStream's cache does not grow beyond 100 GB,
simply declare the following in your user configuration (``~/.config/buildstream.conf``):

.. code:: yaml

  cache:
    quota: 100G

This quota defines the maximum size of the artifact cache in bytes.
Other accepted values are: K, M, G or T (or you can simply declare the value in bytes, without the suffix).
This uses the same format as systemd's
`resource-control <https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html>`_.

2. By expiring artifacts once the file system which contains the cache exceeds a specified usage.

To ensure that we start cleaning the cache once we've used 80% of local disk space (on the file system
which mounts the cache):

.. code:: yaml

  cache:
    quota: 80%


Default configuration
---------------------
The default BuildStream configuration is specified here for reference:

  .. literalinclude:: ../../src/buildstream/data/userconfig.yaml
     :language: yaml
