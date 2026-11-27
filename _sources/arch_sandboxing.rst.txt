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


.. _sandboxing:


Sandboxing
==========

Introduction
------------

BuildStream assembles each element in a *sandbox*. The sandbox is a container
environment which serves two purposes: giving BuildStream control over
all build aspects in order to ensure reproducibility of build results,
and providing safety guarantees for the host system that BuildStream is
running on.

The exact implementation of the sandbox varies depending on which platform you
are running BuildStream. See below for backend-specific details.

There are several factors that affect the build output and must therefore be
under BuildStream's control:

* Filesystem contents and metadata
* The user and permissions model
* Network access
* Device access

Each of these is detailed below.

For safety reasons, BuildStream also controls the following things:

* Access to files outside of the sandbox directory
* Access to certain kernel-specific syscalls

Creating a sandbox can require special priviliges. This is a safety concern too
because bugs in the `bst` program can cause damage to a host if the program is
running with extra privileges. The exact priviliges that are required depend on
your platform and backend.

Element plugins can run arbitary commands within the sandbox using the
:mod:`sandbox API <buildstream.sandbox.sandbox>`.

What elements can and can't do in the sandbox
---------------------------------------------

This section specifies how BuildStream sandboxes are intended to work. A
specific sandbox provider may not necessarily be able to achieve all of the
requirements listed below so be sure to read the "platform notes" section as
well.

Filesystem access
~~~~~~~~~~~~~~~~~

The filesystem inside sandboxes should be read-only during element assembly,
except for certain directories which element plugins can mark as being
read/write. Most elements plugins derive from :mod:`BuildElement
<buildstream.buildelement>`, which marks ``%{build-root}`` and
``%{install-root}`` as read/write.

When running integration commands or `bst shell`, the sandbox should have a
fully read-write filesystem. The changes made here do not need to persist
beyond the lifetime of that sandbox, and **must not** affect the contents of
artifacts stored in the cache.

Certain top level directories should be treated specially in all sandboxes:

* The ``/dev`` directory should contain device nodes, which are described in
  a separate section.

* The ``/proc`` directory should have a UNIX 'procfs' style filesystem mounted.
  It should not expose any information about processes running outside of the
  sandbox.

* The ``/tmp`` directory should be writable.

Filesystem metadata
~~~~~~~~~~~~~~~~~~~

The writable areas inside a BuildStream sandbox are limited in what metadata
can be written and stored.

* All files must be owned by UID 0 and GID 0
* No files may have the setuid or setgid bits set
* Extended file attributes (xattrs) cannot be written to or read.
* Hardlinks to other files can be created, but the information about which
  files are hardlinked to each other will not be stored in the artifact
  that is created from the sandbox.

These restrictions are due to technical limitations. In future we hope to
support a wider range of filesystem metadata operations. See `issue #38
<https://github.com/apache/buildstream/issues/38>`_ for more details.

User and permissions model
~~~~~~~~~~~~~~~~~~~~~~~~~~

All commands inside the sandbox run with user ID 0 and group ID 0. It should
not be possible to become any other user ID.

Network access
~~~~~~~~~~~~~~

Builds should not be able to access the network at all from the sandbox. All
remote resources needed to build an element must be specified in the element's
``sources`` list so that BuildStream is able to see when they have changed.

A sandbox opened by `bst shell` should allow network access.

Device access
~~~~~~~~~~~~~

Builds should not be able to access any hardware devices at all.

A few standard UNIX device files are needed, the whitelist is:

* ``/dev/full``
* ``/dev/null``
* ``/dev/urandom``
* ``/dev/random``
* ``/dev/zero``

It may seem odd that we have sources of randomness in the sandbox, but a lot of
tools do expect them to exist. We take the view that it's up to integrators to
ensure that elements do not deliberately include randomness in their output.

A sandbox opened by `bst shell` can make any devices available. There needs to
be a console device so that it can be used interactively.

Platform notes
--------------

BuildStream delegates sandboxing for local builds to the ``buildbox-run``
command. ``buildbox-run`` provides a platform-independent interface to execute
commands in a sandbox based on parts of the Remote Execution API.

Linux
~~~~~

The recommended ``buildbox-run`` implementation for Linux is
``buildbox-run-bubblewrap``, in combination with ``buildbox-fuse``.

These implementations use the following isolation and sandboxing primitives:

* bind mounts
* FUSE
* Mount namespaces
* Network namespaces
* PID (process ID) namespaces
* User namespaces (if available)
* seccomp

We access all of these features through a sandboxing tool named `Bubblewrap
<https://github.com/projectatomic/bubblewrap/>`_.

User namespaces are not enabled by default in all Linux distributions.
BuildStream still runs on such systems but can't build projects that set
``build-uid`` or ``build-gid`` in the ``sandbox`` configuration.

The Linux platform can operate as a standard user, if unprivileged user namespace
support is available. If user namespace support is not available you have the
option of installing bubblewrap as a setuid binary to avoid needing to run the
entire ``bst`` process as the ``root`` user.

FUSE is used to provide access to directories and files stored in CAS without
having to copy or hardlink the complete input tree into a regular filesystem
directory structure for each build job.

Some of the operations on filesystem metadata listed above are not prohibited
by the sandbox, but will instead be silently dropped when an artifact is
created. For more details see `issue #38
<https://github.com/apache/buildstream/issues/38>`_.

Some details of the host machine are currently leaked by this platform backend.
For more details, see `issue #262
<https://github.com/apache/buildstream/issues/262>`_.

Other POSIX systems
~~~~~~~~~~~~~~~~~~~

On other POSIX systems ``buildbox-run-userchroot`` may be used for sandboxing.
`userchroot <https://gitlab.com/BuildGrid/buildbox/userchroot>`_ allows regular
users to invoke processes in a chroot environment.

``buildbox-run-userchroot`` stages the input tree for each build job using
hardlinks to avoid more expensive file copies. To avoid cache corruption it is
vital that hardlinked files cannot be overwritten. Due to this it's required
to run ``buildbox-casd`` as a separate user, which owns the files in the local
cache.

Network access is not blocked in the chroot. However since there is unlikely
to be a correct `/etc/resolv.conf` file, any network access that depends on
name resolution will most likely fail anyway.
