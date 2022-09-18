Installing
==========

BuildStream is packaged in some Linux distributions. If your distro has an
up-to-date package we recommend using that. The table at
`repology.org <https://repology.org/project/buildstream/versions>`_ may be
useful.

For full install instructions, read on:

* :ref:`Install dependencies<install-dependencies>`
* :ref:`Install BuildStream<install-buildstream>` (from a git checkout, or from PyPi)
* :ref:`Install BuildBox<install-buildbox>` (if needed)
* :ref:`Update PATH<post-install>`

BuildStream can also be run in :ref:`a container<install-container>`.

.. _install-dependencies:

Installing Dependencies
-----------------------

BuildStream has the following base system requirements:

- python3 >= 3.7
- pip (during installation only)

Some :mod:`Source <buildstream.source>` plugins require additional host tools.
Here is a useful subset based on the :ref:`core source plugins <plugins_sources>`
and `buildstream-plugins <https://apache.github.io/buildstream-plugins/>`_.

- git (for ``git`` sources)
- lzip (for ``.tar.lz`` support in ``tar`` sources)
- patch (for ``patch`` sources)

Some BuildBox tools used by BuildStream require additional host tools
for full functionality and performance:

- bubblewrap (for ``buildbox-run-bubblewrap``)
- fusermount3 (for ``buildbox-fuse``)

Additional Python dependencies will be installed via Pip in the next stage.
Several of these include some Cython code and/or bundled C++ source code.
Prebuilt binary "wheel" packages are provided for some platforms and in this
case there are no extra requirements on the host.

In the case that no binary package is available, Pip will try to install from
source. This implies extra install-time requirements:

- C and C++ toolchain
- Python development headers

Arch Linux
~~~~~~~~~~

Install the recommended dependencies with::


    sudo pacman -S bubblewrap fuse3 git lzip patch python python-pip


If needed, get the additional install-time dependencies with::


    sudo pacman -S gcc


Debian
~~~~~~
Install the recommended dependencies with::


    sudo apt-get install \
        git lzip patch bubblewrap fuse3 python3-pip python3


If needed, get the additional install-time dependencies with::


    sudo apt-get install g++ python3-dev

Fedora
~~~~~~
For recent fedora systems, the following line should get you the system
requirements you need::


    dnf install -y \
        python3 python3-pip bubblewrap fuse3 lzip git patch


If needed, get the additional install-time dependencies with::

    dnf install -y gcc-c++ python3-devel


Ubuntu
~~~~~~
Install the recommended dependencies with::


    sudo apt-get install \
        git lzip patch bubblewrap fuse3 python3-pip python3


If needed, get the additional install-time dependencies with::


    sudo apt-get install g++ python3-dev


.. _install-buildstream:

Installing BuildStream
----------------------

Installing from PyPI
~~~~~~~~~~~~~~~~~~~~

For the latest release of BuildStream 2, including the necessary Python
dependencies and BuildBox tools, run the following command::

    pip3 install --user BuildStream

This will install BuildStream and its dependencies into your user's homedir in
``~/.local``.  Pip will use binary "wheel" packages from PyPI where these are
available for your platform. Otherwise it will build bundled C++ and Cython
code from source, which requires the additional install-time only dependencies
documented in the previous section.

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
to the latest release like so::


    pip3 install --user --upgrade BuildStream



Installing from a git checkout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To install directly from the `git repository <https://github.com/apache/buildstream>`_
using python's ``pip`` package manager, you will require the extra install-time
dependencies documented above.

Before installing, please check the existing tags in the git repository
and determine which version you want to install.

Run the following commands::


    git clone https://github.com/apache/buildstream.git
    cd buildstream
    git checkout <desired release tag>
    pip3 install --user .

This will install BuildStream into your user's homedir in ``~/.local``, along
with neccessary Python dependencies fetched from PyPI.

You can optionally use Pip's
`editable mode <https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs>`_
(the ``-e`` flag) in this case.

Keep following the instructions below to ensure that the ``bst``
command is in your ``PATH`` and to enable bash completions for it.


Upgrading from a git checkout
+++++++++++++++++++++++++++++
If you installed BuildStream from a local git checkout using the ``-e``
option, all you need to do to upgrade BuildStream is to update your local git
checkout::

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


    # Install BuildStream 2.0 in an environment called "venv-bst2"
    python3 -m venv venv-bst2
    venv-bst-stable/bin/pip install BuildStream

    # Install BuildStream 1.0 in an environment called "venv-bst1"
    # (At time of writing, this will be Buildstream 1)
    python3 -m venv venv-bst1
    venv-bst-latest/bin/pip install BuildStream==1

To start using BuildStream from the desired environment, you will need to
activate it first. Activating it will automatically add ``bst`` to your ``PATH``
and set up other necessary environment variables::


    # Use BuildStream 2.0 from venv-bst2
    source venv-bst2/bin/activate
    bst --version

    # Use BuildStream 1.0 from venv-bst1
    source venv-bst1/bin/activate
    bst --version

    # Once you are done, remember to deactivate the virtual environment
    deactivate

If you do not want to manage your virtual environments manually, you can
consider using `pipx <https://docs.python.org/3/tutorial/venv.html>`_.


.. _install-buildbox:

Installing BuildBox
-------------------

The BuildStream binary packages from PyPI contain working BuildBox binaries.
If these are installed on your system, the following command will tell you::

    pip3 show --files buildstream | grep subprojects/buildbox

If you see no output here, you will need to follow the below instructions to
obtain BuildBox.

BuildStream depends on the following tools from
`BuildBox <https://gitlab.com/BuildGrid/buildbox/>`_:

  * ``buildbox-casd`` (to manage local and remote content-addressed storage)
  * ``buildbox-fuse`` (to check out content from the local CAS)
  * ``buildbox-run-bubblewrap`` (to run element commands in a controlled sandbox)

These components can be installed from binaries, or built from source.

Install binaries
~~~~~~~~~~~~~~~~
Browse the `release history of static binaries here
<https://gitlab.com/BuildGrid/buildbox/buildbox-integration/-/releases>`_.

Linux x86-64 users can download the `latest statically linked binaries here
<https://gitlab.com/BuildGrid/buildbox/buildbox-integration/-/releases/permalink/latest/downloads/buildbox-x86_64-linux-gnu.tgz>`_,
The contents of the tarball should be extracted into a directory in ``PATH``,
e.g., ``~/.local/bin``.


Build from source
~~~~~~~~~~~~~~~~~

Each of the 4 buildbox components can be installed separately from their
respective git repositiories, and each respository has individual install
instructions. We recommend installing the latest release tag of each
component.

| **Buildbox-common:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-common/-/blob/master/README.rst
| (Be sure to install from the latest stable release tag.)

| **Buildbox-casd:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-casd/-/blob/master/README.rst \
| (Be sure to install from the latest stable release tag.)

| **Buildbox-fuse:** See
| https://gitlab.com/BuildGrid/buildbox/buildbox-fuse/-/blob/master/INSTALL.rst
| (Be sure to install from the latest stable release tag.)

| **Buildbox-run-bublewrap:** See the installation section in:
| https://gitlab.com/BuildGrid/buildbox/buildbox-run-bubblewrap/-/blob/master/README.rst
| (Be sure to install from the latest stable release tag.)

Finally, configure buildbox-run-bubblewrap as the default buildbox-run
implementation::

    ln -sv buildbox-run-bubblewrap /usr/local/bin/buildbox-run


.. _post-install:

Post-install setup
------------------

After having installed from source using any of the above methods, some
setup may be required to use BuildStream.



Adjust ``PATH``
~~~~~~~~~~~~~~~
If BuildStream is now installed under your local user's install directories,
you need to ensure that ``PATH`` is adjusted.

A regular way to do this is to add the following line to the end of your ``~/.bashrc``::

  export PATH="${PATH}:${HOME}/.local/bin"

.. note::

   You will have to restart your terminal in order for these changes to take effect.


.. _install-container:

Buildstream Inside a Container
-------------------------------

It is possible to run BuildStream in an OCI container tool such as Docker.
This gives you an easy way to get started using BuildStream on any Unix-like
platform where containers are available, including macOS.

Prebuilt images are available, see the documentation
`here <https://gitlab.com/BuildStream/buildstream-docker-images/-/blob/master/USING.md>`_

You can also produce your own container images, either by adapting the
`buildstream-docker-images project <https://gitlab.com/BuildStream/buildstream-docker-images/>`_,
or by following the full installation instructions above.

Note that some special configuration is often needed to run BuildStream in a container:

  * User namespaces are used to isolate and control builds. This requires the
    Docker ``--privileged`` mode.
  * FUSE should be available in the container, achieved via the Docker
    ``--device /dev/fuse`` option.
