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



.. _handling_files_overlaps:

Overlapping files
=================
In this chapter, we will discuss what happens when files from multiple
element artifacts conflict with eachother, and what strategies we can
use to resolve these situations.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/overlaps
   <https://github.com/apache/buildstream/tree/master/doc/examples/overlaps>`_
   subdirectory.


Overview
--------
This project builds on the previous chapter on :ref:`composition <handling_files_composition>`,
and as such we'll only go over what has changed from there, which is not much.


Project structure
-----------------
In this example we've just extended the ``libhello.bst`` and the ``hello.bst``
elements such that they both install an additional file: ``%{docdir}/hello.txt``.

We've updated the following Makefiles:


files/libhello/Makefile
~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/overlaps/files/libhello/Makefile
   :language: Makefile


files/hello/Makefile
~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/overlaps/files/hello/Makefile
   :language: Makefile


As you can see, this now presents a conflict of sorts, where multiple
elements in the pipeline want to install the *same file*.


Using the project
-----------------
In this chapter, we're only going to present the warning and then
discuss how to mitigate this situation.

See what happens when we try to build the ``runtime-only.bst``
:mod:`compose <elements.compose>` element:

.. raw:: html
   :file: ../sessions/overlaps-build.html

Notice the warning message about the conflicting file, it is there to
inform the user about which files are *overlapping*, and also which
elements are being staged in which order.

Note also that BuildStream does not discover the overlap until the
moment that you build a reverse dependency which will require staging
of both artifacts.

.. tip::

   The ``overlaps`` warning discussed here can be configured to be
   a :ref:`fatal warning <configurable_warnings>`. This is useful
   in the case that you want to be strict about avoiding overlapping
   files in your project.


Mitigating overlapping files
----------------------------
Since we recently discussed :ref:`filtering of artifacts <handling_files_filtering>`,
we should note that it is of course possible to handle this case by
having ``hello.bst`` depend on a *filtered* version of ``libhello.bst`` with the
offending file excluded.

However, working with :mod:`filter <elements.filter>` elements just for the
sake of handling a conflicting artifact would be quite inconvenient, so we
have other means.


Whitelisting overlapping files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream allows explicitly ignoring such errors by adding the files
to an :ref:`overlap whitelist <public_overlap_whitelist>`, you could achieve
this in the given example by adding the following to the ``hello.bst`` element:

.. code:: yaml

  public:
    bst:
      overlap-whitelist:
      - |
        %{docdir}/hello.txt

.. note::

   Note that :func:`glob patterns <buildstream.utils.glob>` are also
   supported in the whitelist.


Artifact munging
~~~~~~~~~~~~~~~~
Another way around this situation is the *munge* the artifacts at install
time such that there is no conflict.

This is the easiest approach in the case that you might want to keep the
underlying ``%{docdir}/hello.txt`` from ``libhello.bst`` and discard the
same file from ``hello.bst``.

In this case, we might modify the ``hello.bst`` file so that it's install
command contain an ``rm`` statement, as such:

.. code:: yaml

  install-commands:
  - make -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install

  - |
    # Rid ourselves of the unwanted file at install time
    rm -f %{install-root}%{docdir}/hello.txt

This would cause later builds of ``runtime-only.bst`` to no longer
conflict on the given file.


Summary
-------
In this chapter we've presented a situation where an artifact
can *conflict* with another artifact by way of providing the
same files.

We've presented the :ref:`overlap whitelist <public_overlap_whitelist>`
public data which is the typical solution for silencing the
error when the outcome is desired, and also presented a strategy
to deal with cases where you want to keep files from the
*overlapped* artifact instead.
