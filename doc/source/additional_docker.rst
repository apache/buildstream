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


.. _bst_and_docker:


BuildStream and Docker
======================
BuildStream integrates with Docker in multiple ways. Here are some ways in
which these integrations work.


Run BuildStream inside Docker
-----------------------------
Refer to the `BuildStream inside Docker <https://buildstream.build/install.html#container-images>`_
documentation for instructions on how to run BuildStream as a Docker container.


Generate Docker images
----------------------
The `bst-docker-import script <https://github.com/apache/buildstream/blob/master/contrib/bst-docker-import>`_
can be used to generate a Docker image from built artifacts.

You can download it and make it executable like this:

.. code:: bash

  mkdir -p ~/.local/bin
  curl --get https://raw.githubusercontent.com/apache/buildstream/master/contrib/bst-docker-import > ~/.local/bin/bst-docker-import
  chmod +x ~/.local/bin/bst-docker-import

Check if ``~/.local/bin`` appears in your PATH environment variable -- if it
doesn't, you should
`edit your ~/.profile so that it does <https://stackoverflow.com/questions/14637979/>`_.

Once the script is available in your PATH and assuming you have Docker
installed, you can start using the ``bst-docker-import`` script. Here is a
minimal example to generate an image called ``bst-hello`` from an element
called ``hello.bst`` assuming it is already built:

.. code:: bash

  bst-docker-import -t bst-hello hello.bst

This script can also be used if you are running BuildStream inside Docker. In
this case, you will need to supply the command that you are using to run
BuildStream using the ``-c`` option.  If you are using the
`bst-here wrapper script <https://github.com/apache/buildstream/blob/master/contrib//bst-here>`_,
you can achieve the same results as the above example like this:

.. code:: bash

  bst-docker-import -c bst-here -t bst-hello hello.bst
