Hacking on BuildStream
======================
Some tips and guidelines for developers hacking on BuildStream


Feature Additions
-----------------
Major feature additions should be proposed on the
`mailing list <https://mail.gnome.org/mailman/listinfo/buildstream-list>`_
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


Patch Submissions
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


Commit Messages
~~~~~~~~~~~~~~~
Commit messages must be formatted with a brief summary line, optionally
followed by an empty line and then a free form detailed description of
the change.

The summary line must start with what changed, followed by a colon and
a very brief description of the change.

**Example**::

  element.py: Added the frobnicator so that foos are properly frobbed.

  The new frobnicator frobnicates foos all the way throughout
  the element. Elements that are not properly frobnicated raise
  an error to inform the user of invalid frobnication rules.

  This fixes issue #123


Coding Style
------------
Coding style details for BuildStream


Style Guide
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


Documenting BuildStream
-----------------------
BuildStream starts out as a documented project from day one and uses
sphinx to document itself.

Useful links:

* Sphinx documentation: http://www.sphinx-doc.org/en/1.4.8/contents.html
* rst primer: http://www.sphinx-doc.org/en/stable/rest.html


Building Docs
~~~~~~~~~~~~~
The documentation build is not integrated into the ``setup.py`` and is
difficult (or impossible) to do so, so there is a little bit of setup
you need to take care of first.

Before you can build the BuildStream documentation yourself, you need
to first install ``sphinx`` and ``sphinx-click``, using pip or some
other mechanism::

  pip install --user sphinx
  pip install --user sphinx-click
  pip install --user sphinx_rtd_theme

Furthermore, the documentation build requires that BuildStream itself
be installed.

To build the documentation, just run the following::

  make -C doc

This will give you a ``doc/build/html`` directory with the html docs which
you can view in your browser locally to test.


Man Pages
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


Documenting Conventions
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


Testing BuildStream
-------------------
BuildStream uses pytest for regression tests and testing out
the behavior of newly added components.

The elaborate documentation for pytest can be found here: http://doc.pytest.org/en/latest/contents.html

Don't get lost in the docs if you don't need to, follow existing examples instead.


Running Tests
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


Adding Tests
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


The MANIFEST.in and setup.py
----------------------------
When adding a dependency to BuildStream, it's important to update the setup.py accordingly.

When adding data files which need to be discovered at runtime by BuildStream, update setup.py accordingly.

When adding data files for the purpose of docs or tests, or anything that is not covered by
setup.py, update the MANIFEST.in accordingly.

At any time, running the following command to create a source distribution should result in
creating a tarball which contains everything we want it to include::

  ./setup.py sdist
