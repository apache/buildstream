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



.. _porting_command_line:

Porting command line usage
==========================
This document outlines breaking changes made to the :ref:`command line interface <commands>`
in BuildStream 2.


:ref:`bst init <invoking_init>`
-------------------------------

* The global ``--directory`` option is no longer observed by ``bst init``, instead
  the command accepts an optional target directory argument.

* The ``--format-version`` option has been removed in favor of the new ``--min-version`` option.


:ref:`bst build <invoking_build>`
---------------------------------

* Tracking is no longer supported at build time and must be performed separately, this
  removes the ``--track``, ``--track-all``, ``--track-except``, ``--track-cross-junctions``
  and ``--track-save`` options from the command.

  To track your elements in BuildStream 2, use the :ref:`bst source track <invoking_source_track>`
  command instead.

* The ``--all`` option which was used to indicate that all dependencies should be built
  regardless of whether they are needed for producing the target elements has been removed
  in favor of adding the ``--deps`` option.

  To acheive the same functionality, use ``bst build --deps all ...``.


:ref:`bst show <invoking_show>`
-------------------------------

* The ``plan`` value is no longer supported as a value for the ``--deps`` option.

* Values for the ``%{state}`` format have changed

  * :mod:`junction <elements.junction>` elements will display ``junction``, as these cannot be built
  * In the case a cached failed build artifact is found, then ``failed`` will be displayed
  * Due to changes in the scheduler, we may observe changes as to when ``waiting``, ``buildable``, ``fetch needed``
    are displayed for a given element.


:ref:`bst fetch <invoking_source_fetch>`
----------------------------------------

* This command has been removed as a top-level command and now exists as :ref:`bst source fetch <invoking_source_fetch>`

* Tracking is no longer supported at fetch time and must be performed separately, this
  removes the ``--track`` and ``--track-cross-junctions`` options from the command.

  To track your elements in BuildStream 2, use the :ref:`bst source track <invoking_source_track>`
  command instead.

* The ``plan`` value is no longer supported as a value for the ``--deps`` option. The default
  value for the ``--deps`` option is now ``none``.


:ref:`bst track <invoking_source_track>`
----------------------------------------

* This command has been removed as a top-level command and now exists as :ref:`bst source track <invoking_source_track>`


:ref:`bst pull <invoking_artifact_pull>`
----------------------------------------

* This command has been removed as a top-level command and now exists as :ref:`bst artifact pull <invoking_artifact_pull>`

* The ``--remote`` option has been removed in favor the ``--artifact-remote`` option, which can be
  specified multiple times.

* The values which can be specified by ``--artifact-remote`` options have a new format which
  is :ref:`documented here <invoking_specify_remotes>`.


:ref:`bst push <invoking_artifact_push>`
----------------------------------------

* This command has been removed as a top-level command and now exists as :ref:`bst artifact push <invoking_artifact_push>`

* The ``--remote`` option has been removed in favor the ``--artifact-remote`` option, which can be
  specified multiple times.

* The values which can be specified by ``--artifact-remote`` options have a new format which
  is :ref:`documented here <invoking_specify_remotes>`.



:ref:`bst checkout <invoking_artifact_checkout>`
------------------------------------------------

* This command has been removed as a top-level command and now exists as :ref:`bst artifact checkout <invoking_artifact_checkout>`

* The trailing ``LOCATION`` argument has been removed in favor of a ``--directory`` option.

  **BuildStream 1:**

  .. code:: shell

     bst checkout element.bst ~/checkout

  **BuildStream 2:**

  .. code:: shell

     bst artifact checkout --directory ~/checkout element.bst


:ref:`bst shell <invoking_shell>`
---------------------------------

* The ``--sysroot`` option has been completely removed.

  This is no longer needed for failed builds as the build tree will be cached in a failed build artifact.

* Sources and artifacts required to produce the shell environment will now be downloaded
  automatically by default.


:ref:`bst workspace open <invoking_workspace_open>`
---------------------------------------------------

* The ``--track`` option is now removed.

* The trailing ``LOCATION`` argument has been removed in favor of a ``--directory`` option.

  **BuildStream 1:**

  .. code:: shell

     bst workspace open element.bst ~/workspace

  **BuildStream 2:**

  .. code:: shell

     bst workspace open --directory ~/workspace element.bst


:ref:`bst workspace reset <invoking_workspace_reset>`
-----------------------------------------------------

* The ``--track`` option is now removed.


:ref:`bst source-bundle <invoking_source_checkout>`
---------------------------------------------------
This command has been completely removed, but similar behavior can be achieved
using the :ref:`bst source checkout <invoking_source_checkout>` command.


**BuildStream 1:**

.. code:: shell

   bst source-bundle --directory ~/bundle element.bst

**BuildStream 2:**

.. code:: shell

   bst source checkout \
       --tar ~/sources.tgz \
       --compression gz \
       --include-build-scripts \
       element.bst
