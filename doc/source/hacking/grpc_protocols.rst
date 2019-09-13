

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

