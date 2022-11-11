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



.. _cache_servers:

Configuring Cache Servers
=========================
BuildStream caches the results of builds in a local artifact cache, and will
avoid building an element if there is a suitable build already present in the
local artifact cache. Similarly it will cache sources and avoid pulling them if
present in the local cache. See :ref:`caches <caches>` for more details.

In addition to the local caches, you can configure one or more remote caches and
BuildStream will then try to pull a suitable object from one of the remotes,
falling back to performing a local build or fetching a source if needed.

On the client side, cache servers are declared and configured in
:ref:`user configuration <config_cache_servers>`, and since it is typical
for projects to maintain their own cache servers, it is also possible for
projects to provide recommended :ref:`artifact cache servers <project_artifact_cache>`
and :ref:`source cache servers <project_source_cache>` through project
configuration, so that downstream users can download from services
provided by upstream projects by default.


Setting up a remote cache
-------------------------
BuildStream relies on the `ContentAddressableStorage protocol
<https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/remote_execution.proto>`_
in order to exchange data with remote services, in concert with the `remote asset protocol
<https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/asset/v1/remote_asset.proto>`_
in order to assign symbolic labels (such as :ref:`artifact names <artifact_names>`) to identify
stored content. As such, BuildStream is able to function with any implementations of these
two services.


Known implementations
---------------------
Here are some details about known open source implementations of the required protocols


Buildbarn
~~~~~~~~~
The `Buildbarn <https://github.com/buildbarn>`_ project provides a remote execution
service implementation for use in build tooling such as BuildStream, `Bazel <https://bazel.build/>`_
and `recc <https://gitlab.com/bloomberg/recc>`_, the `bb-storage <https://github.com/buildbarn/bb-storage>`_
and `bb-remote-asset <https://github.com/buildbarn/bb-remote-asset>`_ services are tested
to work as cache service for BuildStream's artifact and source caches.

A simple configuration to spin up the service using `docker compose <https://docs.docker.com/compose/>`_ follows:

.. literalinclude:: ../../.github/compose/ci.buildbarn.yml
    :language: yaml

Visit the `bb-storage <https://github.com/buildbarn/bb-storage>`_ and
`bb-remote-asset <https://github.com/buildbarn/bb-remote-asset>`_ project pages to
find more documentation about setting up services with authentication enabled.
