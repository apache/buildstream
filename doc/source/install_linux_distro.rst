
.. _install:

Installing BuildStream on a Linux distro
========================================


Installing from distro packages
-------------------------------


Arch Linux
~~~~~~~~~~
Packages for Arch exist in `AUR <https://wiki.archlinux.org/index.php/Arch_User_Repository#Installing_packages>`_.
Two different package versions are available:

 - BuildStream latest release: `buildstream <https://aur.archlinux.org/packages/buildstream>`_
 - BuildStream latest development snapshot: `buildstream-git <https://aur.archlinux.org/packages/buildstream-git>`_

The external plugins are available as well:

 - BuildStream-external plugins latest release: `bst-external` https://aur.archlinux.org/packages/bst-external>`_


Fedora
~~~~~~
BuildStream is in the official Fedora repositories::

  sudo dnf install buildstream

Optionally, install the `buildstream-docs` package to have the BuildStream
documentation in Devhelp or GNOME Builder.


Installing from source
----------------------
Until BuildStream is available in your distro, you will need to install
it yourself from the `git repository <https://gitlab.com/BuildStream/buildstream.git>`_
using python's ``pip`` package manager.

BuildStream requires the following base system requirements:

* python3 >= 3.5
* libostree >= v2017.8 with introspection data
* bubblewrap >= 0.1.2
* fuse2
* psutil python library (so you don't have to install GCC and python-devel to build it yourself)

BuildStream also depends on the host tools for the :mod:`Source <buildstream.source>` plugins.
Refer to the respective :ref:`source plugin <plugins_sources>` documentation for host tool
requirements of specific plugins.

If you intend to push built artifacts to a remote artifact server,
which requires special permissions, you will also need:

* ssh

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

  sudo pacman -S fuse2 ostree bubblewrap git \
                 python python-pip python-gobject python-psutil lzip


Debian
++++++


Stretch
^^^^^^^
With stretch, you first need to ensure that you have the backports repository
setup as described `here <https://backports.debian.org/Instructions/>`__

By adding the following line to your sources.list::

  deb http://ftp.debian.org/debian stretch-backports main

And then running::

  sudo apt-get update

At this point you should be able to get the system requirements with::

  sudo apt-get install \
      fuse ostree gir1.2-ostree-1.0 bubblewrap git \
      python3 python3-pip python3-gi python3-psutil lzip
  sudo apt-get install -t stretch-backports \
      gir1.2-ostree-1.0 ostree


Buster and newer
^^^^^^^^^^^^^^^^
The following line should be enough
to get the base system requirements installed::

  sudo apt-get install \
      fuse ostree gir1.2-ostree-1.0 bubblewrap git \
      python3 python3-pip python3-gi python3-psutil lzip


Fedora
++++++
For recent fedora systems, the following line should get you the system
requirements you need::

  dnf install -y fuse ostree bubblewrap git \
                 python3 python3-pip python3-gobject python3-psutil lzip


Installing
~~~~~~~~~~
Once you have the base system dependencies, you can clone the BuildStream
git repository and install it as a regular user::

  git clone https://github.com/apache/buildstream.git
  cd buildstream
  git checkout <VERSION_TAG>
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

   You can view available version tags `here <https://github.com/apache/buildstream/tags>`__
   for example to install version 1.6.6 ``git checkout 1.6.6``

   You may require ``bst-external`` the install instructions can be found on the `bst-external gitlab <https://gitlab.com/BuildStream/bst-external>`__

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
Assuming you have followed the default instructions above, all
you need to do to upgrade BuildStream is to update your local git
checkout::

  cd /path/to/buildstream
  git pull --rebase

If you did not specify the ``-e`` option at install time, you will
need to cleanly reinstall BuildStream::

  pip3 uninstall buildstream
  cd /path/to/buildstream
  git pull --rebase
  pip3 install --user .
