#
#  Copyright (C) 2016-2018 Codethink Limited
#  Copyright (C) 2017-2020 Bloomberg Finance LP
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

from typing import TYPE_CHECKING, Iterator

from ._context import Context

from .storage._casbaseddirectory import CasBasedDirectory

if TYPE_CHECKING:
    from typing import List

    from .source import Source

# An ElementSources object represents the combined sources of an element.
class ElementSources:
    def __init__(self, context: Context):

        self._context = context
        self._sources = []  # type: List[Source]
        self.vdir = None  # Directory with staged sources
        self._sourcecache = context.sourcecache  # Source cache
        self._is_resolved = False  # Whether the source is fully resolved or not
        self._cached = None  # If the sources are known to be successfully cached in CAS

        # the index of the last source in this element that requires previous
        # sources for staging
        self._last_source_requires_previous_idx = None

    # add_source():
    #
    # Append source to this list of element sources.
    #
    # Args:
    #   source (Source): The source to add
    #
    def add_source(self, source):
        self._sources.append(source)

    # sources():
    #
    # A generator function to enumerate the element sources
    #
    # Yields:
    #   Source: The individual sources
    #
    def sources(self) -> Iterator["Source"]:
        for source in self._sources:
            yield source

    # track():
    #
    # Calls track() on the Element sources
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    # Returns:
    #    (list): A list of Source object ids and their new references
    #
    def track(self, workspace):
        refs = []
        for index, source in enumerate(self._sources):
            old_ref = source.get_ref()
            new_ref = source._track(self._sources[0:index])
            refs.append((source._unique_id, new_ref))

            # Complimentary warning that the new ref will be unused.
            if old_ref != new_ref and workspace:
                detail = (
                    "This source has an open workspace.\n"
                    + "To start using the new reference, please close the existing workspace."
                )
                source.warn("Updated reference will be ignored as source has open workspace", detail=detail)

        return refs

    # stage():
    #
    # Stage the element sources to a directory
    #
    # Returns:
    #     (:class:`.storage.Directory`): A virtual directory object to stage sources into.
    #
    def stage(self):
        # Assert sources are cached
        assert self.cached()

        self.vdir = CasBasedDirectory(self._context.get_cascache())

        if self._sources:
            # find last required source
            last_required_previous_idx = self._last_source_requires_previous()

            for source in self._sources[last_required_previous_idx:]:
                source_dir = self._sourcecache.export(source)
                self.vdir.import_files(source_dir)

        return self.vdir

    # fetch_done()
    #
    # Indicates that fetching the sources for this element has been done.
    #
    # Args:
    #   fetched_original (bool): Whether the original sources had been asked (and fetched) or not
    #
    def fetch_done(self, fetched_original):
        self._cached = True

        for source in self._sources:
            source._fetch_done(fetched_original)

    # push()
    #
    # Push the element's sources.
    #
    # Returns:
    #   (bool): True if the remote was updated, False if it already existed
    #           and no updated was required
    #
    def push(self):
        pushed = False

        for source in self.sources():
            if self._sourcecache.push(source):
                pushed = True

        return pushed

    # init_workspace():
    #
    # Initialises a new workspace from the element sources.
    #
    # Args:
    #   directory (str): Path of the workspace to init
    #
    def init_workspace(self, directory: str):
        for source in self.sources():
            source._init_workspace(directory)

    # fetch():
    #
    # Fetch the element sources.
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    def fetch(self, fetch_original=False):
        previous_sources = []
        fetch_needed = False

        if self._sources and not fetch_original:
            for source in self._sources:
                if self._sourcecache.contains(source):
                    continue

                # try and fetch from source cache
                if not source._is_cached() and self._sourcecache.has_fetch_remotes():
                    if self._sourcecache.pull(source):
                        continue

                fetch_needed = True

        # We need to fetch original sources
        if fetch_needed or fetch_original:
            for source in self.sources():
                if not source._is_cached():
                    source._fetch(previous_sources)
                previous_sources.append(source)

            self._cache_sources()

    # get_unique_key():
    #
    # Return something which uniquely identifies the combined sources of the
    # element.
    #
    # Returns:
    #    (str, list, dict): A string, list or dictionary as unique identifier
    #
    def get_unique_key(self):
        result = []

        for source in self._sources:
            result.append({"key": source._get_unique_key(), "name": source._get_source_name()})

        return result

    # cached():
    #
    # Check if the element sources are cached in CAS, generating the source
    # cache keys if needed.
    #
    # Returns:
    #    (bool): True if the element sources are cached
    #
    def cached(self):
        if self._cached is not None:
            return self._cached

        sourcecache = self._sourcecache

        # Go through sources we'll cache generating keys
        for ix, source in enumerate(self._sources):
            if not source._key:
                if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                    source._generate_key(self._sources[:ix])
                else:
                    source._generate_key([])

        # Check all sources are in source cache
        for source in self._sources:
            if not sourcecache.contains(source):
                return False

        self._cached = True
        return True

    # is_resolved():
    #
    # Get whether all sources of the element are resolved
    #
    # Returns:
    #    (bool): True if all element sources are resolved
    #
    def is_resolved(self):
        return self._is_resolved

    # cached_original():
    #
    # Get whether all the sources of the element have their own cached
    # copy of their sources.
    #
    # Returns:
    #    (bool): True if all element sources have the original sources cached
    #
    def cached_original(self):
        return all(source._is_cached() for source in self._sources)

    # update_resolved_state():
    #
    # Updates source's resolved state
    #
    # An element's source state must be resolved before it may compute
    # cache keys, because the source's ref, whether defined in yaml or
    # from the workspace, is a component of the element's cache keys.
    #
    def update_resolved_state(self):
        for source in self._sources:
            if not source.is_resolved():
                break
        else:
            self._is_resolved = True

    # preflight():
    #
    # A internal wrapper for calling the abstract preflight() method on
    # the element and its sources.
    #
    def preflight(self):
        # Ensure that the first source does not need access to previous sources
        if self._sources and self._sources[0]._requires_previous_sources():
            from .element import ElementError  # pylint: disable=cyclic-import

            raise ElementError(
                "{}: {} cannot be the first source of an element "
                "as it requires access to previous sources".format(self, self._sources[0])
            )

        # Preflight the sources
        for source in self.sources():
            source._preflight()

    # _cache_sources():
    #
    # Caches the sources into the local CAS
    #
    def _cache_sources(self):
        if self._sources and not self.cached():
            last_requires_previous = 0
            # commit all other sources by themselves
            for idx, source in enumerate(self._sources):
                if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                    self._sourcecache.commit(source, self._sources[last_requires_previous:idx])
                    last_requires_previous = idx
                else:
                    self._sourcecache.commit(source, [])

    # _last_source_requires_previous
    #
    # This is the last source that requires previous sources to be cached.
    # Sources listed after this will be cached separately.
    #
    # Returns:
    #    (int): index of last source that requires previous sources
    #
    def _last_source_requires_previous(self):
        if self._last_source_requires_previous_idx is None:
            last_requires_previous = 0
            for idx, source in enumerate(self._sources):
                if source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                    last_requires_previous = idx
            self._last_source_requires_previous_idx = last_requires_previous
        return self._last_source_requires_previous_idx
