#
#  Copyright Bloomberg Finance LP
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
#        Antoine Wacheux <awacheux@bloomberg.net>
#        Gokcen Nurlu <gnurlu1@bloomberg.net>
"""
SourceTransform
===============


.. _core_sourcetransform_abstract_methods:

This plugin is a base for package-manager-like source plugins. It can't be the
first source in an element and it makes use of previously tracked & fetched
sources.

Abstract Methods
----------------
For loading and configuration purposes, SourceTransform based plugins must
implement the
:ref:`Plugin base class abstract methods <core_plugin_abstract_methods>` and
:ref:`Source base class abstract methods <core_source_abstract_methods>`.

Keep in mind that SourceTransform exposes the following abstract methods that
have function signature different than
:ref:`their counterparts in Source <core_source_abstract_methods>` and these
have to be implemented instead.

* :func:`SourceTransform.track(previous_staging_dir) <buildstream.source.SourceTransform.track>`

  Automatically derive a new ref from previously staged sources.

* :func:`SourceTransform.fetch(previous_staging_dir) <buildstream.source.SourceTransform.fetch>`

  Fetch the actual payload for the currently set ref.

"""

from buildstream import Consistency
from .source import Source
from . import utils
from ._exceptions import ImplError


class SourceTransform(Source):
    def __ensure_previous_sources(self, previous_sources):
        for src in previous_sources:
            if src.get_consistency() == Consistency.RESOLVED:
                src._fetch()
            elif src.get_consistency() == Consistency.INCONSISTENT:
                new_ref = src._track()
                src._save_ref(new_ref)
                src._fetch()

    def track(self, previous_staging_dir):
        """Resolve a new ref from the plugin's track option

        Different than :func:`~buildstream.source.Source.track`, implementors
        have access to previous sources. This one is also mandatory to
        implement.

        Args:
           previous_staging_dir (str): Path to a temporary directory where
                                       previous sources are staged.

        Returns:
           (simple object): A new internal source reference, or None

        See :func:`~buildstream.source.Source.get_ref` for a discussion on
        the *ref* parameter.
        """
        raise ImplError("SourceTransform plugin '{}' does not implement track()".format(self.get_kind()))

    def fetch(self, previous_staging_dir):
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Different than :func:`~buildstream.source.Source.fetch`, implementors
        have access to previous sources.

        Args:
           previous_staging_dir (str): Path to a temporary directory where
                                       previous sources are staged.

        Raises:
           :class:`.SourceError`

        Implementors should raise :class:`.SourceError` if the there is some
        network error or if the source reference could not be matched.
        """
        raise ImplError("SourceTransform plugin '{}' does not implement fetch()".format(self.get_kind()))

    def _track(self, previous_sources):
        self.__ensure_previous_sources(previous_sources)

        with self.tempdir() as staging_directory:
            for src in previous_sources:
                src._stage(staging_directory)

            # Rest is same with Source._track(), but calling a different .track
            new_ref = self.track(staging_directory)
            current_ref = self.get_ref()

            if new_ref is None:
                # No tracking, keep current ref
                new_ref = current_ref

            if current_ref != new_ref:
                self.info("Found new revision: {}".format(new_ref))

            return new_ref

    def _fetch(self, previous_sources):
        self.__ensure_previous_sources(previous_sources)

        with self.tempdir() as staging_directory:
            for src in previous_sources:
                src._stage(staging_directory)

            self.fetch(staging_directory)
