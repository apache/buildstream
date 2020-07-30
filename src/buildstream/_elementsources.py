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

from . import _cachekey, utils
from ._context import Context
from ._protos.buildstream.v2 import source_pb2
from .plugin import Plugin

from .storage._casbaseddirectory import CasBasedDirectory

if TYPE_CHECKING:
    from typing import List

    # pylint: disable=cyclic-import
    from .source import Source
    from ._project import Project

    # pylint: enable=cyclic-import

# An ElementSources object represents the combined sources of an element.
class ElementSources:
    def __init__(self, context: Context, project: "Project", plugin: Plugin):

        self._context = context
        self._project = project
        self._plugin = plugin
        self._sources = []  # type: List[Source]
        self._sourcecache = context.sourcecache  # Source cache
        self._elementsourcescache = context.elementsourcescache  # Cache of staged element sources
        self._is_resolved = False  # Whether the source is fully resolved or not
        self._cached = None  # If the sources are known to be successfully cached in CAS
        self._cache_key = None  # Our cached cache key
        self._proto = None  # The cached Source proto

        # the index of the last source in this element that requires previous
        # sources for staging
        self._last_source_requires_previous_idx = None

    # get_project():
    #
    # Return the project associated with this object
    #
    def get_project(self):
        return self._project

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

    # stage_and_cache():
    #
    # Stage the element sources to a directory in CAS
    #
    def stage_and_cache(self):
        vdir = self._stage()

        source_proto = source_pb2.Source()
        source_proto.files.CopyFrom(vdir._get_digest())

        self._elementsourcescache.store_proto(self, source_proto)

        self._proto = source_proto
        self._cached = True

    # get_files():
    #
    # Get a virtual directory for the staged source files
    #
    # Returns:
    #     (Directory): The virtual directory object
    #
    def get_files(self):
        # Assert sources are cached
        assert self.cached()

        cas = self._context.get_cascache()
        return CasBasedDirectory(cas, digest=self._proto.files)

    # fetch_done()
    #
    # Indicates that fetching the sources for this element has been done.
    #
    # Args:
    #   fetched_original (bool): Whether the original sources had been asked (and fetched) or not
    #
    def fetch_done(self, fetched_original):
        self._proto = self._elementsourcescache.load_proto(self)
        assert self._proto
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
            if source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH or source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                continue

            if self._sourcecache.contains(source) and self._sourcecache.push(source):
                pushed = True

        if self._elementsourcescache.push(self, self._plugin):
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
    # Fetch the combined or individual element sources.
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    def fetch(self):
        if self.cached():
            return

        # Try to fetch staged sources from remote source cache
        if self._elementsourcescache.has_fetch_remotes() and self._elementsourcescache.pull(self, self._plugin):
            self.fetch_done(False)
            return

        # Otherwise, fetch individual sources
        self.fetch_sources()

    # fetch_sources():
    #
    # Fetch the individual element sources.
    #
    # Args:
    #   fetch_original (bool): Always fetch original source
    #
    # Raises:
    #    SourceError: If one of the element sources has an error
    #
    def fetch_sources(self, *, fetch_original=False):
        previous_sources = []
        for source in self._sources:
            if (
                fetch_original
                or source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH
                or source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE
            ):
                # Source depends on previous sources, it cannot be stored in
                # CAS-based source cache on its own. Fetch original source
                # if it's not in the plugin-specific cache yet.
                if not source._is_cached():
                    source._fetch(previous_sources)
            else:
                self._fetch_source(source)

            previous_sources.append(source)

    # get_unique_key():
    #
    # Return something which uniquely identifies the combined sources of the
    # element.
    #
    # Returns:
    #    (str, list, dict): A string, list or dictionary as unique identifier
    #
    def get_unique_key(self):
        assert self.is_resolved()

        result = []

        for source in self._sources:
            result.append({"key": source._get_unique_key(), "name": source.get_kind()})

        return result

    # get_cache_key():
    #
    # Return cache key for the combined element sources
    #
    def get_cache_key(self):
        return self._cache_key

    # _get_brief_display_key()
    #
    # Returns an abbreviated cache key for display purposes
    #
    # Returns:
    #    (str): An abbreviated hex digest cache key for this Element
    #
    def get_brief_display_key(self):
        context = self._context
        key = self._cache_key

        length = min(len(key), context.log_key_length)
        return key[:length]

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

        cas = self._context.get_cascache()
        elementsourcescache = self._elementsourcescache

        source_proto = elementsourcescache.load_proto(self)
        if not source_proto:
            self._cached = False
            return False

        if not cas.contains_directory(source_proto.files, with_files=True):
            self._cached = False
            return False

        self._proto = source_proto
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
        if self._is_resolved:
            # Already resolved
            return

        for source in self._sources:
            if not source.is_resolved():
                return

            # Source is resolved, generate its cache key
            source._generate_key()

        self._is_resolved = True

        # Also generate the cache key for the combined element sources
        unique_key = self.get_unique_key()
        self._cache_key = _cachekey.generate_key(unique_key)

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

    # _fetch_source():
    #
    # Fetch a single source into the local CAS-based source cache
    #
    # Args:
    #   source (Source): The source to fetch
    #
    def _fetch_source(self, source):
        # Cannot store a source in the CAS-based source cache on its own
        # if the source depends on previous sources.
        assert not source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH and not source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE

        if self._sourcecache.contains(source):
            # Already cached
            return

        cached_original = source._is_cached()
        if not cached_original:
            if self._sourcecache.has_fetch_remotes() and self._sourcecache.pull(source):
                # Successfully fetched individual source from remote source cache
                return

            # Unable to fetch source from remote source cache, fall back to
            # fetching the original source.
            source._fetch([])

        # Stage original source into the local CAS-based source cache
        self._sourcecache.commit(source)

    # _stage():
    #
    # Stage the element sources
    #
    def _stage(self):
        vdir = CasBasedDirectory(self._context.get_cascache())

        for source in self._sources:
            if source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH or source.BST_REQUIRES_PREVIOUS_SOURCES_STAGE:
                if source.BST_STAGE_VIRTUAL_DIRECTORY:
                    source._stage(vdir)
                else:
                    with utils._tempdir(dir=self._context.tmpdir, prefix="staging-temp") as tmpdir:
                        # Stage previous sources
                        vdir.export_files(tmpdir)

                        source._stage(tmpdir)

                        # Capture modified tree
                        vdir._clear()
                        vdir.import_files(tmpdir)
            else:
                source_dir = self._sourcecache.export(source)
                vdir.import_files(source_dir)

        return vdir
