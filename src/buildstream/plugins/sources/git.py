#
#  Copyright (C) 2016 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

"""
git - stage files from a git repository
=======================================

**Host dependencies:**

  * git

.. attention::

    Note that this plugin **will checkout git submodules by default**; even if
    they are not specified in the `.bst` file.

**Usage:**

.. code:: yaml

   # Specify the git source kind
   kind: git

   # Specify the repository url, using an alias defined
   # in your project configuration is recommended.
   url: upstream:foo.git

   # Optionally specify a symbolic tracking branch or tag, this
   # will be used to update the 'ref' when refreshing the pipeline.
   track: master

   # Optionally specify the ref format used for tracking.
   # The default is 'sha1' for the raw commit hash.
   # If you specify 'git-describe', the commit hash will be prefixed
   # with the closest tag.
   ref-format: sha1

   # Specify the commit ref, this must be specified in order to
   # checkout sources and build, but can be automatically updated
   # if the 'track' attribute was specified.
   ref: d63cbb6fdc0bbdadc4a1b92284826a6d63a7ebcd

   # Optionally specify whether submodules should be checked-out.
   # This is done recursively, as with `git clone --recurse-submodules`.
   # If not set, this will default to 'True'
   checkout-submodules: True

   # If your repository has submodules, explicitly specifying the
   # url from which they are to be fetched allows you to easily
   # rebuild the same sources from a different location. This is
   # especially handy when used with project defined aliases which
   # can be redefined at a later time.
   # You may also explicitly specify whether to check out this
   # submodule. If 'checkout' is set, it will control whether to
   # checkout that submodule and recurse into it. It defaults to the
   # value of 'checkout-submodules'.
   submodules:
     plugins/bar:
       url: upstream:bar.git
       checkout: True
     plugins/bar/quux:
       checkout: False
     plugins/baz:
       url: upstream:baz.git
       checkout: False

   # Enable tag tracking.
   #
   # This causes the `tags` metadata to be populated automatically
   # as a result of tracking the git source.
   #
   # By default this is 'False'.
   #
   track-tags: True

   # If the list of tags below is set, then a lightweight dummy
   # git repository will be staged along with the content at
   # build time.
   #
   # This is useful for a growing number of modules which use
   # `git describe` at build time in order to determine the version
   # which will be encoded into the built software.
   #
   # The 'tags' below is considered as a part of the git source
   # reference and will be stored in the 'project.refs' file if
   # that has been selected as your project's ref-storage.
   #
   # Migration notes:
   #
   #   If you are upgrading from BuildStream 1.2, which used to
   #   stage the entire repository by default, you will notice that
   #   some modules which use `git describe` are broken, and will
   #   need to enable this feature in order to fix them.
   #
   #   If you need to enable this feature without changing the
   #   the specific commit that you are building, then we recommend
   #   the following migration steps for any git sources where
   #   `git describe` is required:
   #
   #     o Enable `track-tags` feature
   #     o Set the `track` parameter to the desired commit sha which
   #       the current `ref` points to
   #     o Run `bst source track` for these elements, this will result in
   #       populating the `tags` portion of the refs without changing
   #       the refs
   #     o Restore the `track` parameter to the branches which you have
   #       previously been tracking afterwards.
   #
   tags:
   - tag: lightweight-example
     commit: 04ad0dc656cb7cc6feb781aa13bdbf1d67d0af78
     annotated: false
   - tag: annotated-example
     commit: 10abe77fe8d77385d86f225b503d9185f4ef7f3a
     annotated: true

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.

**Configurable Warnings:**

This plugin provides the following :ref:`configurable warnings <configurable_warnings>`:

- ``git:inconsistent-submodule`` - A submodule present in the git repository's .gitmodules was never
  added with `git submodule add`.

- ``git:unlisted-submodule`` - A submodule is present in the git repository but was not specified in
  the source configuration and was not disabled for checkout.

- ``git:invalid-submodule`` - A submodule is specified in the source configuration but does not exist
  in the repository.

This plugin also utilises the following configurable :class:`core warnings <buildstream.types.CoreWarnings>`:

- :attr:`ref-not-in-track <buildstream.types.CoreWarnings.REF_NOT_IN_TRACK>` - The provided ref was not
  found in the provided track in the element's git repository.
"""

from buildstream import _GitSourceBase


class GitSource(_GitSourceBase):

    BST_MIN_VERSION = "2.0"


# Plugin entry point
def setup():
    return GitSource
