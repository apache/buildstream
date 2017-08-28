.. _completion:

Bash Completions
================

Bash completions are supported by sourcing the ``buildstream/data/bst``
script found in the BuildStream repository. On many systems this script
can be installed into a completions directory but when installing BuildStream
without a package manager this is not an option.

To enable completions for an installation of BuildStream you
installed yourself from git, just append the script verbatim
to your ``~/.bash_completion``:

.. literalinclude:: ../../buildstream/data/bst
   :language: yaml
