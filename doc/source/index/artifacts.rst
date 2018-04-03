
.. _artifacts:


Artifact Caches
===============
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

Remote artifact caches are identified by their URL. There are currently three
supported protocols:

* ``http``: Pull-only access, without transport-layer security
* ``https``: Pull-only access, with transport-layer security
* ``ssh``: Push access, authenticated via SSH

BuildStream allows you to configure as many caches as you like, and will query
them in a specific order:

1. Project-specific overrides in the user config
2. Project configuration
3. User configuration

When an artifact is built locally, BuildStream will try to push it to all the
caches which have the ``push: true`` flag set. You can also manually push
artifacts to a specific cache using the :ref:`bst pull command <invoking>`.

Artifacts are identified using the element's :ref:`cache key <cachekeys>` so
the builds provided by a cache should be interchangable with those provided
by any other cache.


Setting up a remote artifact cache
----------------------------------
The rest of this page outlines how to set up a shared artifact cache.

Setting up the user
~~~~~~~~~~~~~~~~~~~
A specific user is not needed for downloading artifacts, but since we
are going to use ssh to upload the artifacts, you will want a dedicated
user to own the artifact cache.

.. code:: bash

   useradd artifacts


Installing the receiver
~~~~~~~~~~~~~~~~~~~~~~~
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
~~~~~~~~~~~~~~~~~~~~~~
Now that you have a dedicated user to own the artifact cache, change
to that user, and create the artifact cache ostree repository directly
in it's home directory as such:

.. code:: bash

   ostree init --mode archive-z2 --repo artifacts

This should result in an artifact cache residing at the path ``/home/artifacts/artifacts``


Serve the cache over https
~~~~~~~~~~~~~~~~~~~~~~~~~~
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
~~~~~~~~~~~~~~~~~~~~~~
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
	# The exact pull URL must also be specified.
        ForceCommand bst-artifact-receive --pull-url https://example.com/artifacts --verbose artifacts


Summary file updates
~~~~~~~~~~~~~~~~~~~~
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
~~~~~~~~~~~~~~~~~~
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

     url: https://artifacts.com/artifacts

     # Alternative form if you have push access to the cache
     #url: ssh://artifacts@artifacts.com:22200/artifacts
     #push: true


Authenticating Users
~~~~~~~~~~~~~~~~~~~~
In order to give permission to a given user to upload
artifacts, simply use the regular ``ssh`` method.

First obtain the user's public ssh key, and add it
to the authorized keys, like so:

.. code:: bash

   cat user_id_rsa.pub >> /home/artifacts/.ssh/authorized_keys

