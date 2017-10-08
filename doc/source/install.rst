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
* ruamel.yaml python library
* PyGObject introspection bindings
* OSTree >= v2017.8 with introspection data

Note that ``ruamel.yaml`` is a pure python library which is normally
obtainable via pip, however there seems to be some problems with installing
this package so we recommend installing it with your package manager first.

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
      bubblewrap ruamel.yaml


Debian Stretch or Sid
~~~~~~~~~~~~~~~~~~~~~
For debian unstable or testing, only the following line should be enough
to get the base system requirements installed::

  sudo apt-get install \
      python3 python3-dev python3-pip git \
      python3-gi gir1.2-ostree-1.0 ostree \
      bubblewrap ruamel.yaml


User installation with pip
--------------------------
Once you have the base system dependencies, you can clone the buildstream
git repository and install it as a regular user::

  git clone https://gitlab.com/BuildStream/buildstream.git
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
  git clone https://gitlab.com/BuildStream/buildstream.git
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

The BuildStream project provides
`Docker images <https://hub.docker.com/r/buildstream/buildstream-fedora/>`_
containing BuildStream and its dependencies.
This gives you an easy way to get started using BuildStream on any Unix-like
platform where Docker is available, including Mac OS X.

To use BuildStream build tool you will need to spawn a container from that image
and mount your workspace directory as a volume. You will want a second volume
to store the cache, which we can create from empty like this:

::

    docker volume create buildstream-cache

You can now run the following command to fetch the latest official Docker image
build, and spawn a container running an interactive shell. This assumes that the
path to all the source code you need is available in ``~/src``.

::

    docker run -it \
          --cap-add SYS_ADMIN \
          --device /dev/fuse \
          --security-opt seccomp=unconfined \
          --volume ~/src:/src \
          --volume buildstream-cache:/root/.cache \
          buildstream/buildstream-fedora:latest /bin/bash
