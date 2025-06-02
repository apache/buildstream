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



.. _protocol_buffers:

Generating protocol buffers
---------------------------
BuildStream uses protobuf and gRPC for serialization and communication with
artifact cache servers.  This requires ``.proto`` files and Python code
generated from the ``.proto`` files using protoc.  All these files live in the
``src/buildstream/_protos`` directory.  The generated files are included in the
git repository to avoid depending on grpcio-tools for user installations.


Regenerating code
~~~~~~~~~~~~~~~~~
When ``.proto`` files are modified, the corresponding Python code needs to
be regenerated.  As a prerequisite for code generation you need to install
``grpcio-tools`` using pip or some other mechanism::

  pip3 install --user grpcio-tools

To actually regenerate the code::

  ./setup.py build_grpc

The ``requirements/requirements.in`` file needs to be updated to match the
protobuf version requirements of the ``grpcio-tools`` version used to
generate the code.
