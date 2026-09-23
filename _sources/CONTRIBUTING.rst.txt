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

Contributing
============
Some tips and guidelines for developers hacking on BuildStream


.. _contributing_filing_issues:

Filing issues
-------------
If you are experiencing an issue with BuildStream, or would like to submit a patch
to fix an issue, then you should first search the list of `open issues <https://github.com/apache/buildstream/issues>`_
to see if the issue is already filed, and `open an issue <https://github.com/apache/buildstream/issues/new>`_
if no issue already exists.


.. _contributing_fixing_bugs:

Fixing bugs
-----------
Before fixing a bug, it is preferred that an :ref:`issue be filed <contributing_filing_issues>`
first in order to better document the defect, however this need not be followed to the
letter for minor fixes.

Patches which fix bugs should always come with a regression test.


.. _contributing_adding_features:

Adding new features
-------------------
Feature additions should be proposed on the `mailing list
<https://lists.apache.org/list.html?dev@buildstream.apache.org>`_
before being considered for inclusion. To save time and avoid any frustration,
we strongly recommend proposing your new feature in advance of commencing work.

Once consensus has been reached on the mailing list, then the proposing
party should :ref:`file an issue <contributing_filing_issues>` to track the
work.

New features must be well documented and tested in our test suite.

It is expected that the individual submitting the work take ownership
of their feature within BuildStream for a reasonable timeframe of at least
one release cycle after their work has landed on the master branch. This is
to say that the submitter is expected to address and fix any side effects,
bugs or regressions which may have fell through the cracks in the review
process, giving us a reasonable timeframe for identifying these.


.. _contributing_submitting_patches:

Submitting patches
------------------
Submitting patches works in the regular GitHub workflow of submitting
pull requests.


Branch names
~~~~~~~~~~~~
If you are an apache member with access to the main repository, and are
submitting a pull request for a branch within the main repository, then
please be careful to use an identifiable branch name.

Branch names for pull requests should be prefixed with the submitter's
name or nickname, followed by a forward slash, and then a descriptive
name. e.g.::

  username/fix-that-bug

This allows us to more easily identify which branch does what and
belongs to whom, especially so that we can effectively cleanup stale
branches in the upstream repository over time.


Pull requests
~~~~~~~~~~~~~
Once you have created a local branch, you can push it to the upstream
BuildStream repository using the command line::

  git push origin username/fix-that-bug

GitHub will respond to this with a message and a link to allow you to create
a new merge request. You can also `create a pull request using the GitHub UI
<https://github.com/apache/buildstream/compare>`_.

You may open pull requests for the branches you create before you are ready
to have them reviewed and considered for inclusion if you like. Until your merge
request is ready for review, the pull request title must be prefixed with the
``WIP:`` identifier.

Consider marking a pull request as WIP again if you are taking a while to
address a review point. This signals that the next action is on you, and it
won't appear in a reviewer's search for non-WIP merge requests to review.



Organized commits
~~~~~~~~~~~~~~~~~
Submitted branches must not contain a history of the work done in the
feature branch. For example, if you had to change your approach, or
have a later commit which fixes something in a previous commit on your
branch, we do not want to include the history of how you came up with
your patch in the upstream master branch.

Please use git's interactive rebase feature in order to compose a clean
patch series suitable for submission upstream.

Every commit in series should pass the test suite, this is very important
for tracking down regressions and performing git bisections in the future.

We prefer that documentation changes be submitted in separate commits from
the code changes which they document, and newly added test cases are also
preferred in separate commits.

If a commit in your branch modifies behavior such that a test must also
be changed to match the new behavior, then the tests should be updated
with the same commit, so that every commit passes its own tests.

These principles apply whenever a branch is non-WIP. So for example, don't push
'fixup!' commits when addressing review comments, instead amend the commits
directly before pushing.


Commit messages
~~~~~~~~~~~~~~~
Commit messages must be formatted with a brief summary line, followed by
an empty line and then a free form detailed description of the change.

The summary line must start with what changed, followed by a colon and
a very brief description of the change.

If the commit fixes an issue, or is related to an issue; then the issue
number must be referenced in the commit message.

**Example**::

  element.py: Added the frobnicator so that foos are properly frobbed.

  The new frobnicator frobnicates foos all the way throughout
  the element. Elements that are not properly frobnicated raise
  an error to inform the user of invalid frobnication rules.

  Fixes #123

Note that the 'why' of a change is as important as the 'what'.

When reviewing this, folks can suggest better alternatives when they know the
'why'. Perhaps there are other ways to avoid an error when things are not
frobnicated.

When folks modify this code, there may be uncertainty around whether the foos
should always be frobnicated. The comments, the commit message, and issue #123
should shed some light on that.

In the case that you have a commit which necessarily modifies multiple
components, then the summary line should still mention generally what
changed (if possible), followed by a colon and a brief summary.

In this case the free form detailed description of the change should
contain a bullet list describing what was changed in each component
separately.

**Example**::

  artifact cache: Fixed automatic expiry in the local cache

    o _artifactcache/artifactcache.py: Updated the API contract
      of ArtifactCache.remove() so that something detailed is
      explained here.

    o _artifactcache/cascache.py: Adhere to the new API contract
      dictated by the abstract ArtifactCache class.

    o tests/artifactcache/expiry.py: Modified test expectations to
      match the new behavior.

  This is a part of #123


Committer access
----------------
Committers in the BuildStream project are those folks to whom the right to
directly commit changes to our version controlled resources has been granted.

While every contribution is valued regardless of its source, not every person
who contributes code to the project will earn commit access.
The `COMMITTERS`_ file lists all committers.

.. _COMMITTERS: https://github.com/apache/buildstream/blob/master/COMMITTERS.rst


How commit access is granted
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
After someone has successfully contributed a few non-trivial patches, some full
committer, usually whoever has reviewed and applied the most patches from that
contributor, proposes them for commit access. This proposal is sent only to the
other full committers - the ensuing discussion is private, so that everyone can
feel comfortable speaking their minds. Assuming there are no objections, the
contributor is granted commit access. The decision is made by consensus; there
are no formal rules governing the procedure, though generally if someone strongly
objects the access is not offered, or is offered on a provisional basis.

This of course relies on contributors being responsive and showing willingness
to address any problems that may arise after landing patches. However, the primary
criterion for commit access is good judgement.

You do not have to be a technical wizard or demonstrate deep knowledge of the
entire codebase to become a committer. You just need to know what you don't
know. Non-code contributions are just as valuable in the path to commit access.
If your patches adhere to the guidelines in this file, adhere to all the usual
unquantifiable rules of coding (code should be readable, robust, maintainable, etc.),
and respect the Hippocratic Principle of "first, do no harm", then you will probably
get commit access pretty quickly. The size, complexity, and quantity of your patches
do not matter as much as the degree of care you show in avoiding bugs and minimizing
unnecessary impact on the rest of the code. Many full committers are people who have
not made major code contributions, but rather lots of small, clean fixes, each of
which was an unambiguous improvement to the code. (Of course, this does not mean the
project needs a bunch of very trivial patches whose only purpose is to gain commit
access; knowing what's worth a patch post and what's not is part of showing good
judgement.)


Windows CI
----------
The infrastructure for running the CI against Windows is different from the usual
runners, due to a combination of licensing technicalities and differing
containerisation support.

The scripts used to generate a CI runner can be found at
`https://gitlab.com/BuildStream/windows-startup-script`.
The `wsl` branch can be used to generate a runner for WSL, and the `win32` branch
can be used to generate a native-windows runner.


Further information
-------------------

.. toctree::
   :maxdepth: 1

   hacking/coding_guidelines.rst
   hacking/using_the_testsuite.rst
   hacking/writing_documentation.rst
   hacking/writing_plugins.rst
   hacking/measuring_performance.rst
   hacking/making_releases.rst
   hacking/grpc_protocols.rst
   hacking/managing_data_files.rst
   hacking/updating_python_deps.rst
   hacking/ui.rst
