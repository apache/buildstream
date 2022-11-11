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



.. _writing_documentation:

Writing documentation
---------------------
BuildStream starts out as a documented project from day one and uses
`sphinx <www.sphinx-doc.org>`_ to document itself.

This section discusses formatting policies for editing files in the
``doc/source`` directory, and describes the details of how the docs are
generated so that you can easily generate and view the docs yourself before
submitting patches to the documentation.

For details on how API documenting comments and docstrings are formatted,
refer to the :ref:`documenting section of the coding guidelines
<contributing_documenting_symbols>`.


Documentation formatting policy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The BuildStream documentation style is as follows:

* Titles and headings require two leading empty lines above them.
  Only the first word in a title should be capitalized.

  * If there is an ``.. _internal_link:`` anchor, there should be two empty lines
    above the anchor, followed by one leading empty line.

* Within a section, paragraphs should be separated by one empty line.

* Notes are defined using: ``.. note::`` blocks, followed by an empty line
  and then indented (3 spaces) text.

  * Other kinds of notes can be used throughout the documentation and will
    be decorated in different ways, these work in the same way as ``.. note::`` does.

    Feel free to also use ``.. attention::`` or ``.. important::`` to call special
    attention to a paragraph, ``.. tip::`` to give the reader a special tip on how
    to use an advanced feature or ``.. warning::`` to warn the user about a potential
    misuse of the API and explain its consequences.

* Code blocks are defined using: ``.. code:: LANGUAGE`` blocks, followed by an empty
  line and then indented (3 spaces) text. Note that the default language is ``python``.

* Cross references should be of the form ``:role:`target```.

  * Explicit anchors can be declared as ``.. _anchor_name:`` on a line by itself.

  * To cross reference arbitrary locations with, for example, the anchor ``anchor_name``,
    always provide some explicit text in the link instead of deriving the text from
    the target, e.g.: ``:ref:`Link text <anchor_name>```.
    Note that the "_" prefix is not used when referring to the target.

For further information about using the reStructuredText with sphinx, please see the
`Sphinx Documentation <http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_.


Building Docs
~~~~~~~~~~~~~
Before you can build the docs, you will end to ensure that you have installed
the required :ref:`build dependencies <contributing_build_deps>` as mentioned
in the testing section above.

To build the documentation, just run the following::

  tox -e docs

This will give you a ``doc/build/html`` directory with the html docs which
you can view in your browser locally to test.


.. _contributing_session_html:

Regenerating session html
'''''''''''''''''''''''''
The documentation build will build the session files if they are missing,
or if explicitly asked to rebuild. We revision the generated session html files
in order to reduce the burden on documentation contributors.

To explicitly rebuild the session snapshot html files, it is recommended that you
first set the ``BST_SOURCE_CACHE`` environment variable to your source cache, this
will make the docs build reuse already downloaded sources::

  export BST_SOURCE_CACHE=~/.cache/buildstream/sources

To force rebuild session html while building the doc, simply run `tox` with the
``BST_FORCE_SESSION_REBUILD`` environment variable set, like so::

  env BST_FORCE_SESSION_REBUILD=1 tox -e docs


.. _contributing_man_pages:

Man pages
~~~~~~~~~
Unfortunately it is quite difficult to integrate the man pages build
into the ``setup.py``, as such, whenever the frontend command line
interface changes, the static man pages should be regenerated and
committed with that.

To do this, run the following from the the toplevel directory of BuildStream::

  tox -e man

And commit the result, ensuring that you have added anything in
the ``man/`` subdirectory, which will be automatically included
in the buildstream distribution.


User guide
~~~~~~~~~~
The :ref:`user guide <using>` is comprised of free form documentation
in manually written ``.rst`` files and is split up into a few sections,
of main interest are the :ref:`tutorial <tutorial>` and the
:ref:`examples <examples>`.

The distinction of the two categories of user guides is important to
understand too.

* **Tutorial**

  The tutorial is structured as a series of exercises which start with
  the most basic concepts and build upon the previous chapters in order
  to arrive at a basic understanding of how to create BuildStream projects.

  This series of examples should be easy enough to complete in a matter
  of a few hours for a new user, and should provide just enough insight to
  get the user started in creating their own projects.

  Going through the tutorial step by step should also result in the user
  becoming proficient enough with the reference manual to get by on their own.

* **Examples**

  These exist to demonstrate how to accomplish more advanced tasks which
  are not always obvious and discoverable.

  Alternatively, these also demonstrate elegant and recommended ways of
  accomplishing some tasks which could be done in various ways.


Guidelines
''''''''''
Here are some general guidelines for adding new free form documentation
to the user guide.

* **Focus on a single subject**

  It is important to stay focused on a single subject and avoid getting
  into tangential material when creating a new entry, so that the articles
  remain concise and the user is not distracted by unrelated subject material.

  A single tutorial chapter or example should not introduce any additional
  subject material than the material being added for the given example.

* **Reuse existing sample project elements**

  To help avoid distracting from the topic at hand, it is always preferable to
  reuse the same project sample material from other examples and only deviate
  slightly to demonstrate the new material, than to create completely new projects.

  This helps us remain focused on a single topic at a time, and reduces the amount
  of unrelated material the reader needs to learn in order to digest the new
  example.

* **Don't be redundant**

  When something has already been explained in the tutorial or in another example,
  it is best to simply refer to the other user guide entry in a new example.

  Always prefer to link to the tutorial if an explanation exists in the tutorial,
  rather than linking to another example, where possible.

* **Link into the reference manual at every opportunity**

  The format and plugin API is 100% documented at all times. Whenever discussing
  anything about the format or plugin API, always do so while providing a link
  into the more terse reference material.

  We don't want users to have to search for the material themselves, and we also
  want the user to become proficient at navigating the reference material over
  time.

* **Use concise terminology**

  As developers, we tend to come up with code names for features we develop, and
  then end up documenting a new feature in an example.

  Never use a code name or shorthand to refer to a feature in the user guide, instead
  always use fully qualified sentences outlining very explicitly what we are doing
  in the example, or what the example is for in the case of a title.

  We need to be considerate that the audience of our user guide is probably a
  proficient developer or integrator, but has no idea what we might have decided
  to name a given activity.


Structure of an example
'''''''''''''''''''''''
The :ref:`tutorial <tutorial>` and the :ref:`examples <examples>` sections
of the documentation contain a series of sample projects, each chapter in
the tutorial, or standalone example uses a sample project.

Here is the the structure for adding new examples and tutorial chapters.

* The example has a ``${name}``.

* The example has a project users can copy and use.

  * This project is added in the directory ``doc/examples/${name}``.

* The example has a documentation component.

  * This is added at ``doc/source/examples/${name}.rst``
  * An entry for ``examples/${name}`` is added to the toctree in ``doc/source/using_examples.rst``
  * This documentation discusses the project elements declared in the project and may
    provide some BuildStream command examples.
  * This documentation links out to the reference manual at every opportunity.

  .. note::

     In the case of a tutorial chapter, the ``.rst`` file is added in at
     ``doc/source/tutorial/${name}.rst`` and an entry for ``tutorial/${name}``
     is added to ``doc/source/using_tutorial.rst``.

* The example has a CI test component.

  * This is an integration test added at ``tests/examples/${name}``.
  * This test runs BuildStream in the ways described in the example
    and assert that we get the results which we advertize to users in
    the said examples.


Adding BuildStream command output
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
As a part of building the docs, BuildStream will run itself and extract
some html for the colorized output which is produced.

If you want to run BuildStream to produce some nice html for your
documentation, then you can do so by adding new ``.run`` files to the
``doc/sessions/`` directory.

Any files added as ``doc/sessions/${example}.run`` will result in generated
file at ``doc/source/sessions/${example}.html``, and these files can be
included in the reStructuredText documentation at any time with::

  .. raw:: html
     :file: sessions/${example}.html

The ``.run`` file format is just another YAML dictionary which consists of a
``commands`` list, instructing the program what to do command by command.

Each *command* is a dictionary, the members of which are listed here:

* ``directory``: The input file relative project directory.

* ``output``: The input file relative output html file to generate (optional).

* ``fake-output``: Don't really run the command, just pretend to and pretend
  this was the output, an empty string will enable this too.

* ``command``: The command to run, without the leading ``bst``.

* ``shell``: Specifying ``True`` indicates that ``command`` should be run as
  a shell command from the project directory, instead of a bst command (optional).

When adding a new ``.run`` file, one should normally also commit the new
resulting generated ``.html`` file(s) into the ``doc/source/sessions-stored/``
directory at the same time, this ensures that other developers do not need to
regenerate them locally in order to build the docs.

**Example**:

.. code:: yaml

   commands:

   # Make it fetch first
   - directory: ../examples/foo
     command: source fetch hello.bst

   # Capture a build output
   - directory: ../examples/foo
     output: ../source/sessions/foo-build.html
     command: build hello.bst
