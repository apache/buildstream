.. _docker:

Using BuildStream inside Docker
===============================
Some of the dependencies needed to use BuildStream are still not available in
some Linux distributions.

It is also possible that the users don't want to install these dependencies in
their systems. For these cases, it's possible to use Docker.

Here in this page we are going to explain how to use Docker for developing and
running BuildStream.


Building a Docker container to use BuildStream
----------------------------------------------
To create a Docker image ready to use with BuildStream you need to run the
following command in the top level directory of BuildStream repository.

::

    docker build -t buildstream .

Options explained:

-  ``-t buildstream``: Tag the created container as ``buildstream``

The container created will have BuildStream installed. If you want to run a
different version, you have to switch to the modified source tree and build the
container image running the same command, or with a different tag.


Running BuildStream tests in Docker
-----------------------------------
To run the tests inside a Docker container, we only need to mount the
repository inside the running container and run the tests. To do this run the
following command:

::

    docker run -it -u $UID:$EUID -v `pwd`:/bst-src:rw --privileged -w /bst-src buildstream python3 setup.py test

Options explained:

-  ``-it``: Interactive shell and TTY support.
-  ``-u $UID:$EUID``: Use $UID as user-id and $EUID as group-id when
   running the container.
-  ``-v $(pwd):/bst-src:rw``: Mount BuildStream source tree in
   ``/bst-src`` with RW permissions.
-  ``--privileged``: To give extra privileges to the container (Needed
   to run some of the sandbox tests).
-  ``-w /bst-src``: Switch to the ``/bst-src`` directory when running the
   container.


Using BuildStream in a Docker container
---------------------------------------
To use BuildStream build tool you will need to mount inside the container your
workspace, and a folder that BuildStream will use for temporary data. This way
we make the temporary data persistent between runs.

Run the following command to run a bash session inside the container:

::

    docker run -it -u $UID:$EUID -v /path/to/buildstream/workspace:/src:rw -v /path/to/buildstream/tmp:/buildstream:rw buildstream bash

Options:

-  ``-it``: Interactive shell and TTY support.
-  ``-u $UID:$EUID``: Use $UID as user-id and $EUID as group-id when
   running the container.
-  ``-v /path/to/buildstream/workspace:/src:rw``: Mount your workspace in
   ``/src`` inside the container.
-  ``-v /path/to/buildstream/tmp:/buildstream:rw``: Mount a temporary folder
   where BuildStream stores artifacts, sources, etc.
