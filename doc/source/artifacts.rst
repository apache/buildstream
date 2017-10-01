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


Installing the receiver
-----------------------
You will also need to install BuildStream on the artifact server in order
to receive uploaded artifacts over ssh. Follow the instructions for installing
BuildStream :ref:`here <installing>`

When installing BuildStream on the artifact server, it must be installed
in a system wide location, with ``pip3 install .`` in the BuildStream
checkout directory.

Otherwise, some tinkering is required to ensure BuildStream is available
in ``PATH`` when it's companion ``bst-artifact-receive`` program is run
remotely.

You can install only the artifact receiver companion program without
requiring BuildStream's more exigent dependencies by setting the
``BST_ARTIFACTS_ONLY`` environment variable at install time, like so:

.. code::

    BST_ARTIFACTS_ONLY=1 pip3 install .


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

   # Some specifics for the artifacts user
   Match user artifacts

        # Dont allow password authentication for artifacts user
	#
        PasswordAuthentication no

        # Also lets dedicate this login for only running the
	# bst-artifact-receive program, note that the full
	# command must be specified here; 'artifacts' is
	# the HOME relative path to the artifact cache.
	#
        ForceCommand bst-artifact-receive --verbose artifacts


Summary file updates
--------------------
BuildStream uses the OSTree summary file to determine what artifacts are
available in the remote artifact cache. ``ostree summary -u`` updates
the summary file. This command cannot be run concurrently and thus it
cannot be executed by ``bst-artifact-receive``, it has to be triggered
externally.

A simple way to configure this is to set up a cron job that triggers the
summary file update every 5 minutes.
E.g., create ``/etc/cron.d/artifacts`` with the following content:

.. code::

   */5 * * * * artifacts ostree --repo=/home/artifacts/artifacts summary -u


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

     # If the artifact server uses a custom port for sshd
     # then you can specify it here
     push-port: 666


Authenticating Users
--------------------
In order to give permission to a given user to upload
artifacts, simply use the regular ``ssh`` method.

First obtain the user's public ssh key, and add it
to the authorized keys, like so:

.. code:: bash

   cat user_id_rsa.pub >> /home/artifacts/.ssh/authorized_keys

