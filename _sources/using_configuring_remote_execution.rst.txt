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



.. _remote_execution_servers:

Remote Execution Servers
========================
BuildStream supports building remotely using the
`Google Remote Execution API (REAPI). <https://github.com/bazelbuild/remote-apis>`_, which
has various known implementations.

Some of these implementations include:

* `BuildGrid <https://buildgrid.build/>`_
* `BuildBarn <https://github.com/buildbarn>`_
* `Buildfarm <https://github.com/bazelbuild/bazel-buildfarm>`_

These various implementations implement the `Google Remote Execution API (REAPI)
<https://github.com/bazelbuild/remote-apis>`_ to various degrees as these projects
have different priorities.

On the client side, the remote execution service to use can be
specified in the :ref:`user configuration <user_config_remote_execution>`.


BuildStream specific requirements
---------------------------------
In order for BuildStream to work correctly with a remote execution cluster, there
are a couple of requirements that implementation needs to meet.


Implementation of platform properties
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The remote execution service must properly implement `platform properties
<https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/platform.md>`_.

This is crucial because BuildStream needs to be guaranteed the correct operating
system and ISA which it requests from the service.


Staging the input root as the filesystem root
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream requires that the *input root* given to the remote execution service
be treated as the absolute *filesystem root*.

This is because BuildStream provides guarantees that all build dependencies, including
the base runtime and compilers, are defined by elements and run within a sandboxed and
isolated build environment, but the `REAPI <https://github.com/bazelbuild/remote-apis>`_
was originally developped without this determinism and control in mind. Instead, typically
it is up to the user to configure a cluster to use a docker image to build payloads
with, rather than allowing the REAPI client to control the entire sandbox.

Unfortunately the ability to dictate that the *input root* be treated as the *filesystem root*
in a container on remote workers in the cluster is not yet standardized in the REAPI protocol.

.. note::

   The *input root* is referred to as the ``input_root_digest`` member of the ``Action`` message
   as defined in the `protocol <https://github.com/bazelbuild/remote-apis/blob/main/build/bazel/remote/execution/v2/remote_execution.proto>`_


Example working configuration
-----------------------------
A simple configuration to spin up the `BuildGrid <https://buildgrid.build/>`_ service using
`docker compose <https://docs.docker.com/compose/>`_ follows:

.. literalinclude:: ../../.github/compose/ci.buildgrid.yml
    :language: yaml
