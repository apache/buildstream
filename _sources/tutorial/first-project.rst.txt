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



.. _tutorial_first_project:

Your first project
==================
To get a feel for the basics, we'll start with the most basic BuildStream project we
could think of.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/first-project
   <https://github.com/apache/buildstream/tree/master/doc/examples/first-project>`_
   subdirectory.


Creating the project
--------------------
First, lets create the project itself using the convenience :ref:`bst init <invoking_init>`
command to create a little project structure:

.. raw:: html
   :file: ../sessions/first-project-init.html


This will give you a :ref:`project.conf <projectconf>` which will look like this:

``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/first-project/project.conf
   :language: yaml

The :ref:`project.conf <projectconf>` is a central point of configuration
for your BuildStream project.


Add some content
----------------
BuildStream processes directory trees as input and output,
so let's just create a ``hello.world`` file for the project
to have.

.. raw:: html
   :file: ../sessions/first-project-touch.html


Declare the element
-------------------
Here we're going to declare a simple :mod:`import <elements.import>` element
which will import the ``hello.world`` file we've created in the previous step.

Create ``elements/hello.bst`` with the following content:


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/first-project/elements/hello.bst
   :language: yaml


The source
~~~~~~~~~~
The :mod:`local <sources.local>` source used by the ``hello.bst`` element,
can be used to access files or directories which are stored in the same repository
as your BuildStream project. The ``hello.bst`` element uses the :mod:`local <sources.local>`
source to stage our local ``hello.world`` file.


The element
~~~~~~~~~~~
The :mod:`import <elements.import>` element can be used to simply add content
directly to the output artifacts. In this case, it simply takes the ``hello.world`` file
provided by its source and stages it directly to the artifact output root.

.. tip::

   In this example so far we've used two plugins, the :mod:`local <sources.local>`
   source and the :mod:`import <elements.import>` element.

   You can always browse the documentation for all plugins in
   the :ref:`plugins section <plugins>` of the manual.


Build the element
-----------------
In order to carry out the activities of the :mod:`import <elements.import>` element
we've declared, we're going to have to ask BuildStream to *build*.

This process will collect all of the sources required for the specified ``hello.bst``
and get the backing :mod:`import <elements.import>` element to generate an *artifact*
for us.

.. raw:: html
   :file: ../sessions/first-project-build.html

Now the artifact is ready.

Using :ref:`bst show <invoking_show>`, we can observe that the artifact's state, which was reported
as ``buildable`` in the :ref:`bst build <invoking_build>` command above, has now changed to ``cached``:

.. raw:: html
   :file: ../sessions/first-project-show.html


Observe the output
------------------
Now that we've finished building, we can checkout the output of the
artifact we've created using :ref:`bst artifact checkout <invoking_artifact_checkout>`

.. raw:: html
   :file: ../sessions/first-project-checkout.html

And observe that the file we expect is there:

.. raw:: html
   :file: ../sessions/first-project-ls.html


Summary
-------
In this section we've created our first BuildStream project from
scratch, but it doesnt do much.

We've observed the general structure of a BuildStream project,
and we've run our first build.
