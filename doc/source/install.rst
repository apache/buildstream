:orphan:

.. _installing:


Installing BuildStream
======================
Until BuildStream is available in your distro, you will need to install
it yourself from the `git repository <https://gitlab.com/BuildStream/buildstream.git>`_
using python's ``pip`` package manager.

This page has some instructions for installing the dependencies you
will need using your distribution's package manager, this is followed by
instructions for installing BuildStream itself :ref:`using pip <installing_pip>`.
=======
BuildStream on your host
========================

Until BuildStream is available in your distro, there are a few hoops to jump
through to get started.

If your system cannot provide the base system requirements for BuildStream,
then we have some instructions which can help you get started
:ref:`using BuildStream with Docker <docker>`.


System requirements
-------------------

BuildStream requires the following base system requirements:

* python3 >= 3.4
* ruamel.yaml python library
* OSTree >= v2017.8 with introspection data
* bubblewrap
* gobject-introspection
* PyGObject introspection bindings

Note that ``ruamel.yaml`` is a pure python library which is normally
obtainable via pip, however, there seem to be some problems with installing
this package so we recommend installing it with your package manager first.

For the purpose of installing BuildStream while there are no distro packages,
you will additionally need:

* pip for python3 (only required for setup)
* Python 3 development libraries and headers
* git (to checkout or install BuildStream from git)

Here are some examples of how to prepare the base requirements on
some distros.

Arch
~~~~

Install the dependencies with::

  sudo pacman -S fuse2 python python-pip python-gobject git \
                 ostree bubblewrap python-ruamel-yaml

Debian Stretch
~~~~~~~~~~~~~~

With stretch, you first need to ensure that you have the backports repository
setup as described `here <https://backports.debian.org/Instructions/>`_

By adding the following line to your sources.list::

  deb http://ftp.debian.org/debian stretch-backports main

And then running::

  sudo apt-get update

At this point, you should be able to get the system requirements with::

  sudo apt-get install \
      python3-dev python3-pip git python3-gi \
      python3-ruamel.yaml bubblewrap fuse libfuse2
  sudo apt-get install -t stretch-backports \
      gir1.2-ostree-1.0 ostree

Debian Buster or Sid
~~~~~~~~~~~~~~~~~~~~

For Debian unstable or testing, the following line should be enough
to get most of the base system requirements installed::

  sudo apt-get install \
      python3-dev python3-pip git \
      python3-gi gir1.2-ostree-1.0 ostree \
      bubblewrap python3-ruamel.yaml fuse libfuse2


Fedora
~~~~~~

For recent Fedora systems, the following line should get you the system
requirements you need::

  dnf install -y bubblewrap fuse fuse-libs git python3-gobject \
                 python3-psutil ostree python3-ruamel-yaml


.. _installing_pip:

Installing with pip
-------------------

User installation with pip
--------------------------
Once you have the base system dependencies, you can clone the BuildStream
git repository and install it as a regular user::

  git clone https://gitlab.com/BuildStream/buildstream.git

  cd buildstream

  pip3 install --user -e .

This will install buildstream's pure python dependencies into
your user's homedir in ``~/.local`` and will run BuildStream directly
from the git checkout directory.
=======

  pip3 install --user .

This will install BuildStream and its pure python dependencies directly into
your user's home dir in ``~/.local``

Keep following the instructions below to ensure that the ``bst``
command is in your ``PATH`` and to enable bash completions for it.

.. note::

   We recommend the ``-e`` option because you can upgrade your
   installation by simply updating the checked out git repository.

   If you want a full installation that is not linked to your
   git checkout, just omit the ``-e`` option from the above commands.


Adjust PATH
~~~~~~~~~~~

Since BuildStream is now installed under your local user's install directories,
you need to ensure that ``PATH`` is adjusted.

The regular way to do this is to add the following line to the end of your ``~/.bashrc``::

  export PATH=${PATH}:~/.local/bin


Bash Completions
~~~~~~~~~~~~~~~~

Bash completions are supported by sourcing the ``buildstream/data/bst``
script found in the BuildStream repository. On many systems this script
can be installed into a completions directory but when installing BuildStream
without a package manager, this is not an option.

To enable completions for an installation of BuildStream you
installed yourself from git, just append the script verbatim
to your ``~/.bash_completion``:

.. literalinclude:: ../../buildstream/data/bst
  :language: yaml


Upgrading BuildStream with pip
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Assuming you have followed the default instructions above, all
you need to do to upgrade BuildStream is to update your local git
checkout::

  cd /path/to/buildstream
  git pull --rebase

If you did not specify the ``-e`` option at install time, you will
need to cleanly reinstall BuildStream::

  pip3 uninstall buildstream
  cd /path/to/buildstream


Upgrading with pip
~~~~~~~~~~~~~~~~~~

To upgrade a previously installed BuildStream, you will need to pull
the latest changes and reinstall as such::

  pip3 uninstall buildstream

  cd buildstream

  git pull --rebase

  pip3 install --user .
