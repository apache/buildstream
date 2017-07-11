.. _artifacts:


Artifact Caches
===============
BuildStream revisions output of each element under it's specific
cache key in a local artifact cache.

This artifact cache can however be shared with others, or automated
builders can be made to contribute to a shared artifact cache so
that developers dont need to build everything all the time, instead
they can download prebuilt artifacts from a shared cache, if an artifact
is available for the specific cache keys they need.

This page outlines how to setup and use a shared artifact cache.


Setting up the user
-------------------
A specific user is not needed for downloading artifacts, but since we
are going to use ssh to upload the artifacts, you will want a dedicated
user to own the artifact cache.

.. code:: bash

   useradd artifacts

You will also need to install BuildStream on the artifact server in order
to receive uploaded artifacts over ssh. Follow the instructions for installing
BuildStream :ref:`here <installing>`

.. note::

   When installing BuildStream on the artifact server, it must be installed
   in a system wide location, with ``pip3 install .`` in the BuildStream
   checkout directory.

   Otherwise, some tinkering is required to ensure BuildStream is available
   in ``PATH`` when it's companion ``bst-artifact-receive`` program is run
   remotely.


Initializing the cache
----------------------
Now that you have a dedicated user to own the artifact cache, change
to that user, and create the artifact cache ostree repository directly
in it's home directory as such:

.. code:: bash

   ostree init --mode archive-z2 --repo artifacts

This should result in an artifact cache residing at the path ``/home/artifacts/artifacts``


Serve the cache over https
--------------------------
This part should be pretty simple, you can do this with various technologies, all
we really require is that you make the artifacts available over https (you can use
http but until we figure out using gpg signed ostree commits for the artifacts, it's
better to serve over https).

Here is an example, note that you must have a certificate **pem** file to use, as
is the case for hosting anything over https.

.. code:: python

   import http.server, ssl, os

   # Maybe use a custom port, especially if you are serving
   # other web pages on the same computer
   server_address = ('localhost', 443)
   artifact_path = '/home/artifacts'

   # The http server will serve from it's current
   # working directory
   os.chdir(artifact_path)

   # Create Server
   httpd = http.server.HTTPServer(
       server_address,
       http.server.SimpleHTTPRequestHandler)

   # Add ssl
   httpd.socket = ssl.wrap_socket(httpd.socket,
                                  server_side=True,
                                  certfile='localhost.pem',
                                  ssl_version=ssl.PROTOCOL_TLSv1)

   # Run it
   httpd.serve_forever()


Configure and run sshd
----------------------
You will need to run the sshd service to allow uploading artifacts.

For this you will want something like the following in your ``/etc/ssh/sshd_config``

.. code:: bash

   # Allow ssh logins/commands with the artifacts user
   AllowUsers artifacts

   # Dont allow password authentication for artifacts user
   #
   # Also lets restrict these logins to only running
   # the artifact receive process
   Match user artifacts
        ForceCommand bst-artifact-receive
        PasswordAuthentication no


User Configuration
------------------
The user configuration for artifacts is documented with the rest
of the :ref:`user configuration documentation <config>`.

Assuming you have the same setup used in this document, and that your
host is reachable on the internet as ``artifacts.com`` (for example),
then a user can use the following user configuration:

.. code:: yaml

   #
   #    Artifacts
   #
   artifacts:

     # A url from which to download prebuilt artifacts
     pull-url: https://artifacts.com

     # A url to upload built artifacts to
     push-url: artifacts@artifacts.com:artifacts

Also, if you have used a custom port for uploading
artifacts, there is no syntax for specifying that in
the URL.

Instead the user must specify this in their own ssh
configuration in ``~/.ssh/config``

This can be done with the following snippet, assuming
the same ``artifacts.com`` url, and port ``10000``:

.. code:: bash

   Host artifacts.com
        Port 10000


Authenticating Users
--------------------
In order to give permission to a given user to upload
artifacts, simply use the regular ``ssh`` method.

First obtain the user's public ssh key, and add it
to the authorized keys, like so:

.. code:: bash

   cat user_id_rsa.pub >> /home/artifacts/.ssh/authorized_keys

