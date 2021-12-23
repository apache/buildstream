

.. _docker:

BuildStream inside Docker
-------------------------
If your system cannot provide the base system requirements for BuildStream, then it is possible to run buildstream within a Docker image.

The BuildStream project provides
`Docker images <https://hub.docker.com/r/buildstream/buildstream>`_
containing BuildStream and its dependencies.
This gives you an easy way to get started using BuildStream on any Unix-like
platform where Docker is available, including Mac OS X.

We recommend using the
`bst-here wrapper script <https://gitlab.com/BuildStream/buildstream/blob/master/contrib/bst-here>`_
which automates the necessary container setup. You can download it and make
it executable like this:

.. code:: bash

  mkdir -p ~/.local/bin
  curl --get https://gitlab.com/BuildStream/buildstream/raw/master/contrib/bst-here > ~/.local/bin/bst-here
  chmod +x ~/.local/bin/bst-here

Check if ``~/.local/bin`` appears in your PATH environment variable -- if it
doesn't, you should
`edit your ~/.profile so that it does <https://stackoverflow.com/questions/14637979/>`_.

Once the script is available in your PATH, you can run ``bst-here`` to open a
shell session inside a new container based off the latest version of the
buildstream Docker image. The current working directory will be mounted
inside the container at ``/src``.

You can also run individual BuildStream commands as ``bst-here COMMAND``. For
example: ``bst-here show systems/my-system.bst``. Note that BuildStream won't
be able to integrate with Bash tab-completion if you invoke it in this way.

Two Docker volumes are set up by the ``bst-here`` script:

 * buildstream-cache -- mounted at ``~/.cache/buildstream``
 * buildstream-config -- mounted at ``~/.config/``

These are necessary so that your BuildStream cache and configuration files
persist between invocations of ``bst-here``.
