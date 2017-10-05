.. _docker:

BuildStream inside Docker
=========================
The BuildStream project provides
`Docker images <https://hub.docker.com/r/buildstream/buildstream-fedora>`_
containing BuildStream and its dependencies.
This gives you an easy way to get started using BuildStream on any Unix-like
platform where Docker is available, including Mac OS X.

We recommend using the
`bst-here wrapper script <https://gitlab.com/BuildStream/buildstream/blob/master/contrib/bst-here>`_
which automates the necessary container setup. You can download it and make
it executable like this:

    mkdir -p ~/.local/bin
    curl --get https://gitlab.com/BuildStream/buildstream/raw/master/contrib/bst-here > ~/.local/bin/bst-here
    chmod +x ~/.local/bin/bst-here

Check if ``~/.local/bin`` appears in your PATH environment variable -- if it
doesn't, you should
`edit your ~/.profile so that it does <https://stackoverflow.com/questions/14637979/>`_.

Once ``bst-here`` is available in your PATH, you just prefix every BuildStream
command you need to run with ``bst-here`` so that it executes through the
wrapper. The latest version of the buildstream-fedora Docker image is
automatically pulled if needed. The contents of your working directory will be
made available at ``/src`` inside the container.

Two other volumes are set up by the ``bst-here`` script:

 * buildstream-cache -- mounted at ``~/.cache/buildstream``
 * buildstream-config -- mounted at ``~/.config/``

These are necessary so that your BuildStream cache and configuration files
persist between invocations of ``bst-here``. You can open a shell inside the
container by running ``bst-here -t /bin/bash``, which is useful if for example
you need to add something custom to ``~/.config/buildstream.conf``.
