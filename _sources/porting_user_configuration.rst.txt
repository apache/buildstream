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



.. _porting_user_configuration:

Porting the buildstream.conf
============================
This document outlines breaking changes made to the :ref:`user configuration <user_config>`
in BuildStream 2.


Filename and parallel installation
----------------------------------
The default filename to load user configuration remains unchanged, however,
if you plan to install and use both versions of BuildStream on the same
host, it is recommended to keep your BuildStream 2 configuration in a
file named ``buildstream2.conf``.


Working directories
-------------------
The ``builddir`` and ``artifactdir`` have been removed in favor of the new ``cachedir``.


BuildStream 1:
~~~~~~~~~~~~~~

.. code:: yaml

   builddir: ${XDG_CACHE_HOME}/buildstream/build
   artifactdir: ${XDG_CACHE_HOME}/buildstream/artifacts


BuildStream 2:
~~~~~~~~~~~~~~

.. code:: yaml

   cachedir: ${XDG_CACHE_HOME}/buildstream/cache


Remote cache configuration
--------------------------
The configuration for remote artifact caches has been completely
redesigned, please refer to the :ref:`artifact cache configuration documentation <config_artifact_caches>`
for details on how to configure remotes in BuildStream 2.
