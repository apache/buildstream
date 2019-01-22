

.. _artifacts:

Configuring Artifact Server
===========================
BuildStream caches the results of builds in a local artifact cache, and will
avoid building an element if there is a suitable build already present in the
local artifact cache.

In addition to the local artifact cache, you can configure one or more remote
artifact caches and BuildStream will then try to pull a suitable build from one
of the remotes, falling back to a local build if needed.

Configuring BuildStream to use remote caches
--------------------------------------------
A project will often set up continuous build infrastructure that pushes
built artifacts to a shared cache, so developers working on the project can
make use of these pre-built artifacts instead of having to each build the whole
project locally. The project can declare this cache in its
:ref:`project configuration file <project_essentials_artifacts>`.

Users can declare additional remote caches in the :ref:`user configuration
<config_artifacts>`. There are several use cases for this: your project may not
define its own cache, it may be useful to have a local mirror of its cache, or
you may have a reason to share artifacts privately.

Remote artifact caches are identified by their URL. There are currently two
supported protocols:

* ``http``: Pull and push access, without transport-layer security
* ``https``: Pull and push access, with transport-layer security

BuildStream allows you to configure as many caches as you like, and will query
them in a specific order:

1. Project-specific overrides in the user config
2. Project configuration
3. User configuration

When an artifact is built locally, BuildStream will try to push it to all the
caches which have the ``push: true`` flag set. You can also manually push
artifacts to a specific cache using the :ref:`bst artifact push command <invoking_artifact_push>`.

Artifacts are identified using the element's :ref:`cache key <cachekeys>` so
the builds provided by a cache should be interchangable with those provided
by any other cache.


Setting up a remote artifact cache
----------------------------------
The rest of this page outlines how to set up a shared artifact cache.

Setting up the user
~~~~~~~~~~~~~~~~~~~
A specific user is not needed, however, a dedicated user to own the
artifact cache is recommended.

.. code:: bash

   useradd artifacts

The recommended approach is to run two instances on different ports.
One instance has push disabled and doesn't require client authentication.
The other instance has push enabled and requires client authentication.

Alternatively, you can set up a reverse proxy and handle authentication
and authorization there.


Installing the server
~~~~~~~~~~~~~~~~~~~~~
You will also need to install BuildStream on the artifact server in order
to receive uploaded artifacts over ssh. Follow the instructions for installing
BuildStream `here <https://buildstream.build/install.html>`_.

When installing BuildStream on the artifact server, it must be installed
in a system wide location, with ``pip3 install .`` in the BuildStream
checkout directory.

Otherwise, some tinkering is required to ensure BuildStream is available
in ``PATH`` when its companion ``bst-artifact-server`` program is run
remotely.

You can install only the artifact server companion program without
requiring BuildStream's more exigent dependencies by setting the
``BST_ARTIFACTS_ONLY`` environment variable at install time, like so:

.. code::

    BST_ARTIFACTS_ONLY=1 pip3 install .


Command reference
~~~~~~~~~~~~~~~~~

.. click:: buildstream._cas.casserver:server_main
   :prog: bst-artifact-server


.. _server_authentication:

Key pair for the server
~~~~~~~~~~~~~~~~~~~~~~~

For TLS you need a key pair for the server. The following example creates
a self-signed key, which requires clients to have a copy of the server certificate
(e.g., in the project directory).
You can also use a key pair obtained from a trusted certificate authority instead.

.. code:: bash

    openssl req -new -newkey rsa:4096 -x509 -sha256 -days 3650 -nodes -batch -subj "/CN=artifacts.com" -out server.crt -keyout server.key

.. note::

    Note that in the ``-subj "/CN=<foo>"`` argument, ``/CN`` is the *certificate common name*,
    and as such ``<foo>`` should be the public hostname of the server. IP addresses will
    **not** provide you with working authentication.

    In addition to this, ensure that the host server is recognised by the client.
    You may need to add the line: ``<ip address>`` ``<hostname>`` to
    your ``/etc/hosts`` file.

Authenticating users
~~~~~~~~~~~~~~~~~~~~
In order to give permission to a given user to upload
artifacts, create a TLS key pair on the client.

.. code:: bash

    openssl req -new -newkey rsa:4096 -x509 -sha256 -days 3650 -nodes -batch -subj "/CN=client" -out client.crt -keyout client.key

Copy the public client certificate ``client.crt`` to the server and then add it
to the authorized keys, like so:

.. code:: bash

   cat client.crt >> /home/artifacts/authorized.crt


Serve the cache over https
~~~~~~~~~~~~~~~~~~~~~~~~~~

Public instance without push:

.. code:: bash

    bst-artifact-server --port 11001 --server-key server.key --server-cert server.crt /home/artifacts/artifacts

Instance with push and requiring client authentication:

.. code:: bash

    bst-artifact-server --port 11002 --server-key server.key --server-cert server.crt --client-certs authorized.crt --enable-push /home/artifacts/artifacts

Managing the cache with systemd
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We recommend running the cache as a systemd service, especially if it is running
on a dedicated server, as this will allow systemd to manage the cache, in case
the server encounters any issues.

Below are two examples of how to run the cache server as a systemd service. The
first, is for pull only and the other is configured for push & pull. Notice that
the two configurations use different ports.

``bst-artifact-serve.service``:

.. code:: ini

   #
   # Pull
   #
   [Unit]
   Description=Buildstream Artifact pull server
   After=remote-fs.target network-online.target

   [Service]
   Environment="LC_ALL=C.UTF-8"
   ExecStart=/usr/local/bin/bst-artifact-server --port 11001 --server-key {{certs_path}}/server.key --server-cert {{certs_path}}/server.crt {{artifacts_path}}
   User=artifacts

   [Install]
   WantedBy=multi-user.target


``bst-artifact-serve-receive.service``:

.. code:: ini

   #
   # Pull/Push
   #
   [Unit]
   Description=Buildstream Artifact pull/push server
   After=remote-fs.target network-online.target

   [Service]
   Environment="LC_ALL=C.UTF-8"
   ExecStart=/usr/local/bin/bst-artifact-server --port 11002 --server-key {{certs_path}}/server.key --server-cert {{certs_path}}/server.crt --client-certs {{certs_path}}/authorized.crt --enable-push {{artifacts_path}}
   User=artifacts

   [Install]
   WantedBy=multi-user.target


Here we define when systemd should start the service, which is after the networking
stack has been started, we then define how to run the cache with the desired
configuration, under the artifacts user. The {{ }} are there to denote where you
should change these files to point to your desired locations.

.. note::

    You may need to run some of the following commands as the superuser.

These files should be copied to ``/etc/systemd/system/``. We can then start these services
with:

.. code:: bash

    systemctl enable bst-artifact-serve.service
    systemctl enable bst-artifact-serve-receive.service

Then, to start these services:

.. code:: bash

    systemctl start bst-artifact-serve.service
    systemctl start bst-artifact-serve-receive.service

We can then check if the services are successfully running with:

.. code:: bash

    journalctl -u bst-artifact-serve.service
    journalctl -u bst-artifact-serve-receive.service

For more information on systemd services see: 
`Creating Systemd Service Files <https://www.devdungeon.com/content/creating-systemd-service-files>`_.

Declaring remote artifact caches
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Remote artifact caches can be declared within either:

1. The :ref:`project configuration <project_essentials_artifacts>`, or
2. The :ref:`user configuration <config_artifacts>`.

Please follow the above links to see examples showing how we declare remote
caches in both the project configuration and the user configuration, respectively.
