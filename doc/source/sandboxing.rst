
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

The filesystem inside sandboxes should be read only during element assembly,
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
<https://gitlab.com/BuildStream/buildstream/issues/38>`_ for more details.

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

BuildStream currently only carries first-class support for modern Linux-based
operating systems.

There is also a "fallback" backend which aims to make BuildStream usable on any
POSIX-compatible operating system. The POSIX standard does not provide good
support for creating containers so this implementation makes a number of
unfortunate compromises.

Linux
~~~~~

On Linux we use the following isolation and sandboxing primitives:

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
BuildStream still runs on such systems but will give a big warning on startup
and will refuse to push any artifacts built on such a system to a remote cache.
For more information, see `issue #92
<https://gitlab.com/BuildStream/buildstream/issues/92>`_.

The Linux platform can operate as a standard user provided user namespace
support is available. If user namespace support is not available you have the
option of installing bubblewrap as a setuid binary to avoid needing to run the
entire ``bst`` process as the ``root`` user.

The artifact cache on Linux systems is implemented using `OSTree
<https://github.com/ostreedev/ostree>`_, which can allow us to stage artifacts
using hardlinks instead of copying them. To avoid cache corruption it is
vital that hardlinked files cannot be overwritten. In cases where the root
filesystem inside the sandbox needs to be writable, a custom FUSE filesystem
named SafeHardlinks is used which provides a copy-on-write layer.

Some of the operations on filesystem metadata listed above are not prohibited
by the sandbox, but will instead be silently dropped when an artifact is
created. For more details see `issue #38
<https://gitlab.com/BuildStream/buildstream/issues/38>`_.

Some details of the host machine are currently leaked by this platform backend.
For more details, see `issue #262
<https://gitlab.com/BuildStream/buildstream/issues/262>`_.

Fallback (POSIX)
~~~~~~~~~~~~~~~~

The fallback backend aims to be usable on a wide range of operating systems.
Any OS that implements the POSIX specification and the ``chroot()`` syscall
can be expected to work. There are no real isolation or sandboxing primitives
that work across multiple operating systems, so the protection provided by
this backend is minimal. It would be much safer to use a platform-specific
backend.

Filesystem isolation is done using the chroot() system call. This system call
requires special privileges to use so ``bst`` usually needs to be run as the
``root`` user when using this backend.

Network access is not blocked in the sandbox. However since there is unlikely
to be a correct `/etc/resolv.conf` file, any network access that depends on
name resolution will most likely fail anyway.

Builds inside the sandbox execute as the ``root`` user.
