.. _image_authoring:

Authoring System Images
=======================
This section forms a guide to creating system images with BuildStream.

Building a Linux image
----------------------

Setting up the project
~~~~~~~~~~~~~~~~~~~~~~

To create an image, we will want to use the x86image plugin from the
``bst-external`` repository. The ``bst-external`` repository is a
collection of plugins that are either too niche or unpolished to
include as plugins in the main repository, but are useful for various
purposes.

If you have not already, install the latest version of this
repository:

	git clone https://gitlab.com/BuildStream/bst-external.git
	cd bst-external
	pip3 install .

This should make bst-external plugins available to buildstream. To use
the x86image and docker plugins in our project, we need to set up
plugins in our =project.conf=:

#+INCLUDE: "./project.conf" example yaml :lines "-17"

We also set aliases for all project pages we will be fetching sources
from, should we later want to change their location (e.g. when we
decide that we want to mirror the files in our datacenter for
performance reasons):

#+INCLUDE: "./project.conf" example yaml :lines "17-"

Base System
~~~~~~~~~~~

The base system will be used to *build* the image and the project, but
it won't be a part of the final result. It should contain everything
that is required to build both the project and the tools required to
create an image.

The x86image plugin requires a specific set of tools to create an
image. To make using this plugin easier, we provide an alpine-based
base system using docker that contains all required tools:

#+INCLUDE: "./elements/base.bst" example yaml

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
