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


.. _commands:

Commands
========
This page contains documentation for each BuildStream command,
along with their possible options and arguments. Each command can be
invoked on the command line, where, in most cases, this will be from the
project's main directory.


Commonly used parameters
------------------------


.. _invoking_specify_remotes:

Remotes
~~~~~~~
Remote :ref:`cache servers <config_cache_servers>` can be specified on the
command line for commands which may result in communicating with such servers.

Any command which has arguments to specify a ``REMOTE``, such as ``--artifact-remote``
or ``--source-remote``, will override whatever was set in the user configuration,
and will have an accompanying switch which allows the command to decide whether
to ignore any remote :ref:`artifact <project_artifact_cache>` or :ref:`source <project_source_cache>`
caches suggested by project configuration.

Remotes can be specified on the command line either as a simple URI, or as
a comma separated list of key value pairs.

**Specifying a remote using a URI**

.. code:: shell

   bst artifact push --remote https://artifacts.com/artifacts:8088 element.bst

**Specifying a remote using key value pairs**

.. code:: shell

   bst build --artifact-remote \
       url=https://artifacts.com/artifacts:8088,type=index,server-cert=~/artifacts.cert \
       element.bst


Attributes
''''''''''
Here is the list attributes which can be spefied when providing a ``REMOTE`` on the command line:

* ``url``

  The URL of the remote, possibly including a port number.

* ``instance-name``

  The instance name of this remote, used for sharding by some implementations.

* ``type``

  Whether this remote is to be used for indexing, storage or both, as explained
  in the corresponding :ref:`user configuration documentation <config_cache_servers>`

* ``push``

  Normally one need not specify this, as it is often inferred by the command
  being used. In some cases, like :ref:`bst build <invoking_build>`, it can
  be useful to specify multiple remotes, and only allow pushing to some of
  the remotes.

  If unspecified, this is assumed to be ``True`` and BuildStream will attempt
  to push to the remote, but fallback to only pulling if insufficient credentials
  were provided.

* ``server-cert``, ``client-cert``, ``client-key``:

  These keys specify the attributes of the :ref:`authentication configuration <config_remote_auth>`.

  When specifying these on the command line, they are interpreted as paths relative
  to the current working directory.


Top-level commands
------------------

.. The bst options e.g. bst --version, or bst --verbose etc.
.. _invoking_bst:

.. click:: buildstream._frontend:cli
   :prog: bst

.. Further description of the command goes here

----

.. _invoking_artifact:

.. click:: buildstream._frontend.cli:artifact
   :prog: bst artifact

----

.. the `bst init` command
.. _invoking_init:

.. click:: buildstream._frontend.cli:init
   :prog: bst init

----

.. the `bst build` command
.. _invoking_build:

.. click:: buildstream._frontend.cli:build
   :prog: bst build

----

.. _invoking_show:

.. click:: buildstream._frontend.cli:show
   :prog: bst show

----

.. _invoking_shell:

.. click:: buildstream._frontend.cli:shell
   :prog: bst shell

----

.. _invoking_source:

.. click:: buildstream._frontend.cli:source
   :prog: bst source

----

.. _invoking_workspace:

.. click:: buildstream._frontend.cli:workspace
   :prog: bst workspace


.. _artifact_subcommands:

Artifact subcommands
--------------------


.. _artifact_names:

Artifact names
~~~~~~~~~~~~~~
Various artifact subcommands accept either :ref:`element names <format_element_names>`,
which will operate on artifacts by deriving the artifact from local project state,
or :term:`artifact names <Artifact name>` interchangeably as targets. Artifact names allow
the user to operate directly on cached artifacts, without requiring local project data.

An artifact name is composed of the following identifiers:

* The :ref:`project name <project_format_name>`

* The :ref:`element name <format_element_names>`, without any trailing ``.bst`` extension

* The cache key of the element at the time it was built.

To compose an artifact name, simply join these using a forward slash (``/``) character, like so: ``<project-name>/<element-name>/<cache-key>``.

An artifact name might look like: ``project/target/788da21e7c1b5818b7e7b60f7eb75841057ff7e45d362cc223336c606fe47f27``


.. _invoking_artifact_checkout:

.. click:: buildstream._frontend.cli:artifact_checkout
   :prog: bst artifact checkout

----

.. _invoking_artifact_log:

.. click:: buildstream._frontend.cli:artifact_log
   :prog: bst artifact log

----

.. _invoking_artifact_pull:

.. click:: buildstream._frontend.cli:artifact_pull
   :prog: bst artifact pull

----

.. _invoking_artifact_push:

.. click:: buildstream._frontend.cli:artifact_push
   :prog: bst artifact push

----

.. _invoking_artifact_delete:

.. click:: buildstream._frontend.cli:artifact_delete
   :prog: bst artifact delete

----

.. _invoking_artifact_show:

.. click:: buildstream._frontend.cli:artifact_show
   :prog: bst artifact show

----

.. _invoking_artifact_list_contents:

.. click:: buildstream._frontend.cli:artifact_list_contents
   :prog: bst artifact list-contents


.. _source_subcommands:

Source subcommands
------------------

.. _invoking_source_fetch:

.. click:: buildstream._frontend.cli:source_fetch
   :prog: bst source fetch

----

.. _invoking_source_track:

.. click:: buildstream._frontend.cli:source_track
   :prog: bst source track

----

.. _invoking_source_push:

.. click:: buildstream._frontend.cli:source_push
   :prog: bst source push

----

.. _invoking_source_checkout:

.. click:: buildstream._frontend.cli:source_checkout
   :prog: bst source checkout


.. _workspace_subcommands:

Workspace subcommands
---------------------

.. _invoking_workspace_open:

.. click:: buildstream._frontend.cli:workspace_open
   :prog: bst workspace open

----

.. _invoking_workspace_close:

.. click:: buildstream._frontend.cli:workspace_close
   :prog: bst workspace close

----

.. _invoking_workspace_reset:

.. click:: buildstream._frontend.cli:workspace_reset
   :prog: bst workspace reset

----

.. _invoking_workspace_list:

.. click:: buildstream._frontend.cli:workspace_list
   :prog: bst workspace list
