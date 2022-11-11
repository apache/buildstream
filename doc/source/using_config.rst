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


.. _user_config:


User configuration
==================
User configuration and preferences can be specified in a user provided
configuration file, and in most cases these preferences can be overridden
using :ref:`command line options <commands>`.

Values that are not specified in a user configuration file assume
their :ref:`default values <config_defaults>`.


Configuration file
------------------
Unless a configuration file is explicitly specified on the :ref:`command line <invoking_bst>`
when invoking ``bst``, an attempt is made to load user specific configuration from
``$XDG_CONFIG_HOME/buildstream.conf``. On most Linux based systems, the location
will be ``~/.config/buildstream.conf``

.. note::

   If you have have multiple major versions of BuildStream installed, you
   can have separate configuration files in your ``${XDG_CONFIG_HOME}``.

   You can do this by naming them according to the major versions of
   BuildStream you have installed. BuildStream 1 will load its configuration
   from ``$XDG_CONFIG_HOME/buildstream1.conf`` and BuildStream 2 will load
   its configuration from ``$XDG_CONFIG_HOME/buildstream2.conf``, while
   any version will fallback to ``$XDG_CONFIG_HOME/buildstream.conf``.



Working directories
-------------------
The working directories control where BuildStream will store data. While
these will have sane defaults, you may want to change these directories
depending on your partitioning scheme and where you may have extra space.

Environment variables and ``~/`` home directory expressions are supported
when specifying working directories.

Working directories are configured at the toplevel of your configuration file, like so:

.. code:: yaml

   #
   # Configure working directories
   #
   sourcedir: ~/buildstream/sources


Attributes
~~~~~~~~~~

* ``sourcedir``

  This is the location where BuildStream stores the source code it downloads
  for builds.

* ``logdir``

  This is the location where BuildStream stores log files of build command
  output and basically logs pertaining to any activity BuildStream orchestrates.

* ``cachedir``

  This is the location where BuildStream stores the local *CAS* (*Content Addressable Storage*).

  The *CAS* is used to cache anything and everything which BuildStream may
  reuse at a later time.

  .. attention::

     While it may be beneficial at times to delete the entire cache directory
     manually in order to free up disk space, one should keep in mind that
     the ``sourcedir`` and ``logdir`` are configured as subdirectories of
     this directory when default configuration is used.

     Take care not to accidentally remove all your cached downloaded sources
     when deleting your cache.

* ``workspacedir``

  A default location for :ref:`opening workspaces <invoking_workspace_open>`.

  .. note::

     By default this is configured to ``.``, which is to say workspaces are
     created as a subdirectory of the current working directory by default.

     Because of this, the ``workspacedir`` directory is the only directory
     which is allowed to be declared as a relative path.


.. _config_local_cache:

Cache control
-------------
Beyond deciding what directory you intend to place the cache, there are
some controls on what is cached locally and how.

These are controlled by the attributes of a ``cache`` dictionary at the
toplevel of your configuration file, like so:

.. code::

   #
   # Control the cache
   #
   cache:

     # Allow using as much free space as possible
     quota: infinity

     # Avoid pulling large amounts of data we don't need locally
     pull-buildtrees: False

     #
     # Avoid caching build trees if we don't need them
     cache-buildtrees: auto

     #
     # Support CAS server as remote cache
     # Useful to minimize network traffic with remote execution
     # or to work with limited local disk space
     storage-service:
       url: https://cache-server.com/cas:11001
       auth:
         server-cert: server.crt
         client-cert: client.crt
         client-key: client.key


Attributes
~~~~~~~~~~

* ``quota``

  This controls how much data you allow BuildStream to cache locally.

  An attempt will be made to error out instead of exceeding the maximum
  quota which the user has allowed here. Given that it is impossible for
  BuildStream to know how much data a given build will create, this quota
  is implemented on a best effort basis.

  The ``quota`` can be specified in multiple ways:

  * The special ``infinity`` value

    This default value states that BuildStream can use as much space as
    is available on the filesystem where the cache resides.

  * A number in bytes.

  * A human readable number, suffixed in K, M, G or T

    E.g. ``250K`` being 250 kilobytes, ``100M`` being 100 megabytes, etc.

  * A percentage value, e.g. ``80%``

    Percentage values are taken to represent a percentage of the partition
    size on the filesystem where the cache has been configured.

* ``pull-buildtrees``

  Whether to pull *build trees* when downloading remote artifacts.

  The *build tree* of an artifact is the directory where a build took
  place, this is useful for :ref:`running a build shell <invoking_shell>`
  in order to observe how an element was built or to debug how a
  build failed if the build failed remotely.

  Since build trees are rather expensive, the default is to not pull
  build trees for every artifact. If you need a build tree that exists
  remotely, it will be possible to download it as an option at the
  time you run a command which requires it.

* ``cache-buildtrees``

  Whether to cache build trees when creating artifacts, if build trees
  are cached locally and the client is configured to push to remote servers,
  then build trees will be pushed along with any uploaded artifacts.

  This configuration has three possible values:

  * ``never``: Never cache build trees
  * ``auto``: Only cache the build trees where necessary (e.g. for failed builds)
  * ``always``: Always cache the build tree.

* ``storage-service``

  An optional :ref:`service configuration <user_config_remote_execution_service>`
  to use a *Content Addressable Storage* service as a remote cache. Write access
  is required.

  This service is compatible with the *storage* service offered by
  :ref:`cache servers <config_cache_servers>`.

  Without this option, all content is stored in the local cache. This includes
  CAS objects from fetched sources, build outputs and pulled artifacts.
  With this option, content is primarily stored in the remote cache and the
  local cache is populated only as needed. E.g. ``bst artifact checkout``
  will download CAS objects on demand from the remote cache.
  This feature is incompatible with offline operation.

  This is primarily useful in combination with
  :ref:`remote execution <user_config_remote_execution>` to minimize downloads
  of build outputs, which may not be needed locally. The elimination of
  unnecessary downloads reduces total build time, especially if the bandwidth
  between the local system and the remote execution cluster is limited.

  .. tip::

     Skip the ``storage-service`` option in the
     :ref:`remote execution <user_config_remote_execution>` configuration to
     use the same CAS service for caching and remote execution.

  It is also possible to configure this with local builds without remote
  execution. This enables operation with a small local cache even with large
  projects. However, for local builds this can result in a longer total build
  time due to additional network transfers. This is only recommended with a
  high bandwidth connection to a storage-service, ideally in a local network.


Scheduler controls
------------------
Controls related to how the scheduler works are exposed as attributes of the
toplevel ``scheduler`` dictionary, like so:

.. code:: yaml

   #
   # Control the scheduler
   #
   scheduler:

     # Allow building up to four seperate elements at a time
     builders: 4

     # Continue building as many elements as possible if anything fails
     on-error: continue


Attributes
~~~~~~~~~~

* ``fetchers``

  The number of concurrent tasks which download sources or artifacts.

* ``pushers``

  The number of concurrent tasks which upload sources or artifacts.

* ``builders``

  The number of concurrent tasks which build elements.

  .. note::

     This does not control the number of processes in the scope of the
     build of a single element, but rather the number of elements which
     may be built in parallel.

* ``network-retries``

  The number of times to retry a task which failed due to network connectivity issues.

* ``on-error``

  What to do when a task fails and BuildStream is running in non-interactive mode. This can
  be set to the following values:

  * ``continue``: Continue with other tasks, a summary of errors will be printed at the end
  * ``quit``: Quit after all ongoing tasks have completed
  * ``terminate``: Abort any ongoing tasks and exit immediately

  .. note::

     If BuildStream is running in interactive mode, then the ongoing build will be suspended
     and the user will be prompted and asked what to do when a task fails.

     Interactive mode is automatically enabled if BuildStream is connected to a terminal
     rather than being run automatically, or, it can be specified on the :ref:`command line <invoking_bst>`.


Build controls
--------------
Some aspects about how elements get built can be controlled by attributes of the ``build``
dictionary at the toplevel, like so:

.. code:: yaml

   #
   # Build controls
   #
   build:

     #
     # Allow up to 4 parallel processes to execute within the scope of one build
     #
     max-jobs: 4


Attributes
~~~~~~~~~~

* ``max-jobs``

  This is a best effort attempt to instruct build systems on how many parallel
  processes to use when building an element.

  It is supported by most popular build systems such as ``make``, ``cmake``, ``ninja``,
  etc, via environment variables such as ``MAXJOBS`` and similar command line options.

  When using the special value ``0``, BuildStream will allocate the number of threads
  available on the host and limit this with a hard coded value of ``8``, which was
  found to be an optimial number when building even on hosts with many cores.

* ``dependencies``

  This instructs what dependencies of the target elements should be built, valid
  values for this attribute are:

  * ``none``: Only build elements required to generate the expected target artifacts
  * ``all``: Build elements even if they are build dependencies of artifacts which are already cached


Fetch controls
--------------
Some aspects about how sources get fetched can be controlled by attributes of the ``fetch``
dictionary at the toplevel, like so:

.. code:: yaml

   #
   # Fetch controls
   #
   fetch:

     #
     # Don't allow fetching from project defined alias or mirror URIs
     #
     source: user


Attributes
~~~~~~~~~~

* ``source``

  This controls what URIs are allowed to be accessed when fetching sources,
  valid values for this attribute are:

  * ``all``: Fetch from mirrors defined in :ref:`user configuration <config_mirrors>` and
    :ref:`project configuration <project_essentials_mirrors>`, and also project defined
    :ref:`default alias URIs <project_source_aliases>`.
  * ``aliases``: Only allow fetching from project defined :ref:`default alias URIs <project_source_aliases>`.
  * ``mirrors``: Only allow fetching from mirrors defined in :ref:`user configuration <config_mirrors>` and
    :ref:`project configuration <project_essentials_mirrors>`
  * ``user``: Only allow fetching from mirrors defined in :ref:`user configuration <config_mirrors>`


Track controls
--------------
Some aspects about how sources get tracked can be controlled by attributes of the ``track``
dictionary at the toplevel, like so:

.. code:: yaml

   #
   # Track controls
   #
   track:

     #
     # Only track sources for new refs from project defined default alias URIs
     #
     source: aliases


Attributes
~~~~~~~~~~

* ``source``

  This controls what URIs are allowed to be accessed when tracking sources
  for new refs, valid values for this attribute are:

  * ``all``: Track from mirrors defined in :ref:`user configuration <config_mirrors>` and
    :ref:`project configuration <project_essentials_mirrors>`, and also project defined
    :ref:`default alias URIs <project_source_aliases>`.
  * ``aliases``: Only allow tracking from project defined :ref:`default alias URIs <project_source_aliases>`.
  * ``mirrors``: Only allow tracking from mirrors defined in :ref:`user configuration <config_mirrors>` and
    :ref:`project configuration <project_essentials_mirrors>`
  * ``user``: Only allow tracking from mirrors defined in :ref:`user configuration <config_mirrors>`


Logging controls
----------------
Various aspects of how BuildStream presents output and UI can be controlled with
attributes of the toplevel ``logging`` dictionary, like so:

.. code:: yaml

   #
   # Control logging output
   #
   logging:

     #
     # Whether to be verbose
     #
     verbose: True


Attributes
~~~~~~~~~~

* ``verbose``

  Whether to use verbose logging.

* ``debug``

  Whether to print messages related to debugging BuildStream itself.

* ``key-length``

  When displaying abbreviated cache keys, this controls the number of characters
  of the cache key which should be printed.

* ``throttle-ui-updates``

  Whether the throttle updates to the status bar in interactive mode. If set to ``True``,
  then the status bar will be updated once per second.

* ``error-lines``

  The maximum number of lines to print in the main logging output related to an
  error processing an element, these will be the last lines found in the relevant
  element's stdout and stderr.

* ``message-lines``

  The maximum number of lines to print in a detailed message sent to the main logging output.

* ``element-format``

  The default format to use when printing out elements in :ref:`bst show <invoking_show>`
  output, and when printing the pipeline summary at the beginning of sessions.

  The format is specified as a string containing variables which will be expanded
  in the resulting string, variables must be specified using a leading percent sign
  and enclosed in curly braces, a colon can be specified in the variable to perform
  python style string alignments, e.g.:

  .. code:: yaml

     logging:

       #
       # Set the element format
       #
       element-format: |

         %{state: >12} %{full-key} %{name} %{workspace-dirs}

  Variable names which can be used in the element format consist of:

  * ``name``

    The :ref:`element path <format_element_names>`, which is the name of the element including
    any leading junctions.

  * ``key``

    The abbreviated cache key, the length of which is controlled by the ``key-length`` logging configuration.

  * ``full-key``

    The full cache key.

  * ``state``

    The element state, this will be formatted as one of the following:

    * ``no reference``: If the element still needs to be :ref:`tracked <invoking_source_track>`.
    * ``junction``: If the element is a junction and as such does not have any relevant state.
    * ``failed``: If the element has been built and the build has failed.
    * ``cached``: If the element has been successfully built and is present in the local cache.
    * ``fetch needed``: If the element cannot be built yet because the sources need to be :ref:`fetched <invoking_source_fetch>`.
    * ``buildable``: If the element has all of its sources and build dependency artifacts cached locally.
    * ``waiting``: If the element has all of its sources cached but its build dependencies are not yet locally cached.

  * ``config``

    The :ref:`element configuration <format_config>`, formatted in YAML.

  * ``vars``

    The resolved :ref:`element variables <format_variables>`, formatted as a simple YAML dictionary.

  * ``env``

    The resolved :ref:`environment variables <format_environment>`, formatted as a simple YAML dictionary.

  * ``public``

    The resolved :ref:`public data <format_public>`, formatted in YAML.

  * ``workspaced``

    If the element has an open workspace, this will expand to the string *"(workspaced)"*, otherwise
    it will expand to an empty string.

  * ``workspace-dirs``

    If the element has an open workspace, this will expand to the workspace directory, prefixed with
    the text *"Workspace: "*, otherwise it will expand to an empty string.

  * ``deps``

    A list of the :ref:`element paths <format_element_names>` of all dependency elements.

  * ``build-deps``

    A list of the :ref:`element paths <format_element_names>` of all build dependency elements.

  * ``runtime-deps``

    A list of the :ref:`element paths <format_element_names>` of all runtime dependency elements.

* ``message-format``

  The format to use for messages being logged in the aggregated main logging output.

  Similarly to the ``element-format``, The format is specified as a string containing variables which
  will be expanded in the resulting string, and variables must be specified using a leading percent sign
  and enclosed in curly braces, e.g.:

  .. code:: yaml

     logging:

       #
       # Set the message format
       #
       message-format: |

         [%{elapsed}][%{key}][%{element}] %{action} %{message}

  Variable names which can be used in the element format consist of:

  * ``elapsed``

    If this message announces the completion of (successful or otherwise) of an activity, then
    this will expand to a time code showing how much time elapsed for the given activity, in
    the format: ``HH:MM:SS``, otherwise an empty time code will be displayed in the format:
    ``--:--:--``.

  * ``elapsed-us``

    Similar to the ``elapsed`` variable, however the timecode will include microsecond precision.

  * ``wallclock``

    This will display a timecode for each message displaying the local wallclock time, in the
    format ``HH:MM:SS``.

  * ``wallclock-us``

    Similar to the ``wallclock`` variable, however the timecode will include microsecond precision.

  * ``key``

    The abbreviated cache key of the element the message is related to, the length of which is controlled
    by the ``key-length`` logging configuration.

    If the message in question is not related to any element, then this will expand to whitespace
    of equal length.

  * ``element``

    This will be formatted to an indicator consisting of the type of activity which is being
    performed on the element (e.g. *"build"* or *"fetch"* etc), and the :ref:`element path <format_element_names>`
    of the element this message is related to.

    If the message in question is not related to any element, then a string will be formatted
    to indicate that this message is related to a core activity instead.

  * ``action``

    A classifier of the type of message this is, the possible values this will expand to are:

    * ``DEBUG``

      This is a message related to debugging BuildStream itself

    * ``STATUS``

      A message showing some detail of what is currently happening, this message will not
      be displayed unless verbose output is enabled.

    * ``INFO``

      An informative message, this may be printed for instance when discovering a new
      ref for source code when running :ref:`bst source track <invoking_source_track>`.

    * ``WARN``

      A warning message.

    * ``ERROR``

      An error message.

    * ``BUG``

      A bug happened in BuildStream, this will usually be accompanied by a python stack trace.

    * ``START``

      An activity related to an element started.

      Any ``START`` message will always be accompanied by a later ``SUCCESS``, ``FAILURE``
      or ``SKIPPED`` message.

    * ``SUCCESS``

      An activity related to an element completed successfully.

    * ``FAILURE``

      An activity related to an element failed.

    * ``SKIPPED``

      After strating this activity, it was discovered that no work was needed and
      the activity was skipped.

  * ``message``

    The brief message, or the path to the corresponding log file, will be printed here.

    When this is a scheduler related message about the commencement or completion of
    an element related activity, then the path to the corresponding log for that activity
    will be printed here.

    If it is a message issued for any other reason, then the message text will be formatted here.

  .. note::

     Messages issued by the core or by plugins are allowed to provide detailed accounts, these
     are the indented multiline messages which sometimes get displayed in the main aggregated
     logging output, and will be printed regardless of the logging ``message-format`` value.


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

The ``auth`` configuration block looks like this:

.. code:: yaml

   auth:
     server-cert: server.crt
     client-cert: client.crt
     client-key: client.key


Attributes
''''''''''

* ``server-cert``

  The server certificate is used to decrypt traffic coming from the
  server.

* ``client-cert``

  The client certificate is used by the remote server to decrypt
  traffic being uploaded to the server.

  The remote server will have its own copy of this certificate, but the
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


Attributes
''''''''''

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

Attributes
''''''''''

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

  This is optional if a ``storage-service`` is configured in the
  :ref:`cache configuration <config_local_cache>`, in which case actual file
  contents of build outputs will only be downloaded as needed, e.g. on
  ``bst artifact checkout``.

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

Project specific values
-----------------------
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


.. _config_mirrors:

Mirrors
~~~~~~~
Project defined :ref:`mirrors <project_essentials_mirrors>`, can be overridden
with user configuration. This is helpful when you need to mirror all of the source
code used by subprojects and ensure that your project can be built in perpetuity.

**Example**

.. code:: yaml

   projects:
     project-name:
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


.. _config_default_mirror:

Default mirror
~~~~~~~~~~~~~~
When using :ref:`mirrors <project_essentials_mirrors>`, one can specify which
mirror should be used first.

**Example**

.. code:: yaml

   projects:
     project-name:
       default-mirror: oz


.. note::

   It is possible to override this at invocation time using the
   ``--default-mirror`` command-line option.


Project options
~~~~~~~~~~~~~~~
One can specify values to use for :ref:`project options <project_options>` for the projects
you use here, this avoids needing to specify the options on the command line every time.

**Example**

.. code:: yaml

   projects:

     #
     # Configure the debug flag offered by `project-name`
     #
     project-name:
       options:
         debug-build: True


Source cache servers
~~~~~~~~~~~~~~~~~~~~
As already described in the section concerning configuration of
:ref:`source cache servers <config_source_caches>`, these can be specified on a per project basis.


Artifact cache servers
~~~~~~~~~~~~~~~~~~~~~~
As already described in the section concerning configuration of
:ref:`artifact cache servers <config_artifact_caches>`, these can be specified on a per project basis.


Remote execution configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Following the same format as the toplevel :ref:`remote execution configuration <user_config_remote_execution_service>`,
the global configuration can be overridden on a per project basis in this project override section.

**Example**

.. code:: yaml

   projects:

     project-name:

       #
       # If `project-name` is built as the toplevel project in this BuildStream session,
       # then use this remote execution configuration instead of any globally defined
       # remote execution configuration.
       #
       remote-execution:
         execution-service:
           url: http://execution.example.com:50051
           instance-name: main

.. note::

   Only one remote execution service will be considered for any invocation of BuildStream.

   If you are building a project which has a junction into another subproject for which you have
   specified a project specific remote execution service for in your user configuration, then
   it will be ignored in the context of building that toplevel project.


.. _config_defaults:

Default configuration
---------------------
The default BuildStream configuration is specified here for reference:

  .. literalinclude:: ../../src/buildstream/data/userconfig.yaml
     :language: yaml
