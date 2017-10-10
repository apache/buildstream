.. _docker:

BuildStream inside Docker
=========================
The BuildStream project provides
`Docker images <https://hub.docker.com/r/buildstream/buildstream-fedora/>`_
containing BuildStream and its dependencies.
This gives you an easy way to get started using BuildStream on any Unix-like
platform where Docker is available, including Mac OS X.

To use BuildStream you will need to spawn a container from that image
and mount your workspace directory as a volume. You will want a second volume
to store the cache, which we can create from empty like this:

::

    docker volume create buildstream-cache

You can now run the following command to fetch the latest official Docker image
build, and spawn a container running an interactive shell. This assumes that the
path to all the source code you need is available in ``~/src``.

::

    docker run -it \
          --cap-add SYS_ADMIN \
          --device /dev/fuse \
          --security-opt seccomp=unconfined \
          --volume ~/src:/src \
          --volume buildstream-cache:/root/.cache \
          buildstream/buildstream-fedora:latest /bin/bash
