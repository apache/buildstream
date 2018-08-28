"""
DownloadableFileSource - Abstract class for downloading files
=============================================================
A base abstract class for source implementations which download a file.

Derived classes must write their own stage() implementation, using the
public APIs exposed in this class.

Derived classes must also chain up to the parent method in their get_unique_key()
implementations.

"""

import os
import urllib.request
import urllib.error
import contextlib
import shutil

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class DownloadableFileSource(Source):
    # pylint: disable=attribute-defined-outside-init

    COMMON_CONFIG_KEYS = Source.COMMON_CONFIG_KEYS + ['url', 'ref', 'etag']

    #####################################
    # Implementations of abstract methods
    #####################################

    def configure(self, node):
        self.__original_url = self.node_get_member(node, str, 'url')
        self.__ref = self.node_get_member(node, str, 'ref', None)
        self.__url = self.translate_url(self.__original_url)
        self.__warn_deprecated_etag(node)

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.__original_url, self.__ref]

    def get_consistency(self):
        if self.__ref is None:
            return Consistency.INCONSISTENT

        if os.path.isfile(self.get_mirror_file()):
            return Consistency.CACHED

        else:
            return Consistency.RESOLVED

    def load_ref(self, node):
        self.__ref = self.node_get_member(node, str, 'ref', None)
        self.__warn_deprecated_etag(node)

    def get_ref(self):
        return self.__ref

    def set_ref(self, ref, node):
        node['ref'] = self.__ref = ref

    def track(self):
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        with self.timed_activity("Tracking {}".format(self.__url),
                                 silent_nested=True):
            new_ref = self.ensure_mirror()

            if self.__ref and self.__ref != new_ref:
                detail = "When tracking, new ref differs from current ref:\n" \
                    + "  Tracked URL: {}\n".format(self.__url) \
                    + "  Current ref: {}\n".format(self.__ref) \
                    + "  New ref: {}\n".format(new_ref)
                self.warn("Potential man-in-the-middle attack!", detail=detail)

            return new_ref

    def fetch(self):

        # Just a defensive check, it is impossible for the
        # file to be already cached because Source.fetch() will
        # not be called if the source is already Consistency.CACHED.
        #
        if os.path.isfile(self.get_mirror_file()):
            return  # pragma: nocover

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        with self.timed_activity("Fetching {}".format(self.__url), silent_nested=True):
            sha256 = self.ensure_mirror()
            if sha256 != self.__ref:
                raise SourceError("File downloaded from {} has sha256sum '{}', not '{}'!"
                                  .format(self.__url, sha256, self.__ref))
    ################
    # Public methods
    ################

    def ensure_mirror(self):
        """Downloads from the url and caches it according to its sha256sum

        Returns:
           (str): The sha256sum of the mirrored file

        Raises:
           :class:`.SourceError`
        """
        try:
            with self.tempdir() as td:
                default_name = os.path.basename(self.__url)
                request = urllib.request.Request(self.__url)
                request.add_header('Accept', '*/*')

                # We do not use etag in case what we have in cache is
                # not matching ref in order to be able to recover from
                # corrupted download.
                if self.__ref:
                    etag = self.__get_etag(self.__ref)

                    # Do not re-download the file if the ETag matches.
                    if etag and self.get_consistency() == Consistency.CACHED:
                        request.add_header('If-None-Match', etag)

                with contextlib.closing(urllib.request.urlopen(request)) as response:
                    info = response.info()

                    etag = info['ETag'] if 'ETag' in info else None

                    filename = info.get_filename(default_name)
                    filename = os.path.basename(filename)
                    local_file = os.path.join(td, filename)
                    with open(local_file, 'wb') as dest:
                        shutil.copyfileobj(response, dest)

                # Make sure url-specific mirror dir exists.
                if not os.path.isdir(self.__get_mirror_dir()):
                    os.makedirs(self.__get_mirror_dir())

                # Store by sha256sum
                sha256 = utils.sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                os.rename(local_file, self.get_mirror_file(sha=sha256))

                if etag:
                    self.__store_etag(sha256, etag)
                return sha256

        except urllib.error.HTTPError as e:
            if e.code == 304:
                # 304 Not Modified.
                # Because we use etag only for matching ref, currently specified ref is what
                # we would have downloaded.
                return self.__ref
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.__url, e), temporary=True) from e

        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError, ValueError) as e:
            # Note that urllib.request.Request in the try block may throw a
            # ValueError for unknown url types, so we handle it here.
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.__url, e), temporary=True) from e

    def get_mirror_file(self, *, sha=None):
        """Calculates the path to where this source stores the downloaded file

        Users are expected to read the file this points to when staging their source.

        Returns:
           (str): A path to the file the source should be cached at
        """
        return os.path.join(self.__get_mirror_dir(), sha or self.__ref)

    #######################
    # Local Private methods
    #######################

    def __get_mirror_dir(self):
        # Get the directory this source should store things in, for a given URL
        return os.path.join(self.get_mirror_directory(),
                            utils.url_directory_name(self.__original_url))

    def __warn_deprecated_etag(self, node):
        # Warn the user if the 'etag' field is being used
        etag = self.node_get_member(node, str, 'etag', None)
        if etag:
            provenance = self.node_provenance(node, member_name='etag')
            self.warn('{} "etag" is deprecated and ignored.'.format(provenance))

    def __get_etag(self, ref):
        # Retrieve the etag's data from disk
        etagfilename = os.path.join(self.__get_mirror_dir(), '{}.etag'.format(ref))
        if os.path.exists(etagfilename):
            with open(etagfilename, 'r') as etagfile:
                return etagfile.read()

        return None

    def __store_etag(self, ref, etag):
        # Write the etag's data to disk
        etagfilename = os.path.join(self.__get_mirror_dir(), '{}.etag'.format(ref))
        with utils.save_file_atomic(etagfilename) as etagfile:
            etagfile.write(etag)
