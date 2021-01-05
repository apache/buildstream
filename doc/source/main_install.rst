Installing
==========

Until BuildStream is available in your distro, you may need to install
it yourself from source. The necessary steps are:

* :ref:`Install dependencies<install-dependencies>`
* :ref:`Install BuildBox<install-buildbox>`
* :ref:`Install BuildStream<install-buildstream>` (from a git checkout, or from PyPi)
* :ref:`Update PATH<post-install>`

Alternatively, BuildStream can be run in :ref:`a container<install-container>`.


.. _install-dependencies:

Installing Dependencies
-----------------------

Before installing BuildStream from source, it is necessary to first install
the system dependencies. Below are some linux distribution specific instructions
for installing these dependencies.

BuildStream requires the following base system requirements:

- python3 >= 3.6
- pip
- :ref:`buildbox-casd<install-buildbox>`

BuildStream also depends on the host tools for the :mod:`Source <buildstream.source>` plugins.
Refer to the respective :ref:`source plugin <plugins_sources>` documentation for host tool
requirements of specific plugins.

The default plugins with extra host dependencies are:

- bzr
- git
- patch
- pip
- tar


Arch Linux
~~~~~~~~~~
Install the dependencies with::


    sudo pacman -S python python-pip


For the default plugins::


    sudo pacman -S bzr git lzip patch


Debian
~~~~~~
Install the dependencies with::


    sudo apt-get install \
        python3 python3-pip python3-dev

For the default plugins:

    sudo apt-get install \
        lzip git bzr patch


Fedora
~~~~~~
For recent fedora systems, the following line should get you the system
requirements you need::


    dnf install -y \
        python3 python3-pip python3-devel

For the default plugins::


    dnf install -y \
        bzr git lzip patch


Ubuntu
~~~~~~

Ubuntu 18.04 LTS or later
+++++++++++++++++++++++++
Install the dependencies with::


    sudo apt install \
        python3 python3-pip python3-dev

For the default plugins::


    sudo apt install \
        bzr git lzip patch



.. _install-buildbox:

Installing BuildBox
-------------------

BuildStream master now depends on buildbox-casd to manage the local CAS cache
and communicate with CAS servers. buildbox-run is used for sandboxing. BuildBox
components are still in development and there are no stable releases yet.
Thus, they're not available yet in Linux distros and they have to be manually
installed.

These components can be installed from binaries, or built from source.

Install binaries
~~~~~~~~~~~~~~~~
| Linux x86-64 users can download statically linked binaries: `buildbox-x86_64-linux.tar.xz <https://buildbox-casd-binaries.nyc3.cdn.digitaloceanspaces.com/buildbox-x86_64-linux-0.0.14-872f221d.tar.xz>`_
| ``sha256sum 872f221d06752bb3b7815fa8e59929dcdbc275543728ad1485675eace1c3e8ba``

The tarball contains the binaries ``buildbox-casd``, ``buildbox-fuse``,
``buildbox-run-bubblewrap`` and the symlink ``buildbox-run``, which should be
extracted into a directory in ``PATH``, e.g., ``~/.local/bin``.


Build from source
~~~~~~~~~~~~~~~~~

Each of the 4 buildbox components can be installed separately from their
respective git repositiories, and each respository has individual install
instructions. Make sure that you're installing the correct version of
each component.

| **Buildbox-common:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-common/-/blob/0.0.14/README.rst
| (Be sure to install from the 0.0.14 tag.)

| **Buildbox-casd:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-casd/-/blob/0.0.14/README.rst \
| (Be sure to install from the 0.0.14 tag.)

| **Buildbox-fuse:** See
| https://gitlab.com/BuildGrid/buildbox/buildbox-fuse/-/blob/0.0.14/INSTALL.rst
| (Be sure to install from the 0.0.14 tag.)

| **Buildbox-run-bublewrap:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-run-bubblewrap/-/blob/master/README.rst
| (Be sure to install from the 0.0.8 tag.)

Finally, configure buildbox-run-bubblewrap as the default buildbox-run
implementation::

    ln -sv buildbox-run-bubblewrap /usr/local/bin/buildbox-run


.. _install-buildstream:

Installing BuildStream
----------------------

Installing from PyPI
~~~~~~~~~~~~~~~~~~~~
Once you have the base system dependencies, you can install the BuildStream
python package as a regular user.

To install from PyPI, you will additionally require:

 - pip for python3 (only required for setup)
 - Python 3 development libraries and headers


For the latest dev snapshot of BuildStream 2, simply run the following command::

    pip3 install --user --pre BuildStream

This will install latest dev snapshot of BuildStream and its pure python
dependencies into your user's homedir in ``~/.local``.

.. note::

   At time of writing, BuildStream 2 is only available as dev snapshots; this
   is why the ``--pre`` option is required.  Running
   ``pip3 install --user BuildStream`` (without the ``--pre`` option)
   will install Buildsteam 1.

You can also install a specific dev snapshot of Buildstream by specifying the
version. eg ``pip3 install --user BuildStream==1.93.2.dev0``.
Available versions can be found on the BuildStream history page `on PyPi 
<https://pypi.org/project/BuildStream/#history>`_.
Note that some of the oldest versions are not available on PyPI.

Keep following the :ref:`instructions below<post-install>` to ensure that the ``bst``
command is in your ``PATH``.

Upgrading from PyPI
+++++++++++++++++++
Once you have already installed BuildStream from PyPI, you can later update
to the latest dev snapshot like so::


    pip3 install --user --upgrade --pre BuildStream



Installing from a git checkout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To install directly from the `git repository <https://github.com/apache/buildstream>`_
using python's ``pip`` package manager, you will additionally require:

- pip for python3 (only required for setup)
- Python 3 development libraries and headers
- git (to checkout BuildStream)

Before installing, please check the existing tags in the git repository
and determine which version you want to install.

Run the following commands::


    git clone https://github.com/apache/buildstream.git
    cd buildstream
    git checkout <desired release tag>
    pip3 install --user .

This will install BuildStream's pure python dependencies into
your user's homedir in ``~/.local`` and will run BuildStream directly
from the git checkout directory.

Keep following the instructions below to ensure that the ``bst``
command is in your ``PATH`` and to enable bash completions for it.


Upgrading from a git checkout
+++++++++++++++++++++++++++++
If you installed BuildStream from a local git checkout using ``-e`` option, all
you need to do to upgrade BuildStream is to update your local git checkout::

    cd /path/to/buildstream
    git pull --rebase

If you did not specify the ``-e`` option at install time, you will
need to cleanly reinstall BuildStream::

    pip3 uninstall buildstream
    cd /path/to/buildstream
    git pull --rebase
    pip3 install --user .


Installing in virtual environments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
You can consider installing BuildStream in a
`Virtual Environment <https://docs.python.org/3/tutorial/venv.html>`_ if you want
to install multiple versions of BuildStream, or to isolate BuildStream and its
dependencies from other Python packages.

Here is how to install BuildStream stable and development snapshot releases in
virtual environments of their own::


    # Install BuildStream stable in an environment called "venv-bst-stable"
    # (At time of writing, this will be BuildStream 1)
    python3 -m venv venv-bst-stable
    venv-bst-stable/bin/pip install BuildStream

    # Install BuildStream latest development snapshot in an environment
    # called "venv-bst-latest"
    # (At time of writing, this will be Buildstream 2)
    python3 -m venv venv-bst-latest
    venv-bst-latest/bin/pip install --pre BuildStream

To start using BuildStream from the desired environment, you will need to
activate it first. Activating it will automatically add ``bst`` to your ``PATH``
and set up other necessary environment variables::


    # Use BuildStream stable from venv-bst-stable
    source venv-bst-stable/bin/activate
    bst --version

    # Use BuildStream latest from venv-bst-latest
    source venv-bst-latest/bin/activate
    bst --version

    # Once you are done, remember to deactivate the virtual environment
    deactivate

If you do not want to manage your virtual environments manually, you can
consider using `pipx <https://docs.python.org/3/tutorial/venv.html>`_.


.. _post-install:

Post-install setup
------------------

After having installed from source using any of the above methods, some
setup will be required to use BuildStream.



Adjust ``PATH``
~~~~~~~~~~~~~~~
Since BuildStream is now installed under your local user's install directories,
you need to ensure that ``PATH`` is adjusted.

A regular way to do this is to add the following line to the end of your ``~/.bashrc``::

  export PATH="${PATH}:${HOME}/.local/bin"

.. note::

   You will have to restart your terminal in order for these changes to take effect.


.. _install-container:


Buildstream Inside a Container
-------------------------------
If your system cannot provide the base requirements, it is possible to run
BuildStream within a container. This gives you an easy way to get started
using BuildStream on any Unix-like platform where containers are available,
including macOS. 

For details, see the `Buildstream Docker documentation
<https://gitlab.com/BuildStream/buildstream-docker-images/-/blob/master/USING.md>`_
