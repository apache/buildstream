Contributing
============
Some tips and guidelines for developers hacking on BuildStream


Feature additions
-----------------
Major feature additions should be proposed on the
`mailing list <https://lists.apache.org/list.html?dev@buildstream.apache.org>`_
before being considered for inclusion, we strongly recommend proposing
in advance of commencing work.

New features must be well documented and tested either in our main
test suite if possible, or otherwise in the integration tests.

It is expected that the individual submitting the work take ownership
of their feature within BuildStream for a reasonable timeframe of at least
one release cycle after their work has landed on the master branch. This is
to say that the submitter is expected to address and fix any side effects and
bugs which may have fell through the cracks in the review process, giving us
a reasonable timeframe for identifying these.


Patch submissions
-----------------
Branches must be submitted as merge requests in gitlab and should usually
be associated to an issue report on gitlab.

Commits in the branch which address specific issues must specify the
issue number in the commit message.

Merge requests that are not yet ready for review must be prefixed with the
``WIP:`` identifier. A merge request is not ready for review until the
submitter expects that the patch is ready to actually land.

Submitted branches must not contain a history of the work done in the
feature branch. Please use git's interactive rebase feature in order to
compose a clean patch series suitable for submission.

We prefer that test case and documentation changes be submitted
in separate commits from the code changes which they test.

Ideally every commit in the history of master passes its test cases. This
makes bisections more easy to perform, but is not always practical with
more complex branches.


Commit messages
~~~~~~~~~~~~~~~
Commit messages must be formatted with a brief summary line, optionally
followed by an empty line and then a free form detailed description of
the change.

The summary line must start with what changed, followed by a colon and
a very brief description of the change.

If there is an associated issue, it **must** be mentioned somewhere
in the commit message.

**Example**::

  element.py: Added the frobnicator so that foos are properly frobbed.

  The new frobnicator frobnicates foos all the way throughout
  the element. Elements that are not properly frobnicated raise
  an error to inform the user of invalid frobnication rules.

  This fixes issue #123


Coding style
------------
Coding style details for BuildStream


Style guide
~~~~~~~~~~~
Python coding style for BuildStream is pep8, which is documented here: https://www.python.org/dev/peps/pep-0008/

We have a couple of minor exceptions to this standard, we dont want to compromise
code readability by being overly restrictive on line length for instance.

The pep8 linter will run automatically when running the test suite.


Imports
~~~~~~~
Module imports inside BuildStream are done with relative ``.`` notation

Good::

  from .context import Context

Bad::

  from buildstream.context import Context

The exception to the above rule is when authoring plugins,
plugins do not reside in the same namespace so they must
address buildstream in the imports.

An element plugin will derive from Element by importing::

  from buildstream import Element

When importing utilities specifically, dont import function names
from there, instead import the module itself::

  from . import utils

This makes things clear when reading code that said functions
are not defined in the same file but come from utils.py for example.


Policy for private symbols
~~~~~~~~~~~~~~~~~~~~~~~~~~
Private symbols are expressed via a leading ``_`` single underscore, or
in some special circumstances with a leading ``__`` double underscore.

Before understanding the naming policy, it is first important to understand
that in BuildStream, there are two levels of privateness which need to be
considered.

These are treated subtly differently and thus need to be understood:

* API Private

  A symbol is considered to be *API private* if it is not exposed in the *public API*.

  Even if a symbol does not have any leading underscore, it may still be *API private*
  if the containing *class* or *module* is named with a leading underscore.

* Local private

  A symbol is considered to be *local private* if it is not intended for access
  outside of the defining *scope*.

  If a symbol has a leading underscore, it might not be *local private* if it is
  declared on a publicly visible class, but needs to be accessed internally by
  other modules in the BuildStream core.


Ordering
''''''''
For better readability and consistency, we try to keep private symbols below
public symbols. In the case of public modules where we may have a mix of
*API private* and *local private* symbols, *API private* symbols should come
before *local private* symbols.


Symbol naming
'''''''''''''
Any private symbol must start with a single leading underscore for two reasons:

* So that it does not bleed into documentation and *public API*.

* So that it is clear to developers which symbols are not used outside of the declaring *scope*

Remember that with python, the modules (python files) are also symbols
within their containing *package*, as such; modules which are entirely
private to BuildStream are named as such, e.g. ``_thismodule.py``.


Cases for double underscores
''''''''''''''''''''''''''''
The double underscore in python has a special function. When declaring
a symbol in class scope which has a leading underscore, it can only be
accessed within the class scope using the same name. Outside of class
scope, it can only be accessed with a *cheat*.

We use the double underscore in cases where the type of privateness can be
ambiguous.

* For private modules and classes

  We never need to disambiguate with a double underscore

* For private symbols declared in a public *scope*

  In the case that we declare a private method on a public object, it
  becomes ambiguous whether:

  * The symbol is *local private*, and only used within the given scope

  * The symbol is *API private*, and will be used internally by BuildStream
    from other parts of the codebase.

  In this case, we use a single underscore for *API private* methods which
  are not *local private*, and we use a double underscore for *local private*
  methods declared in public scope.


Documenting private symbols
'''''''''''''''''''''''''''
Any symbol which is *API Private* (regardless of whether it is also
*local private*), should have some documentation for developers to
better understand the codebase.

Contrary to many other python projects, we do not use docstrings to
document private symbols, but prefer to keep *API Private* symbols
documented in code comments placed *above* the symbol (or *beside* the
symbol in some cases, such as variable declarations in a class where
a shorter comment is more desirable), rather than docstrings placed *below*
the symbols being documented.

Other than this detail, follow the same guidelines for documenting
symbols as described below.


Documenting BuildStream
-----------------------
BuildStream starts out as a documented project from day one and uses
sphinx to document itself.


Documentation formatting policy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The BuildStream documentation style is as follows:

* Titles and headings require two leading empty lines above them. Only the first word should be capitalized.

  * If there is an ``.. _internal_link`` anchor, there should be two empty lines above the anchor, followed by one leading empty line.

* Within a section, paragraphs should be separated by one empty line.

* Notes are defined using: ``.. note::`` blocks, followed by an empty line and then indented (3 spaces) text.

* Code blocks are defined using: ``.. code:: LANGUAGE`` blocks, followed by an empty line and then indented (3 spaces) text. Note that the default language is `python`.

* Cross references should be of the form ``:role:`target```.

  * To cross reference arbitrary locations with, for example, the anchor ``_anchor_name``, you must give the link an explicit title: ``:ref:`Link text <anchor_name>```. Note that the "_" prefix is not required.

Useful links:

For further information, please see the `Sphinx Documentation <http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_.


Building Docs
~~~~~~~~~~~~~
The documentation build is not integrated into the ``setup.py`` and is
difficult (or impossible) to do so, so there is a little bit of setup
you need to take care of first.

Before you can build the BuildStream documentation yourself, you need
to first install ``sphinx`` along with some additional plugins and dependencies,
using pip or some other mechanism::

  # Install sphinx
  pip3 install --user sphinx

  # Install some sphinx extensions
  pip3 install --user sphinx-click
  pip3 install --user sphinx_rtd_theme

  # Additional optional dependencies required
  pip3 install --user arpy

To build the documentation, just run the following::

  make -C doc

This will give you a ``doc/build/html`` directory with the html docs which
you can view in your browser locally to test.


Regenerating session html
'''''''''''''''''''''''''
The documentation build will build the session files if they are missing,
or if explicitly asked to rebuild. We revision the generated session html files
in order to reduce the burden on documentation contributors.

To explicitly rebuild the session snapshot html files, it is recommended that you
first set the ``BST_SOURCE_CACHE`` environment variable to your source cache, this
will make the docs build reuse already downloaded sources::

  export BST_SOURCE_CACHE=~/.cache/buildstream/sources

To force rebuild session html while building the doc, simply build the docs like this::

  make BST_FORCE_SESSION_REBUILD=1 -C doc


Man pages
~~~~~~~~~
Unfortunately it is quite difficult to integrate the man pages build
into the ``setup.py``, as such, whenever the frontend command line
interface changes, the static man pages should be regenerated and
committed with that.

To do this, first ensure you have ``click_man`` installed, possibly
with::

  pip install --user click_man

Then, in the toplevel directory of buildstream, run the following::

  python3 setup.py --command-packages=click_man.commands man_pages

And commit the result, ensuring that you have added anything in
the ``man/`` subdirectory, which will be automatically included
in the buildstream distribution.


Documenting conventions
~~~~~~~~~~~~~~~~~~~~~~~
We use the sphinx.ext.napoleon extension for the purpose of having
a bit nicer docstrings than the default sphinx docstrings.

A docstring for a method, class or function should have the following
format::

  """Brief description of entity

  Args:
     argument1 (type): Description of arg
     argument2 (type): Description of arg

  Returns:
     (type): Description of returned thing of the specified type

  Raises:
     (SomeError): When some error occurs
     (SomeOtherError): When some other error occurs

  A detailed description can go here if one is needed, only
  after the above part documents the calling conventions.
  """


Documentation Examples
~~~~~~~~~~~~~~~~~~~~~~
The examples section of the documentation contains a series of standalone
examples, here are the criteria for an example addition.

* The example has a ``${name}``

* The example has a project users can copy and use

  * This project is added in the directory ``doc/examples/${name}``

* The example has a documentation component

  * This is added at ``doc/source/examples/${name}.rst``
  * A reference to ``examples/${name}`` is added to the toctree in ``doc/source/examples.rst``
  * This documentation discusses the project elements declared in the project and may
    provide some BuildStream command examples
  * This documentation links out to the reference manual at every opportunity

* The example has a CI test component

  * This is an integration test added at ``tests/examples/${name}``
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

* ``directory``: The input file relative project directory

* ``output``: The input file relative output html file to generate (optional)

* ``fake-output``: Don't really run the command, just pretend to and pretend
  this was the output, an empty string will enable this too.

* ``command``: The command to run, without the leading ``bst``

When adding a new ``.run`` file, one should normally also commit the new
resulting generated ``.html`` file(s) into the ``doc/source/sessions-stored/``
directory at the same time, this ensures that other developers do not need to
regenerate them locally in order to build the docs.

**Example**:

.. code:: yaml

   commands:

   # Make it fetch first
   - directory: ../examples/foo
     command: fetch hello.bst

   # Capture a build output
   - directory: ../examples/foo
     output: ../source/sessions/foo-build.html
     command: build hello.bst


Protocol Buffers
----------------
BuildStream uses protobuf and gRPC for serialization and communication with
artifact cache servers.  This requires ``.proto`` files and Python code
generated from the ``.proto`` files using protoc.  All these files live in the
``buildstream/_protos`` directory.  The generated files are included in the
git repository to avoid depending on grpcio-tools for user installations.


Regenerating code
~~~~~~~~~~~~~~~~~
When ``.proto`` files are modified, the corresponding Python code needs to
be regenerated.  As a prerequisite for code generation you need to install
``grpcio-tools`` using pip or some other mechanism::

  pip3 install --user grpcio-tools

To actually regenerate the code::

  ./setup.py build_grpc


Testing BuildStream
-------------------
BuildStream uses pytest for regression tests and testing out
the behavior of newly added components.

The elaborate documentation for pytest can be found here: http://doc.pytest.org/en/latest/contents.html

Don't get lost in the docs if you don't need to, follow existing examples instead.


Running tests
~~~~~~~~~~~~~
To run the tests, just type::

  ./setup.py test

At the toplevel.

When debugging a test, it can be desirable to see the stdout
and stderr generated by a test, to do this use the --addopts
function to feed arguments to pytest as such::

  ./setup.py test --addopts -s

You can always abort on the first failure by running::

  ./setup.py test --addopts -x

If you want to run a specific test or a group of tests, you
can specify a prefix to match. E.g. if you want to run all of
the frontend tests you can do::

  ./setup.py test --addopts '-k tests/frontend/'

We also have a set of slow integration tests that are disabled by
default - you will notice most of them marked with SKIP in the pytest
output. To run them, you can use::

  ./setup.py test --addopts '--integration'

By default, buildstream also runs pylint on all files. Should you want
to run just pylint (these checks are a lot faster), you can do so
with::

  ./setup.py test --addopts '-m pylint'

Alternatively, any IDE plugin that uses pytest should automatically
detect the ``.pylintrc`` in the project's root directory.

Adding tests
~~~~~~~~~~~~
Tests are found in the tests subdirectory, inside of which
there is a separarate directory for each *domain* of tests.
All tests are collected as::

  tests/*/*.py

If the new test is not appropriate for the existing test domains,
then simply create a new directory for it under the tests subdirectory.

Various tests may include data files to test on, there are examples
of this in the existing tests. When adding data for a test, create
a subdirectory beside your test in which to store data.

When creating a test that needs data, use the datafiles extension
to decorate your test case (again, examples exist in the existing
tests for this), documentation on the datafiles extension can
be found here: https://pypi.python.org/pypi/pytest-datafiles

Tests that run a sandbox should be decorated with::

  @pytest.mark.integration

and use the integration cli helper.

Measuring BuildStream performance
---------------------------------


Benchmarking framework
~~~~~~~~~~~~~~~~~~~~~~~
BuildStream has a utility to measure performance which is available from a
separate repository at https://gitlab.com/BuildStream/benchmarks. This tool
allows you to run a fixed set of workloads with multiple versions of
BuildStream. From this you can see whether one version performs better or
worse than another which is useful when looking for regressions and when
testing potential optimizations.

For full documentation on how to use the benchmarking tool see the README in
the 'benchmarks' repository.


Profiling tools
~~~~~~~~~~~~~~~
When looking for ways to speed up the code you should make use of a profiling
tool.

Python provides `cProfile <https://docs.python.org/3/library/profile.html>`_
which gives you a list of all functions called during execution and how much
time was spent in each function. Here is an example of running `bst --help`
under cProfile:

    python3 -m cProfile -o bst.cprofile -- $(which bst) --help

You can then analyze the results interactively using the 'pstats' module:

    python3 -m pstats ./bst.cprofile

For more detailed documentation of cProfile and 'pstats', see:
https://docs.python.org/3/library/profile.html.

For a richer visualisation of the callstack you can try `Pyflame
<https://github.com/uber/pyflame>`_. Once you have followed the instructions in
Pyflame's README to install the tool, you can profile `bst` commands as in the
following example:

    pyflame --output bst.flame --trace bst --help

You may see an `Unexpected ptrace(2) exception:` error. Note that the `bst`
operation will continue running in the background in this case, you will need
to wait for it to complete or kill it. Once this is done, rerun the above
command which appears to fix the issue.

Once you have output from pyflame, you can use the ``flamegraph.pl`` script
from the `Flamegraph project <https://github.com/brendangregg/FlameGraph>`_
to generate an .svg image:

    ./flamegraph.pl bst.flame > bst-flamegraph.svg

The generated SVG file can then be viewed in your preferred web browser.


Profiling specific parts of BuildStream with BST_PROFILE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream can also turn on cProfile for specific parts of execution
using BST_PROFILE.

BST_PROFILE can be set to a section name, or 'all' for all
sections. There is a list of topics in `buildstream/_profile.py`. For
example, running::

    BST_PROFILE=load-pipeline bst build bootstrap-system-x86.bst

will produce a profile in the current directory for the time take to
call most of `initialized`, for each element. These profile files
are in the same cProfile format as those mentioned in the previous
section, and can be analysed with `pstats` or `pyflame`.


Profiling the artifact cache receiver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Since the artifact cache receiver is not normally run directly, it's
necessary to alter the ForceCommand part of sshd_config to enable
profiling. See the main documentation in `doc/source/artifacts.rst`
for general information on setting up the artifact cache. It's also
useful to change directory to a logging directory before starting
`bst-artifact-receive` with profiling on.

This is an example of a ForceCommand section of sshd_config used to
obtain profiles::

    Match user artifacts
      ForceCommand BST_PROFILE=artifact-receive cd /tmp && bst-artifact-receive --pull-url https://example.com/ /home/artifacts/artifacts


The MANIFEST.in and setup.py
----------------------------
When adding a dependency to BuildStream, it's important to update the setup.py accordingly.

When adding data files which need to be discovered at runtime by BuildStream, update setup.py accordingly.

When adding data files for the purpose of docs or tests, or anything that is not covered by
setup.py, update the MANIFEST.in accordingly.

At any time, running the following command to create a source distribution should result in
creating a tarball which contains everything we want it to include::

  ./setup.py sdist
