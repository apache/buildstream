
.. _commands:

Commands
========
This page contains documentation for each BuildStream command,
along with their possible options and arguments. Each command can be
invoked on the command line, where, in most cases, this will be from the
project's main directory.


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
