..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

Installing from Source
======================

This page explains how to build and install this version of BuildStream from
source. For general purpose installation instructions consult the
`website <https://buildstream.build/install.html>`_.

For full install instructions, read on:

* :ref:`Install dependencies<install-dependencies>`
* :ref:`Install BuildBox<install-buildbox>`
* :ref:`Install BuildStream<install-buildstream>`
* :ref:`Install completions<install-completions>`

.. _install-dependencies:

Installing Dependencies
-----------------------

Runtime requirements
~~~~~~~~~~~~~~~~~~~~

BuildStream requires the following Python environment to run:

- python3 >= 3.9
- PyPI packages as specified in
  `requirements.in <https://github.com/apache/buildstream/blob/master/requirements/requirements.in>`_.

Some :mod:`Source <buildstream.source>` plugins require specific tools installed
on the host. Here is a commonly used subset based on the
:ref:`core source plugins <plugins_sources>`
and `buildstream-plugins <https://apache.github.io/buildstream-plugins/>`_.

- git (for ``git`` sources)
- lzip (for ``.tar.lz`` support in ``tar`` sources)
- patch (for ``patch`` sources)

Some BuildBox tools used by BuildStream require additional host tools:

- bubblewrap (for ``buildbox-run-bubblewrap``)
- fusermount3 (for ``buildbox-fuse``)

Install-time requirements
~~~~~~~~~~~~~~~~~~~~~~~~~

BuildStream contains Cython code which implies the following extra
dependencies at install-time only:

- C and C++ toolchain
- Python development headers

These instructions use ``pip3`` to install necessary PyPI packages.
Packagers and integrators may use a different tool and can ignore
the `pip` dependency below.

Distribution-specific guides
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This table gives you a list of packages for specific distros:

.. list-table::

  * - **Distribution**
    - **Runtime requires**
    - **Install requires**
  * - Arch Linux
    - bubblewrap fuse3 git lzip patch python
    - gcc python-pip
  * - Debian
    - bubblewrap fuse3 git lzip patch python3
    - g++ python3-dev python3-pip
  * - Fedora
    - bubblewrap fuse3 git lzip patch python3
    - gcc-c++ python3-devel python3-pip
  * - Ubuntu
    - bubblewrap fuse3 git lzip patch python3
    - g++ python3-dev python3-pip

.. _install-buildbox:

Installing BuildBox
-------------------

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

Buildbox components can be installed from their git repository.
We recommend installing from the latest release tag.

See the <"Installation" section here <https://gitlab.com/BuildGrid/buildbox/buildbox/-/blob/master/README.rst#installation>`_.

Buildbox contains many components, BuildStream needs only ``buildbox-casd``,
``buildbox-fuse`` and ``buildbox-run-bubblewrap``, which can be selected by
passing options ``-DTOOLS=OFF -DCASD=ON -DFUSE=ON -DRUN_BUBBLEWRAP=ON`` to CMake.

Finally, configure buildbox-run-bubblewrap as the default buildbox-run
implementation::

    ln -sv buildbox-run-bubblewrap /usr/local/bin/buildbox-run



.. _install-buildstream:

Installing BuildStream from a git checkout
------------------------------------------

First, clone the repository. Please check the existing tags in the git
repository and determine which version you want to install::


    git clone https://github.com/apache/buildstream.git
    cd buildstream
    git checkout <desired release tag>

We recommend ``pip`` as a frontend to the underlying ``setuptools`` build
system.  The following command will build and install BuildStream into your
user's homedir in ``~/.local``, and will attempt to fetch and install any
required PyPI dependencies from the internet at the same time::


    pip3 install --user .

We do not recommend using Pip's `editable mode <https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs>`_
(the ``-e`` flag). See `this issue <https://github.com/apache/buildstream/issues/1760>`_ for discussion.

If you want to stop Pip from fetching missing dependencies, use the
``--no-index`` and ``--no-deps`` options.

Finally, check that the ``PATH`` variable contains the ``~/.local/bin`` directory.
If it doesn't, you could add this to the end of your Bash configuration ``~/.bashrc``
and restart Bash::

  export PATH="${PATH}:${HOME}/.local/bin"

Note for packagers
~~~~~~~~~~~~~~~~~~

Distro packaging standards may recommend a specific installation method
for Python packages.  BuildStream can be installed with any build frontend that
supports the `PEP517 standard <https://peps.python.org/pep-0517/>`_. You are
also welcome to use the underlying
`setuptools <https://setuptools.pypa.io/en/latest/>`_ build backend directly.


.. _install-virtual-environment:

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

.. _install-completions:

Installing completions
----------------------

BuildStream integrates with Bash and Zsh to provide helpful tab-completion.
These completion scripts require manual installation.

Bash completions
~~~~~~~~~~~~~~~~

Bash completions are provided by the ``bst`` completion script, available online
(`src/buildstream/data/bst <https://raw.githubusercontent.com/apache/buildstream/master/src/buildstream/data/bst>`_)
and in your local Git clone at ``src/buildstream/data/bst``.

To install for the current user, paste the contents of the completion script
into the file ``~/.bash_completion``.

To install completions system-wide, copy the completion script to the system-wide
bash-completion installation path, which you can discover as follows::

    pkg-config --variable=completionsdir bash-completion

See the `bash-completion FAQ <https://github.com/scop/bash-completion#faq>`_
for more information.

Zsh completions
~~~~~~~~~~~~~~~~

Zsh completions are provided by the ``_bst`` completion script, available online
(`src/buildstream/data/zsh/_bst <https://raw.githubusercontent.com/apache/buildstream/master/src/buildstream/data/zsh/_bst>`_)
and in your local Git clone at ``src/buildstream/data/zsh/_bst``.

Copy the above file to your Zsh completions location. Here are some instructions
for vanilla Zsh, as well as the *Prezto* and *Oh My Zsh* frameworks:

**Zsh**::

    cp src/buildstream/data/zsh/_bst ~/.zfunc/_bst

You must then add the following lines in your ``~/.zshrc``, if they do not already exist::

    fpath+=~/.zfunc
    autoload -Uz compinit && compinit


**Prezto**::

    cp src/buildstream/data/zsh/_bst ~/.zprezto/modules/completion/external/src/_bst

You may have to reset your zcompdump cache, if you have one, and then restart your shell::

    rm ~/.zcompdump ${XDG_CACHE_HOME:-$HOME/.cache}/prezto/zcompdump

**Oh My Zsh**::

    mkdir $ZSH_CUSTOM/plugins/bst
    cp src/buildstream/data/zsh/_bst $ZSH_CUSTOM/plugins/bst/_bst

You must then add ``bst`` to your plugins array in ``~/.zshrc``::

    plugins(
      bst
      ...
    )
