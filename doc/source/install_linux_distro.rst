
.. _install:

Installing BuildStream on a Linux distro
========================================
BuildStream requires the following base system requirements:

* python3 >= 3.5
* bubblewrap >= 0.1.2
* fuse2

BuildStream also depends on the host tools for the :mod:`Source <buildstream.source>` plugins.
Refer to the respective :ref:`source plugin <plugins_sources>` documentation for host tool
requirements of specific plugins.

The default plugins with extra host dependencies are:

* bzr
* deb
* git
* ostree
* patch
* tar

If you intend to push built artifacts to a remote artifact server,
which requires special permissions, you will also need:

* ssh


Installing from source (recommended)
------------------------------------
Until BuildStream is available in your distro, you will need to install
it yourself from the `git repository <https://gitlab.com/BuildStream/buildstream.git>`_
using python's ``pip`` package manager.

For the purpose of installing BuildStream while there are no distro packages,
you will additionally need:

* pip for python3 (only required for setup)
* Python 3 development libraries and headers
* git (to checkout buildstream)


Installing dependencies
~~~~~~~~~~~~~~~~~~~~~~~


Arch Linux
++++++++++
Install the dependencies with::

  sudo pacman -S \
      python fuse2 bubblewrap \
      python-pip git

For the default plugins::

  sudo pacman -S \
      bzr git lzip ostree patch python-gobject


The package *python-arpy* is required by the deb source plugin. This is not
obtainable via `pacman`, you must get *python-arpy* from AUR:
https://aur.archlinux.org/packages/python-arpy/

To install::

  wget https://aur.archlinux.org/cgit/aur.git/snapshot/python-arpy.tar.gz
  tar -xvf python-arpy.tar.gz
  cd python-arpy
  makepkg -si

Debian
++++++
Install the dependencies with::

  sudo apt-get install \
      python3 fuse bubblewrap \
      python3-pip python3-dev git

For the default plugins:

Stretch
^^^^^^^
With stretch, you first need to ensure that you have the backports repository
setup as described `here <https://backports.debian.org/Instructions/>`_

By adding the following line to your sources.list::

  deb http://deb.debian.org/debian stretch-backports main

And then running::

  sudo apt update

At this point you should be able to get the system requirements for the default plugins with::

  sudo apt install \
      bzr git lzip patch python3-arpy python3-gi
  sudo apt install -t stretch-backports \
      gir1.2-ostree-1.0 ostree

Buster or Sid
^^^^^^^^^^^^^
For debian unstable or testing, only the following line should be enough
to get the system requirements for the default plugins installed::

  sudo apt-get install \
      lzip gir1.2-ostree-1.0 git bzr ostree patch python3-arpy python3-gi


Fedora
++++++
For recent fedora systems, the following line should get you the system
requirements you need::

  dnf install -y \
      python3 fuse bubblewrap \
      python3-pip python3-devel git

For the default plugins::

  dnf install -y \
      bzr git lzip patch ostree python3-gobject
  pip3 install --user arpy


Ubuntu
++++++

Ubuntu 18.04 LTS or later
^^^^^^^^^^^^^^^^^^^^^^^^^
Install the dependencies with::

  sudo apt install \
      python3 fuse bubblewrap \
      python3-pip python3-dev git

For the default plugins::

  sudo apt install \
      bzr gir1.2-ostree-1.0 git lzip ostree patch python3-arpy python3-gi

Ubuntu 16.04 LTS
^^^^^^^^^^^^^^^^
On Ubuntu 16.04, neither `bubblewrap <https://github.com/projectatomic/bubblewrap/>`_
or `ostree <https://github.com/ostreedev/ostree>`_ are available in the official repositories.
You will need to install them in whichever way you see fit. Refer the the upstream documentation
for advice on this.


Installing
~~~~~~~~~~
Once you have the base system dependencies, you can install the BuildStream
python package as a regular user.

Via PyPI (recommended)
++++++++++++++++++++++
::

  pip3 install --user BuildStream

This will install latest stable version of BuildStream and its pure python
dependencies into your user's homedir in ``~/.local``.

Keep following the instructions below to ensure that the ``bst``
command is in your ``PATH`` and to enable bash completions for it.

.. note::

  If you want a specific version of BuildStream, you can install it using
  ``pip install --user BuildStream==<version-number>``

Via Git checkout
++++++++++++++++
::

  git clone https://gitlab.com/BuildStream/buildstream.git
  cd buildstream
  pip3 install --user -e .

This will install buildstream's pure python dependencies into
your user's homedir in ``~/.local`` and will run BuildStream directly
from the git checkout directory.

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

A regular way to do this is to add the following line to the end of your ``~/.bashrc``::

  export PATH="${PATH}:${HOME}/.local/bin"

.. note::

   You will have to restart your terminal in order for these changes to take effect.


Bash completions
~~~~~~~~~~~~~~~~
Bash completions are supported by sourcing the ``buildstream/data/bst``
script found in the BuildStream repository. On many systems this script
can be installed into a completions directory but when installing BuildStream
without a package manager this is not an option.

To enable completions for an installation of BuildStream you
installed yourself from git, just append the script verbatim
to your ``~/.bash_completion``:

.. literalinclude:: ../../buildstream/data/bst
   :language: yaml


Upgrading BuildStream
~~~~~~~~~~~~~~~~~~~~~

Via PyPI
++++++++

If you installed BuildStream from PyPI, you can update it like so::

  pip install --user --upgrade BuildStream

Via Git checkout
++++++++++++++++

If you installed BuildStream from a local git checkout using ``-e`` option, all
you need to do to upgrade BuildStream is to update your local git checkout::

  cd /path/to/buildstream
  git pull --rebase

If you did not specify the ``-e`` option at install time or the dependancies
have changed, you will need to cleanly reinstall BuildStream::

  pip3 uninstall buildstream
  cd /path/to/buildstream
  git pull --rebase
  pip3 install --user .


Installing from distro packages
-------------------------------


Arch Linux
~~~~~~~~~~
Packages for Arch exist in `AUR <https://wiki.archlinux.org/index.php/Arch_User_Repository#Installing_packages>`_.
Two different package versions are available:

* Latest release: `buildstream <https://aur.archlinux.org/packages/buildstream>`_
* Latest development snapshot: `buildstream-git <https://aur.archlinux.org/packages/buildstream-git>`_


Fedora
~~~~~~

BuildStream is not yet in the official Fedora repositories, but you can
install it from a Copr::

  sudo dnf copr enable bochecha/buildstream
  sudo dnf install buildstream

Optionally, install the ``buildstream-docs`` package to have the BuildStream
documentation in Devhelp or GNOME Builder.
