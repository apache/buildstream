.. _installing:


Installing BuildStream
======================
Until BuildStream is available in your distro, there are a few hoops to jump
through to get started.

If your system cannot provide the base system requirements for BuildStream,
then we have some instructions below which can get you started using BuildStream
within a Docker container.


Installing base system requirements
-----------------------------------
BuildStream requires the following base system requirements:

* python3 >= 3.4
* PyGObject introspection bindings
* OSTree >= v2016.8
* OStree introspection data

For the purpose of installing BuildStream while there are no distro packages,
you will additionally need:

* pip for python3 (only required for setup)
* Python 3 development libraries and headers
* git (to checkout buildstream)


Here are some examples of how to prepare the base requirements on
some distros.


Debian Jessie
~~~~~~~~~~~~~
With jessie, you first need to ensure that you have the backports repository
setup as described `here <https://backports.debian.org/Instructions/>`_

By adding the following line to your sources.list::

  deb http://ftp.debian.org/debian jessie-backports main

And then running::

  sudo apt-get update

At this point you should be able to get the system requirements with::

  sudo apt-get install \
      python3 python3-dev python3-pip git \
      python3-gi gir1.2-ostree-1.0 ostree \
      bubblewrap


Debian Stretch or Sid
~~~~~~~~~~~~~~~~~~~~~
For debian unstable or testing, only the following line should be enough
to get the base system requirements installed::

  sudo apt-get install \
      python3 python3-dev python3-pip git \
      python3-gi gir1.2-ostree-1.0 ostree \
      bubblewrap


User installation with pip
--------------------------
Once you have the base system dependencies, you can clone the buildstream
git repository and install it as a regular user::

  git clone git@gitlab.com:BuildStream/buildstream.git
  cd buildstream
  pip3 install --user .

This will install buildstream and it's pure python dependencies directly into
your user's homedir in ``~/.local``


Adjust PATH
~~~~~~~~~~~
Since BuildStream is now installed under your local user's install directories,
you need to ensure that ``PATH`` is adjusted.

A regular way to do this is to add the following line to the end of your ``~/.bashrc``::

  export PATH=${PATH}:~/.local/bin


Upgrading with pip
~~~~~~~~~~~~~~~~~~
To upgrade a previously install BuildStream, you will need to pull the latest
changes and reinstall as such::

  pip3 uninstall buildstream
  cd buildstream
  git pull --rebase
  pip3 install --user .


Using virtualenv
----------------
If you want to install BuildStream in such a way that ``pip`` does not add
any files to your home directory, you can use virtualenv. This is a bit less
convenient because it requires you enter a special environment every time you
want to use BuildStream.

To use virtualenv, you will first need to install virtualenv with your
package manager, in addition to the base requirements listed above.

E.g. with debian systems::

  sudo apt-get install python3-virtualenv

At this point the following instructions will get you a virtual python
environment that is completely encapsulated and does not interfere with
your system or home directory::

  # Clone the repository
  git clone git@gitlab.com:BuildStream/buildstream.git
  cd buildstream

  # Create a virtualenv sandbox for the installation, you need to
  # enable the system site packages in order to have access to the
  # ostree python bindings which unfortunately cannot be installed
  # with pip into your sandbox
  virtualenv --system-site-packages -p python3 sandbox

  # Install into the virtualenv using pip inside the virtualenv
  ./sandbox/bin/pip3 install .

Once you have done the above, you have a completely disposable
``sandbox`` directory which provides an environment you can enter
at anytime to use BuildStream. BuildStream man pages should also
be available when in the virtualenv environment.

To enter the environment, source it's activation script::

  source sandbox/bin/activate

From here, the ``bst`` command is available, run ``bst --help`` or ``man bst``.

The activation script adds a bash function to your environment which you
can use to exit the sandbox environment, just type ``deactivate`` in the
shell to deactivate the virtualenv sandbox.

To upgrade to a new version of BuildStream when using virtualenv, just
remove the ``sandbox`` directory completely and recreate it with a new
version of BuildStream.


Using BuildStream inside Docker
===============================
Some of the dependencies needed to use BuildStream are still not available in
some Linux distributions.

It is also possible that the users don't want to install these dependencies in
their systems. For these cases, it's possible to use Docker.

Here in this page we are going to explain how to use Docker for developing and
running BuildStream.


Building a Docker container to use BuildStream
----------------------------------------------
To create a Docker image ready to use with BuildStream you need to run the
following command in the top level directory of BuildStream repository.

::

    docker build -t buildstream .

Options explained:

-  ``-t buildstream``: Tag the created container as ``buildstream``

The container created will have BuildStream installed. If you want to run a
different version, you have to switch to the modified source tree and build the
container image running the same command, or with a different tag.


Running BuildStream tests in Docker
-----------------------------------
To run the tests inside a Docker container, we only need to mount the
repository inside the running container and run the tests. To do this run the
following command:

::

    docker run -it -u $UID:$EUID -v `pwd`:/bst-src:rw \
               --privileged -w /bst-src buildstream \
	       python3 setup.py test

Options explained:

-  ``-it``: Interactive shell and TTY support.
-  ``-u $UID:$EUID``: Use $UID as user-id and $EUID as group-id when
   running the container.
-  ``-v $(pwd):/bst-src:rw``: Mount BuildStream source tree in
   ``/bst-src`` with RW permissions.
-  ``--privileged``: To give extra privileges to the container (Needed
   to run some of the sandbox tests).
-  ``-w /bst-src``: Switch to the ``/bst-src`` directory when running the
   container.


Using BuildStream in a Docker container
---------------------------------------
To use BuildStream build tool you will need to mount inside the container your
workspace, and a folder that BuildStream will use for temporary data. This way
we make the temporary data persistent between runs.

Run the following command to run a bash session inside the container:

::

    docker run -it -u $UID:$EUID \
           -v /path/to/buildstream/workspace:/src:rw \
	   -v /path/to/buildstream/tmp:/buildstream:rw \
	   buildstream bash

Options:

-  ``-it``: Interactive shell and TTY support.
-  ``-u $UID:$EUID``: Use $UID as user-id and $EUID as group-id when
   running the container.
-  ``-v /path/to/buildstream/workspace:/src:rw``: Mount your workspace in
   ``/src`` inside the container.
-  ``-v /path/to/buildstream/tmp:/buildstream:rw``: Mount a temporary folder
   where BuildStream stores artifacts, sources, etc.
