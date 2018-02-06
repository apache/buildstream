:orphan:

.. _image_authoring:

Authoring System Images
=======================
This section forms a guide to creating system images with BuildStream.

Building a Linux image
----------------------

.. note::

   This page does *not* list all files required for the project, it
   merely comments on noteworthy sections. See `this repository
   <https://gitlab.com/tlater/image-test>`_ for the full project.

Setting up the project
~~~~~~~~~~~~~~~~~~~~~~

To create an image, we will want to use the x86image plugin from the
``bst-external`` repository. The ``bst-external`` repository is a
collection of plugins that are either too niche or unpolished to
include as plugins in the main repository, but are useful for various
purposes.

If you have not already, install the latest version of this
repository:

.. code:: bash

  git clone https://gitlab.com/BuildStream/bst-external.git
  cd bst-external
  pip3 install .

This should make bst-external plugins available to buildstream. To use
the x86image and docker plugins in our project, we need to set up
plugins in our ``project.conf``:

.. literalinclude:: image/project.conf
    :caption: project.conf
    :linenos:
    :language: yaml
    :lines: -17

We also set aliases for all project pages we will be fetching sources
from, should we later want to change their location (e.g. when we
decide that we want to mirror the files in our datacenter for
performance reasons):

.. literalinclude:: image/project.conf
    :caption: project.conf (continued)
    :language: yaml
    :lineno-start: 17
    :linenos:
    :lines: 18-

Base System
~~~~~~~~~~~

The base system will be used to *build* the image and the project, but
it won't be a part of the final result. It should contain everything
that is required to build both the project and the tools required to
create an image.

The x86image plugin requires a specific set of tools to create an
image. To make using this plugin easier, we provide an alpine-based
base system using docker that contains all required tools:

.. literalinclude:: image/elements/base.bst
    :caption: elements/base.bst
    :language: yaml
    :linenos:

This image only provides musl-libc and busybox for building, should
your project require GNU tools it will be simpler to create your own
and ensure that your base system includes the following packages:

* parted
* mtools
* e2fsprogs
* dosfstools
* syslinux
* nasm
* autoconf
* gcc
* g++
* make
* gawk
* bc
* linux-headers


Image Contents
~~~~~~~~~~~~~~

The final linux image will consist of several elements that can be
broadly summarized in four scopes:

1. A sysroot
2. An initramfs
3. A Linux kernel
4. Project-specific elements

A sysroot
+++++++++

Before we create the elements to make an actual image, we will set up
the sysroot that will form the user space. For this tutorial, we will
create a very simple system.

The sysroot must contain everything required to run a Linux system -
this will usually be `GNU coreutils
<https://www.gnu.org/software/coreutils/coreutils.html>`_ or `BusyBox
<https://www.busybox.net/about.html>`_ - and any runtime dependencies,
if these tools are not statically linked - often `glibc
<https://www.gnu.org/software/libc/>`_ or
`musl <https://www.musl-libc.org/>`_.

For this tutorial we will build a BusyBox + musl system:

.. code:: yaml

    kind: stack
    description: The image contents
    depends:
    - contents/busybox.bst

A keen eye may notice that this does not include a ``musl.bst``
dependency - this is because the busybox element itself is set to
run-depend on musl, which we use later to stage sysroot content, but
not the base system.

For the specifics of the included elements, refer to the accompanying
project repository.

An initramfs
++++++++++++

Now that we have defined the basic sysroot we can also set up an
`initramfs <https://en.wikipedia.org/wiki/Initial_ramdisk>`_ - we do
this now, because we have defined the most basic root file system that
will be booted into (for the sake of brevity we will not set up any
kernel modules, otherwise these should be built first and included in
the initramfs).

For our initramfs we will want an ``init`` and ``shutdown`` script,
and a copy of the sysroot created previously. We start with an
initramfs-scripts element:

.. literalinclude:: image/elements/image/initramfs/initramfs-scripts.bst
    :caption: elements/image/initramfs/initramfs-scripts.bst
    :language: yaml
    :linenos:

This will simply place the ``init`` and ``shutdown`` scripts located
in ``files/initramfs-scripts`` in ``/sbin``, where they can later be
found and executed.

We then define our initramfs as the intersection between our
initramfs-scripts and sysroot content:

.. literalinclude:: image/elements/image/initramfs/initramfs.bst
    :caption: elements/image/initramfs/initramfs.bst
    :language: yaml
    :linenos:

Finally we create an element that produces the cpio archive and
compress it using gzip:

.. literalinclude:: image/elements/image/initramfs/initramfs-gz.bst
    :caption: elements/image/initramfs/initramfs-gz.bst
    :language: yaml
    :linenos:

A Linux kernel
++++++++++++++

Now that our final environment is set up, we create the Linux kernel
that will drive it. Setup for this is a little less intricate since it
only involves building a single project:


.. literalinclude:: image/elements/image/linux.bst
    :caption: elements/image/linux.bst
    :language: yaml
    :linenos:
    :lines: -16

.. literalinclude:: image/elements/image/linux.bst
    :caption: elements/image/linux.bst (continued)
    :language: yaml
    :lineno-start: 272
    :linenos:
    :lines: 272-

The main complexity in compiling a Linux kernel is its configuration;
the 'correct' settings depend a lot on the project. The remaining
configuration should be quite portable to other builds, however, and
simply deals with placing files in the correct locations.

Project-specific elements
+++++++++++++++++++++++++

Finally, our project-specific files should be included. For a real
project, this may be an installer, 'rescue' applications such as
parted, distribution-specific files or similar.

In our case, we will include a ``hello`` script that simply prints
``Hello World!``, as is tradition:

.. literalinclude:: image/elements/contents/hello.bst
    :caption: elements/contents/hello.bst
    :language: yaml
    :linenos:

We also update the ``contents.bst`` file to include our project
target:

.. literalinclude:: image/elements/contents.bst
    :caption: elements/contents.bst
    :language: yaml
    :linenos:

While our ``hello`` element run-depends on busybox, our contents
*must* include a working set of coreutils - we make this explicit by
also depending on busybox.

Creating the image
~~~~~~~~~~~~~~~~~~

Now that all image content is defined, we can create the elements that
actually build the image. The x86image plugin requires two elements:

- A base system that contains the tools to create an image
- An element that contains the system we want to create an image of

We already have ``base.bst``, which conveniently contains all tools we
need (we could have used a separate base system to create the image),
but we still need to create a system element.

For the system element, we simply collect the image content elements
and their runtime dependencies:

.. literalinclude:: image/elements/image/system.bst
    :caption: elements/image/system.bst
    :language: yaml
    :linenos:

We can now define our image element - we start by depending on the
above elements:

.. literalinclude:: image/elements/image-x86_64.bst
    :caption: elements/image-x86_64.bst
    :language: yaml
    :linenos:
    :lines: -12

We then set a few parameters to suit our system:

.. literalinclude:: image/elements/image-x86_64.bst
    :caption: elements/image-x86_64.bst (continued)
    :language: yaml
    :lineno-start: 16
    :linenos:
    :lines: 16-31

The correct values for these parameters will depend on the specific
image created, but for this project the following values were used:

boot-size
	The size of ``/boot`` as created by ``image/system.bst`` - the
	system can be inspected using ``bst checkout``.

rootfs-size
	The size of ``/`` as created by ``image/system.bst``.

sector-size
	The default size of 512 should work in most cases, your
	requirements may differ.

swap-size
	The desired size for the swap partition.

kernel-args
  The kernel arguments - the image plugin will by default create the
  following ``/etc/fstab``:

  .. code::

    /dev/sda2   /       ext4   defaults,rw,noatime   0 1
    /dev/sda1   /boot   vfat   defaults              0 2
    /dev/sda3   none    swap   defaults              0 0

  Hence we specify ``root=/dev/sda2`` and ``rootfstype=ext4``.

  ``image/initramfs-scripts.bst`` defines our init script as
  ``/sbin/init``, hence we set ``init=/sbin/init``.

  Finally, qemu (which we will use to try out this image)
  requires our console to be on ttyS0, so we specify
  ``console=ttyS0``.

kernel-name
  The default name of the kernel name as created by
  ``image/linux.bst`` is ``vmlinuz-4.14.3``, and since this is easier
  than renaming it we specify that value.

The final configuration specifies which dependencies to use as the
base/system elements, and creates a script to launch our image using
qemu:

.. literalinclude:: image/elements/image-x86_64.bst
    :caption: elements/image-x86_64.bst (continued)
    :language: yaml
    :lineno-start: 32
    :linenos:
    :lines: 32-

Building the image
~~~~~~~~~~~~~~~~~~

We have now defined everything required to build a basic Linux
image. With bst and the bst-external plugin repository installed, we
can now build and boot our image.

We first run ``bst track --deps all image-x86_64.bst`` to determine
references for all sources used to build this project. We then run
``bst build image-x86_64.bst`` to build and finally ``bst checkout
image-x86_64.bst image`` to retrieve our finalized image.

To test the result, simply run ``cd image/ && ./run-in-qemu.sh``
(perhaps as root), and the image should boot.
