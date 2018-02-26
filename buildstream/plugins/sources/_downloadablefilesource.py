"""A base abstract class for source implementations which download a file"""

import os
import urllib.request
import urllib.error
import contextlib
import re
import shutil

from distutils.version import LooseVersion

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class DownloadableFileSource(Source):

    COMMON_CONFIG_KEYS = Source.COMMON_CONFIG_KEYS + ['url', 'ref', 'etag', 'version']

    def configure(self, node):
        self.original_url = self.node_get_member(node, str, 'url')
        self.version = self.node_get_member(node, str, 'version', '') or None
        self.ref = self.node_get_member(node, str, 'ref', '') or None
        self.etag = self.node_get_member(node, str, 'etag', '') or None
        self.url = self.translate_url(self.original_url)

        if '{version}' in os.path.basename(self.url):
            self.url_format = self.url
            if self.version:
                self.alias_url = self.original_url.format(version=self.version)
                self.url = self.url_format.format(version=self.version)
            else:
                self.alias_url = None
                self.url = None
        else:
            self.alias_url = self.original_url
            self.url_format = None

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.alias_url, self.ref]

    def get_consistency(self):
        if self.alias_url is None or self.ref is None:
            return Consistency.INCONSISTENT

        if os.path.isfile(self._get_mirror_file()):
            return Consistency.CACHED

        else:
            return Consistency.RESOLVED

    def get_ref(self):
        return (self.ref, self.etag, self.version)

    def set_ref(self, ref, node):
        self.ref, self.etag, self.version = ref

        if self.version:
            node['version'] = self.version
        if self.etag:
            node['etag'] = self.etag
        node['ref'] = self.ref

    def track(self):
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        with self.timed_activity("Tracking {}".format(self.url_format or self.url),
                                 silent_nested=True):
            if self.url_format:
                try:
                    filename_format = os.path.basename(self.url_format)
                    index = filename_format.find('{version}')
                    escaped_prefix = re.escape('href="' + filename_format[:index])
                    escaped_suffix = re.escape(filename_format[index + len('{version}'):] + '"')
                    pattern = re.compile(escaped_prefix + r'([0-9.]+)' + escaped_suffix)
                    request = urllib.request.Request(self.url_format[:-len(filename_format)])
                    with contextlib.closing(urllib.request.urlopen(request)) as response:
                        info = response.info()
                        charset = info.get_content_charset()
                        listing = response.read().decode(charset or 'utf-8')

                        new_version = None
                        for match in re.findall(pattern, listing):
                            if new_version is None or LooseVersion(match) > LooseVersion(new_version):
                                new_version = match

                except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError) as e:
                    raise SourceError("{}: Error tracking {}: {}"
                                      .format(self, self.url_format, e)) from e

                if new_version is None:
                    raise SourceError("{}: Error tracking {}: Pattern not found"
                                      .format(self, self.url_format))

                self.alias_url = self.original_url.format(version=new_version)
                self.url = self.url_format.format(version=new_version)
            else:
                new_version = None

            new_ref, new_etag = self._ensure_mirror()

            if self.ref and self.ref != new_ref and self.version == new_version:
                detail = "When tracking, new ref differs from current ref:\n" \
                    + "  Tracked URL: {}\n".format(self.url) \
                    + "  Current ref: {}\n".format(self.ref) \
                    + "  New ref: {}\n".format(new_ref)
                self.warn("Potential man-in-the-middle attack!", detail=detail)

            return (new_ref, new_etag, new_version)

    def fetch(self):

        # Just a defensive check, it is impossible for the
        # file to be already cached because Source.fetch() will
        # not be called if the source is already Consistency.CACHED.
        #
        if os.path.isfile(self._get_mirror_file()):
            return  # pragma: nocover

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        with self.timed_activity("Fetching {}".format(self.url), silent_nested=True):
            sha256, etag = self._ensure_mirror()
            if sha256 != self.ref:
                raise SourceError("File downloaded from {} has sha256sum '{}', not '{}'!"
                                  .format(self.url, sha256, self.ref))

    def _ensure_mirror(self):
        # Downloads from the url and caches it according to its sha256sum.
        try:
            with self.tempdir() as td:
                default_name = os.path.basename(self.url)
                request = urllib.request.Request(self.url)
                request.add_header('Accept', '*/*')

                # Do not re-download the file if the ETag matches
                if self.etag and self.get_consistency() == Consistency.CACHED:
                    request.add_header('If-None-Match', self.etag)

                with contextlib.closing(urllib.request.urlopen(request)) as response:
                    info = response.info()

                    etag = info['ETag'] if 'ETag' in info else None

                    filename = info.get_filename(default_name)
                    filename = os.path.basename(filename)
                    local_file = os.path.join(td, filename)
                    with open(local_file, 'wb') as dest:
                        shutil.copyfileobj(response, dest)

                # Make sure url-specific mirror dir exists.
                if not os.path.isdir(self._get_mirror_dir()):
                    os.makedirs(self._get_mirror_dir())

                # Store by sha256sum
                sha256 = utils.sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                os.rename(local_file, self._get_mirror_file(sha256))

                return (sha256, etag)

        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 304:
                # Already cached and not modified
                return (self.ref, self.etag)

            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.url, e)) from e

    def _get_mirror_dir(self):
        return os.path.join(self.get_mirror_directory(),
                            utils.url_directory_name(self.alias_url))

    def _get_mirror_file(self, sha=None):
        return os.path.join(self._get_mirror_dir(), sha or self.ref)
