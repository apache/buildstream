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



.. _measuring_performance:

Measuring performance
---------------------

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
time was spent in each function. Here is an example of running ``bst --help``
under cProfile:

    python3 -m cProfile -o bst.cprofile -- $(which bst) --help

You can then analyze the results interactively using the 'pstats' module:

    python3 -m pstats ./bst.cprofile

For more detailed documentation of cProfile and 'pstats', see:
https://docs.python.org/3/library/profile.html.

For a richer and interactive visualisation of the `.cprofile` files, you can
try `snakeviz <http://jiffyclub.github.io/snakeviz/#interpreting-results>`_.
You can install it with `pip install snakeviz`. Here is an example invocation:

    snakeviz bst.cprofile

It will then start a webserver and launch a browser to the relevant page.

.. note::

    If you want to also profile cython files, you will need to add
    BST_CYTHON_PROFILE=1 and recompile the cython files.
    ``pip install`` would take care of that.

Profiling specific parts of BuildStream with BST_PROFILE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream can also turn on cProfile for specific parts of execution
using BST_PROFILE.

BST_PROFILE can be set to a section name, or a list of section names separated
by ":". You can also use "all" for getting all profiles at the same time.
There is a list of topics in `src/buildstream/_profile.py`. For example, running::

    BST_PROFILE=load-pipeline bst build bootstrap-system-x86.bst

will produce a profile in the current directory for the time take to
call most of `initialized`, for each element. These profile files
are in the same cProfile format as those mentioned in the previous
section, and can be analysed in the same way.

Fixing performance issues
~~~~~~~~~~~~~~~~~~~~~~~~~

BuildStream uses `Cython <https://cython.org/>`_ in order to speed up specific parts of the
code base.

.. note::

    When optimizing for performance, please ensure that you optimize the algorithms before
    jumping into Cython code. Cython will make the code harder to maintain and less accessible
    to all developers.

When adding a new cython file to the codebase, you will need to register it in ``setup.py``.

For example, for a module ``buildstream._my_module``, to be written in ``src/buildstream/_my_module.pyx``, you would do::

   register_cython_module("buildstream._my_module")

In ``setup.py`` and the build tool will automatically use your module.

.. note::

   Please register cython modules at the same place as the others.

When adding a definition class to share cython symbols between modules, please document the implementation file
and only expose the required definitions.
