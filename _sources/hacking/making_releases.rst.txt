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



.. _making_releases:

Making releases
---------------
This is a checklist of activities which must be observed when creating
BuildStream releases, it is important to keep this section up to date
whenever the release process changes.


Requirements
~~~~~~~~~~~~
There are a couple of requirements and accounts required in order
to publish a release.

* Ability to send email to ``dev@buildstream.apache.org``.

* Shell account at ``master.gnome.org``.

* Access to the `BuildStream project on PyPI <https://pypi.org/project/BuildStream/>`_

* An email client which still knows how to send emails in plain text.


Pre-release changes
~~~~~~~~~~~~~~~~~~~
Before actually rolling the release, here is a list of changes which
might need to be done in preparation of the release.

* Ensure that the man pages are up to date

  The man pages are committed to the repository because we are
  currently unable to integrate this generation into the setuptools
  build phase, as outlined in issue #8.

  If any of the user facing CLI has changed, or if any of the
  related docstrings have changed, then you should
  :ref:`regenerate the man pages <contributing_man_pages>` and
  add/commit the results before wrapping a release.

* Ensure the documentation session HTML is up to date

  The session HTML files are committed to the repository for multiple
  reasons, one of them being that the documentation must be buildable
  from within a release build environment so that downstream distribution
  packagers can easily create the docs package.

  This is currently only needed for the first stable release
  in a stable line of releases, after this point the API is frozen
  and will not change for the remainder of the stable release lifetime,
  so nothing interesting will have changed in these session files.

  If regeneration is needed, follow :ref:`the instructions above <contributing_session_html>`.

* Ensure the NEWS entry is up to date and ready

  For a stable release where features have not been added, we
  should at least add some entries about the issues which have
  been fixed since the last stable release.

  For development releases, it is worthwhile going over the
  existing entries and ensuring all the major feature additions
  are mentioned and there are no redundancies.

* Push pre-release changes

  Now that any final pre-release changes to generated files or NEWS have
  been made, push these directly to the upstream repository.

  Do not sit around waiting for CI or approval, these superficial changes
  do not affect CI and you are intended to push these changes directly
  to the upstream repository.


Release process
~~~~~~~~~~~~~~~

* Ensure that the latest commit is passing in CI

  Of course, we do not release software which does not pass it's own
  tests.

* Get the list of contributors

  The list of contributors for a given list is a list of
  any contributors who have landed any patches since the
  last release.

  An easy way to get this list is to ask git to summarize
  the authors of commits since the *last release tag*. For
  example, if we are about to create the ``1.1.1`` release, then
  we need to observe all of the commits since the ``1.1.0``
  release:

  .. code:: shell

     git shortlog -s 1.1.0...@

  At times, the same contributor might make contributions from different
  machines which they have setup their author names differently, you
  can see that some of the authors are actually duplicates, then
  remove the duplicates.

* Start composing the release announcement email

  The first thing to do when composing the release email is to
  ensure your mail client has disabled any HTML formatting and will
  safely use plain text only.

  Try to make the release announcement consistent with other release
  announcements as much as possible, an example of the email
  can be `found here <https://mail.gnome.org/archives/buildstream-list/2019-February/msg00039.html>`_.

  The recipient of the email is ``dev@buildstream.apache.org`` and the title
  of the email should be of the form: ``BuildStream 1.1.1 released``, without
  any exclamation point.

  The format of the email is essentially::

    Hi all,

    This is the personalized message written to you about this
    release.

    If this is an unstable release, this should include a warning
    to this effect and an invitation to users to please help us
    test this release.

    This is also a good place to highlight specific bug fixes which
    users may have been waiting for, or highlight a new feature we
    want users to try out.


    What is BuildStream ?
    =====================
    This is a concise blurb which describes BuildStream in a couple of
    sentences, and is taken from the the README.rst.

    The easiest thing is to just copy this over from the last release email.


    =================
    buildstream 1.1.1
    =================
    This section is directly copy pasted from the top of the NEWS file


    Contributors
    ============
     - This is Where
     - You Put
     - The Contributor
     - Names Which
     - You Extracted
     - Using git shortlog -s


    Where can I get it ?
    ====================
    https://download.gnome.org/sources/BuildStream/1.1/

    For more information on the BuildStream project, visit our home page
    at https://buildstream.build/

* Publish the release tag

  Now that any pre-release changes are upstream, create and push the
  signed release tag like so:

  .. code:: shell

     git tag -s 1.1.1
     git push origin 1.1.1

  This will trigger the "Release actions" workflow which also takes care of:

    * uploading Github release artifacts
    * uploading Python source and binary packages to PyPI

* Upload the release tarball

  First get yourself into a clean repository state, ensure that you
  don't have any unfinished work or precious, uncommitted files lying
  around in your checkout and then run:

  .. code:: shell

     git clean -xdff

  Create the tarball with the following command:

  .. code:: shell

     python3 setup.py sdist

  And upload the resulting tarball to the master GNOME server:

  .. code:: shell

     scp dist/BuildStream-1.1.1.tar.gz <user>@master.gnome.org:

  And finally login to your account at ``master.gnome.org`` and run
  the install scripts to publish the tarball and update the mirrors:

  .. code:: shell

     ftpadmin install BuildStream-1.1.1.tar.gz

* Send the release email

  Now that the release tag is up and the tarball is published,
  you can send the release email.


Post-release activities
~~~~~~~~~~~~~~~~~~~~~~~
Once the release has been published, there are some activities
which need to be done to ensure everything is up to date.

* Check that the release was successfully uploaded to PyPI. If
  it is an unstable release, make sure the version on PyPI has
  the correct "dev0" postfix so to avoid being treated as stable.

* Update the topic line in the #buildstream IRC channel if needed

  The IRC channel usually advertizes the latest stable release
  in the topic line, now is the right time to update it.

* Update the website repository

  The website wants to link to release announcements, but this
  cannot be automated because we cannot guess what the link to
  the release email will be in the mailing list archive.

  Find the URL to the announcement you just published
  `in the mailing list archives <https://lists.apache.org/list.html?dev@buildstream.apache.org/>`_,
  and use that URL to update the ``anouncements.json`` file in the website
  repository.

  Commit and push this change to the the ``anouncements.json`` file to
  the upstream website repository, and gitlab will take care of automatically
  updating the website accordingly.

* Regenerate BuildStream documentation

  In order to update the badges we use in various documentation
  which reflects what is the latest stable releases and the latest
  development snapshots, we simply need to ensure a pipeline runs
  for the master branch in the BuildStream repository.

  You can do this by using the "Run Pipeline" feature on the
  `pipelines page in the gitlab UI <https://gitlab.com/BuildStream/buildstream/pipelines>`_.
