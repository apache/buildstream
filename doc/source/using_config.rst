
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


Remote services
---------------
BuildStream can be configured to cooperate with remote caches and
execution services.


.. _config_remote_auth:

Authentication
~~~~~~~~~~~~~~
BuildStream supports end to end encryption when communicating with remote
services.

All remote service configuration blocks come with an optional ``auth``
configuration block which allows one to specify the certificates
and keys required for encrypted traffic.

See the :ref:`server configuration documentation <server_authentication>` for
details on how the keys can be generated and managed on the server side.

The ``auth`` configuration block looks like this:

.. code:: yaml

   auth:
     server-cert: server.crt
     client-cert: client.crt
     client-key: client.key

**Attributes:**

* ``server-cert``

  The server certificate is used to decrypt traffic coming from the
  server.

* ``client-cert``

  The client certificate is used by the remote server to decrypt
  traffic being uploaded to the server.

  The remote server will have it's own copy of this certificate, but the
  client needs to send this certificate's identity to the server so that
  the server knows which certificate to use.

* ``client-key``

  The client key is used to encrypt traffic when uploading traffic
  to the server.

Normally, only the ``server-cert`` is required to securely *download* data
from remote cache services, while both the ``client-key`` and ``client-cert``
is required to securely *upload* data to the server.


.. _config_cache_servers:

Cache servers
~~~~~~~~~~~~~
BuildStream supports two types of cache servers, :ref:`source cache servers <config_source_caches>`
and :ref:`artifact cache servers <config_artifact_caches>`. These services allow you
to store sources and build artifacts for later reuse, and share them among your
peers.

.. important::

   **Storing and indexing**

   Cache servers are split into two separate services, the *index* and the *storage*.
   Sometimes these services are provided by the same server, and sometimes it is desirable
   to use different cache servers for indexing and storing data.

   In simple setups, it is possible to use the same cache server for indexing and storing
   of both sources and artifacts. However, when using :ref:`remote execution <user_config_remote_execution>`
   it is recommended to use the remote execution build cluster's ``storage-service`` as the *storage*
   service of your cache servers, which may require setting up your *index* service separately.

   When configuring cache servers, BuildStream will require both storage and indexing capabilities,
   otherwise no attempt will be made to fetch or push data to and from cache servers.

Cache server configuration is declared in the following way:

.. code:: yaml

   override-project-caches: false
   servers:
   - url: https://cache-server.com/cache:11001
     instance-name: main
     type: all
     push: true
     auth:
       server-cert: server.crt
       client-cert: client.crt
       client-key: client.key

**Attributes:**

* ``override-project-caches``

  Whether this user configuration overrides the project recommendations for
  :ref:`artifact caches <project_artifact_cache>` or :ref:`source caches <project_source_cache>`.

  If this is false (which is the default), then project recommended cache
  servers will be observed after user specified caches.

* ``servers``

  This is the list of cache servers in the configuration block, every entry
  in the block represents a server which will be accessed in the specified order.

  * ``url``

    Indicates the ``http`` or ``https`` url and optionally the port number of
    where the cache server is located.

  * ``instance-name``

    Instance names separate different shards on the same endpoint (``url``).

    The instance name is optional, and not all cache server implementations support
    instance names. The instance name should be given to you by the
    service provider of each service.

  * ``type``

    The type of service you intend to use this cache server for. If unspecified,
    the default value for this field is ``all``.

    * ``storage``

      Use this cache service for storage.

    * ``index``

      Use this cache service for index content expected to be present in one
      or more *storage* services.

    * ``all``

      Use this cache service for both indexing and storing data.

  * ``push``

    Set this to ``true`` if you intend to upload data to this cache server.

    Normally this requires additional credentials in the ``auth`` field.

  * ``auth``

    The :ref:`authentication attributes <config_remote_auth>` to connect to
    this server.


.. _config_cache_server_list:

Cache server lists
''''''''''''''''''
Cache servers are always specified as *lists* in the configuration, this allows
*index* and *storage* services to be declared separately, and also allows for
some redundancy.

**Example:**

.. code:: yaml

   - url: https://cache-server-1.com/index
     type: index
   - url: https://cache-server-1.com/storage
     type: storage
   - url: https://cache-server-2.com
     type: all

When downloading data from a cache server, BuildStream will iterate over each
*index* service one by one until it finds the reference to the data it is looking
for, and then it will iterate over each *storage* service one by one, downloading
the referenced data until all data is downloaded.

When uploading data to a cache server, BuildStream will first upload the data to
each *storage* service which was configured with the ``push`` attribute, and
upon successful upload, it will proceed to upload the references to the uploaded
data to each *index* service in the list.


.. _config_artifact_caches:

Artifact cache servers
~~~~~~~~~~~~~~~~~~~~~~
Using artifact :ref:`cache servers <config_cache_servers>` is an essential means of
*build avoidance*, as it will allow you to avoid building an element which has already
been built and uploaded to a common artifact server.

Artifact cache servers can be declared in different ways, with differing priorities.


Command line
''''''''''''
Various commands which involve connecting to artifact servers allow
:ref:`specifying remotes <invoking_specify_remotes>`, remotes specified
on the command line replace all user configuration.


Global caches
'''''''''''''
To declare the global artifact server list, use the ``artifacts`` key at the
toplevel of the user configuration.

.. code:: yaml

   #
   # Configure a global artifact server for pushing and pulling artifacts
   #
   artifacts:
     override-project-caches: false
     servers:
     - url: https://artifacts.com/artifacts:11001
       push: true
       auth:
         server-cert: server.crt
         client-cert: client.crt
         client-key: client.key


Project overrides
'''''''''''''''''
To declare artifact servers lists for individual projects, declare them
in the :ref:`project specific section <user_config_project_overrides>` of
the user configuration.

Artifact server lists declared in this section will only be used for
elements belonging to the specified project, and will be used instead of
artifact cache servers declared in the global caches.

.. code:: yaml

   #
   # Configure an artifact server for pushing and pulling artifacts from project "foo"
   #
   projects:
     foo:
       artifacts:
         override-project-caches: false
         servers:
         - url: https://artifacts.com/artifacts:11001
           push: true
           auth:
             server-cert: server.crt
             client-cert: client.crt
             client-key: client.key


Project recommendations
'''''''''''''''''''''''
Projects can :ref:`recommend artifact cache servers <project_artifact_cache>` in their
individual project configuration files.

These will only be used for elements belonging to their respective projects, and
are the lowest priority configuration.


.. _config_source_caches:

Source cache servers
~~~~~~~~~~~~~~~~~~~~
Using source :ref:`cache servers <config_cache_servers>` enables BuildStream to cache
source code referred to by your project and share those sources with peers who have
access to the same source cache server.

This can optimize your build times in the case that it is determined that an element needs
to be rebuilt because of changes in the dependency graph, as BuildStream will first attempt
to download the source code from the cache server before attempting to obtain it from an
external source, which may suffer higher latencies.

Source cache servers can be declared in different ways, with differing priorities.


Command line
''''''''''''
Various commands which involve connecting to source cache servers allow
:ref:`specifying remotes <invoking_specify_remotes>`, remotes specified
on the command line replace all user configuration.


Global caches
'''''''''''''
To declare the global source cache server list, use the ``source-caches`` key at the
toplevel of the user configuration.

.. code:: yaml

   #
   # Configure a global source cache server for pushing and pulling sources
   #
   source-caches:
     override-project-caches: false
     servers:
     - url: https://sources.com/sources:11001
       push: true
       auth:
         server-cert: server.crt
         client-cert: client.crt
         client-key: client.key


Project overrides
'''''''''''''''''
To declare source cache servers lists for individual projects, declare them
in the :ref:`project specific section <user_config_project_overrides>` of
the user configuration.

Source cache server lists declared in this section will only be used for
elements belonging to the specified project, and will be used instead of
source cache servers declared in the global caches.

.. code:: yaml

   #
   # Configure a source cache server for pushing and pulling sources from project "foo"
   #
   projects:
     foo:
       source-caches:
         override-project-caches: false
         servers:
         - url: https://sources.com/sources:11001
           push: true
           auth:
             server-cert: server.crt
             client-cert: client.crt
             client-key: client.key


Project recommendations
'''''''''''''''''''''''
Projects can :ref:`recommend source cache servers <project_source_cache>` in their
individual project configuration files.

These will only be used for elements belonging to their respective projects, and
are the lowest priority configuration.


.. _user_config_remote_execution:

Remote execution
~~~~~~~~~~~~~~~~
BuildStream supports building remotely using the
`Google Remote Execution API (REAPI). <https://github.com/bazelbuild/remote-apis>`_.

You can configure the remote execution services globally in your user configuration
using the ``remote-execution`` key, like so:

.. code:: yaml

   remote-execution:
     pull-artifact-files: True
     execution-service:
       url: http://execution.fallback.example.com:50051
       instance-name: main
     storage-service:
       url: https://storage.fallback.example.com:11002
       instance-name: main
       auth:
         server-cert: /keys/server.crt
         client-cert: /keys/client.crt
         client-key: /keys/client.key
     action-cache-service:
       url: http://cache.flalback.example.com:50052
       instance-name: main

**Attributes:**

* ``pull-artifact-files``

  This determines whether you want the artifacts which were built remotely
  to be downloaded into the local CAS, so that it is ready for checkout
  directly after a built completes.

  If this is set to ``false``, then you will need to download the artifacts
  you intend to use with :ref:`bst artifact checkout <invoking_artifact_checkout>`
  after your build completes.

* ``execution-service``

  A :ref:`service configuration <user_config_remote_execution_service>` specifying
  how to connect with the main *execution service*, this service is the main controlling
  entity in a remote execution build cluster.

* ``storage-service``

  A :ref:`service configuration <user_config_remote_execution_service>` specifying
  how to connect with the *Content Addressable Storage* service, this is where build
  input and output is stored on the remote execution build cluster.

  This service is compatible with the *storage* service offered by
  :ref:`cache servers <config_cache_servers>`.

* ``action-cache-service``

  A :ref:`service configuration <user_config_remote_execution_service>` specifying
  how to connect with the *action cache*, this service stores information about
  activities which clients request be performed by workers on the remote execution
  build cluster, and results of completed operations.

  This service is optional in a remote execution build cluster, if your remote
  execution service provides an action cache, then you should configure it here.


.. _user_config_remote_execution_service:

Remote execution service configuration
''''''''''''''''''''''''''''''''''''''
Each of the distinct services are described by the same configuration block,
which looks like this:

.. code:: yaml

   url: https://storage.fallback.example.com:11002
   instance-name: main
   auth:
     server-cert: /keys/server.crt
     client-cert: /keys/client.crt
     client-key: /keys/client.key

**Attributes:**

* ``url``

  Indicates the ``http`` or ``https`` url and optionally the port number of
  where the service is located.

* ``instance-name``

  The instance name is optional. Instance names separate different shards on
  the same endpoint (``url``). The instance name should be given to you by the
  service provider of each service.

  Not all service providers support instance names.

* ``auth``

  The :ref:`authentication attributes <config_remote_auth>` to connect to
  this server.


.. _user_config_project_overrides:

Project specific value
----------------------
The ``projects`` key can be used to specify project specific configurations,
the supported configurations on a project wide basis are listed here.

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
