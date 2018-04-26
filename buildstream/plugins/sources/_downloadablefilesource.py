"""A base abstract class for source implementations which download a file"""

import os
import urllib.request
import urllib.error
import contextlib
import shutil

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class DownloadableFileSource(Source):
    # pylint: disable=attribute-defined-outside-init

    COMMON_CONFIG_KEYS = ['url', 'ref',
                          'etag', 'filename']
    COMMON_CONFIG_KEYS.extend(Source.COMMON_CONFIG_KEYS)

    def configure(self, node):
        self.original_url = self.node_get_member(node, str, 'url')
        self.ref = self.node_get_member(node, str, 'ref', None)
        self.url = self.translate_url(self.original_url)
        self._warn_deprecated_etag(node)
        self.filename = self.node_get_member(node, str, 'filename', None)
        if self.filename is None:
            self.filename = os.path.basename(self.url)

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.original_url, self.ref]

    def get_consistency(self):
        if self.ref is None:
            return Consistency.INCONSISTENT

        if self._get_mirror_file():
            return Consistency.CACHED

        else:
            return Consistency.RESOLVED

    def load_ref(self, node):
        self.ref = self.node_get_member(node, str, 'ref', None)
        self._warn_deprecated_etag(node)

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        node['ref'] = self.ref = ref

    def track(self):
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        with self.timed_activity("Tracking {}".format(self.url),
                                 silent_nested=True):
            new_ref = self._ensure_mirror()

            if self.ref and self.ref != new_ref:
                detail = "When tracking, new ref differs from current ref:\n" \
                    + "  Tracked URL: {}\n".format(self.url) \
                    + "  Current ref: {}\n".format(self.ref) \
                    + "  New ref: {}\n".format(new_ref)
                self.warn("Potential man-in-the-middle attack!", detail=detail)

            return new_ref

    def fetch(self):

        # Just a defensive check, it is impossible for the
        # file to be already cached because Source.fetch() will
        # not be called if the source is already Consistency.CACHED.
        #
        cachedfile = self._get_mirror_file()
        if cachedfile is not None and os.path.isfile(cachedfile):
            return  # pragma: nocover

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        with self.timed_activity("Fetching {}".format(self.url), silent_nested=True):
            sha256 = self._ensure_mirror()
            if sha256 != self.ref:
                raise SourceError("File downloaded from {} has sha256sum '{}', not '{}'!"
                                  .format(self.url, sha256, self.ref))

    def _warn_deprecated_etag(self, node):
        etag = self.node_get_member(node, str, 'etag', None)
        if etag:
            provenance = self.node_provenance(node, member_name='etag')
            self.warn('{} "etag" is deprecated and ignored.'.format(provenance))

    def update_mirror(self):
        self._ensure_mirror()

    def _get_etag(self, ref):
        mirrorfilename = self._get_mirror_file(sha=ref)
        if mirrorfilename:
            etagfilename = '{}.etag'.format(mirrorfilename)
            if os.path.exists(etagfilename):
                with open(etagfilename, 'r') as etagfile:
                    return etagfile.read()

        return None

    def _store_etag(self, ref, etag):
        mirrorfilename = self._get_mirror_file(sha=ref, create=True)
        etagfilename = '{}.etag'.format(mirrorfilename)
        with utils.save_file_atomic(etagfilename) as etagfile:
            etagfile.write(etag)

    def _ensure_mirror(self):
        # Downloads from the url and caches it along with its sha256sum and etag.
        try:
            with self.tempdir() as td:
                default_name = os.path.basename(self.url)
                request = urllib.request.Request(self.url)
                request.add_header('Accept', '*/*')

                # We do not use etag in case what we have in cache is
                # not matching ref in order to be able to recover from
                # corrupted download.
                if self.ref:
                    etag = self._get_etag(self.ref)

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

                # Store by sha256sum
                sha256 = utils.sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                mirrorfilename = self._get_mirror_file(sha=sha256, create=True)
                os.rename(local_file, mirrorfilename)
                if etag is not None:
                    with open('{}.etag'.format(mirrorfilename), 'w') as etagfile:
                        etagfile.write(etag)

                if etag:
                    self._store_etag(sha256, etag)
                return sha256

        except urllib.error.HTTPError as e:
            if e.code == 304:
                # 304 Not Modified.
                # Because we use etag only for matching ref, currently specified ref is what
                # we would have downloaded.
                return self.ref
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.url, e)) from e

        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError) as e:
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.url, e)) from e

    def _is_right_mirror(self, path, sha):
        shafilename = os.path.join(path, '{}.sha256'.format(self.filename))
        if os.path.exists(shafilename):
            with open(shafilename, 'r') as shafile:
                return shafile.read(64) == sha
        else:
            with open(shafilename, 'w') as shafile:
                shafile.write(sha)
            return True

    def _get_mirror_file(self, sha=None, create=False):
        if sha is None:
            sha = self.ref
        path = self.find_mirror_directory(self.original_url,
                                          lambda path: self._is_right_mirror(path, sha),
                                          create=create)
        if path:
            return os.path.join(path, self.filename)
        else:
            return None
