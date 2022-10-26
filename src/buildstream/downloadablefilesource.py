#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

"""
DownloadableFileSource - Abstract class for sources downloaded from a URI
=========================================================================

This DownloadableFileSource class is a convenience class on can derive for
implementing sources that get downloaded from a URI.

It provides utilities around handling mirrors, tracking and fetching the source.

Any derived classes must write their own stage() and get_unique_key()
implementation.


"""


import os
import urllib.request
import urllib.error
import contextlib
import shutil
import netrc

from .source import Source, SourceError
from . import utils


class _NetrcFTPOpener(urllib.request.FTPHandler):
    def __init__(self, netrc_config):
        self.netrc = netrc_config

    def _unsplit(self, host, port, user, passwd):
        if port:
            host = "{}:{}".format(host, port)
        if user:
            if passwd:
                user = "{}:{}".format(user, passwd)
            host = "{}@{}".format(user, host)

        return host

    def ftp_open(self, req):
        uri = urllib.parse.urlparse(req.full_url)

        username = uri.username
        password = uri.password

        if uri.username is None and self.netrc:
            entry = self.netrc.authenticators(uri.hostname)
            if entry:
                username, _, password = entry

        req.host = self._unsplit(uri.hostname, uri.port, username, password)

        return super().ftp_open(req)


class _NetrcPasswordManager:
    def __init__(self, netrc_config):
        self.netrc = netrc_config

    def add_password(self, realm, uri, user, passwd):
        pass

    def find_user_password(self, realm, authuri):
        if not self.netrc:
            return None, None
        parts = urllib.parse.urlsplit(authuri)
        entry = self.netrc.authenticators(parts.hostname)
        if not entry:
            return None, None
        else:
            login, _, password = entry
            return login, password


def _download_file(opener, url, etag, directory):
    default_name = os.path.basename(url)
    request = urllib.request.Request(url)
    request.add_header("Accept", "*/*")
    request.add_header("User-Agent", "BuildStream/2")

    if etag is not None:
        request.add_header("If-None-Match", etag)

    with contextlib.closing(opener.open(request)) as response:
        info = response.info()

        # some servers don't honor the 'If-None-Match' header
        if etag and info["ETag"] == etag:
            return None, None

        etag = info["ETag"]

        filename = info.get_filename(default_name)
        filename = os.path.basename(filename)
        local_file = os.path.join(directory, filename)
        with open(local_file, "wb") as dest:
            shutil.copyfileobj(response, dest)

    return local_file, etag


class DownloadableFileSource(Source):
    # pylint: disable=attribute-defined-outside-init

    COMMON_CONFIG_KEYS = Source.COMMON_CONFIG_KEYS + ["url", "ref", "etag"]

    __urlopener = None
    __default_mirror_file = None

    def configure(self, node):
        self.original_url = node.get_str("url")
        self.ref = node.get_str("ref", None)
        self.url = self.translate_url(self.original_url)
        self._mirror_dir = os.path.join(self.get_mirror_directory(), utils.url_directory_name(self.original_url))
        self._warn_deprecated_etag(node)

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.original_url, self.ref]

    def is_cached(self) -> bool:
        return os.path.isfile(self._get_mirror_file())

    def load_ref(self, node):
        self.ref = node.get_str("ref", None)
        self._warn_deprecated_etag(node)

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        node["ref"] = self.ref = ref

    def track(self):  # pylint: disable=arguments-differ
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        new_ref = self._ensure_mirror("Tracking {}".format(self.url))

        if self.ref and self.ref != new_ref:
            detail = (
                "When tracking, new ref differs from current ref:\n"
                + "  Tracked URL: {}\n".format(self.url)
                + "  Current ref: {}\n".format(self.ref)
                + "  New ref: {}\n".format(new_ref)
            )
            self.warn("Potential man-in-the-middle attack!", detail=detail)

        return new_ref

    def fetch(self):  # pylint: disable=arguments-differ

        # Just a defensive check, it is impossible for the
        # file to be already cached because Source.fetch() will
        # not be called if the source is already cached.
        #
        if os.path.isfile(self._get_mirror_file()):
            return  # pragma: nocover

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        sha256 = self._ensure_mirror(
            "Fetching {}".format(self.url),
        )
        if sha256 != self.ref:
            raise SourceError(
                "File downloaded from {} has sha256sum '{}', not '{}'!".format(self.url, sha256, self.ref)
            )

    def _warn_deprecated_etag(self, node):
        etag = node.get_str("etag", None)
        if etag:
            provenance = node.get_scalar(etag).get_provenance()
            self.warn('{} "etag" is deprecated and ignored.'.format(provenance))

    def _get_etag(self, ref):
        etagfilename = os.path.join(self._mirror_dir, "{}.etag".format(ref))
        if os.path.exists(etagfilename):
            with open(etagfilename, "r", encoding="utf-8") as etagfile:
                return etagfile.read()

        return None

    def _store_etag(self, ref, etag):
        etagfilename = os.path.join(self._mirror_dir, "{}.etag".format(ref))
        with utils.save_file_atomic(etagfilename) as etagfile:
            etagfile.write(etag)

    def _ensure_mirror(self, activity_name: str):
        # Downloads from the url and caches it according to its sha256sum.
        try:
            with self.tempdir() as td:
                # We do not use etag in case what we have in cache is
                # not matching ref in order to be able to recover from
                # corrupted download.
                if self.ref and not self.is_cached():
                    # Do not re-download the file if the ETag matches.
                    etag = self._get_etag(self.ref)
                else:
                    etag = None

                local_file, new_etag = self.blocking_activity(
                    _download_file, (self.__get_urlopener(), self.url, etag, td), activity_name
                )

                if local_file is None:
                    return self.ref

                # Make sure url-specific mirror dir exists.
                if not os.path.isdir(self._mirror_dir):
                    os.makedirs(self._mirror_dir)

                # Store by sha256sum
                sha256 = utils.sha256sum(local_file)
                # Even if the file already exists, move the new file over.
                # In case the old file was corrupted somehow.
                os.rename(local_file, self._get_mirror_file(sha256))

                if new_etag:
                    self._store_etag(sha256, new_etag)
                return sha256

        except urllib.error.HTTPError as e:
            if e.code == 304:
                # 304 Not Modified.
                # Because we use etag only for matching ref, currently specified ref is what
                # we would have downloaded.
                return self.ref
            raise SourceError("{}: Error mirroring {}: {}".format(self, self.url, e), temporary=True) from e

        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError, ValueError) as e:
            # Note that urllib.request.Request in the try block may throw a
            # ValueError for unknown url types, so we handle it here.
            raise SourceError("{}: Error mirroring {}: {}".format(self, self.url, e), temporary=True) from e

    def _get_mirror_file(self, sha=None):
        if sha is not None:
            return os.path.join(self._mirror_dir, sha)

        if self.__default_mirror_file is None:
            self.__default_mirror_file = os.path.join(self._mirror_dir, self.ref)

        return self.__default_mirror_file

    @classmethod
    def _reset_url_opener(cls):
        # Needed for tests, in order to cleanup the `netrc` configuration.
        cls.__urlopener = None  # pylint: disable=unused-private-member

    def __get_urlopener(self):
        if not DownloadableFileSource.__urlopener:
            try:
                netrc_config = netrc.netrc()
            except OSError:
                # If the .netrc file was not found, FileNotFoundError will be
                # raised, but OSError will be raised directly by the netrc package
                # in the case that $HOME is not set.
                #
                # This will catch both cases.
                #
                DownloadableFileSource.__urlopener = urllib.request.build_opener()
            except netrc.NetrcParseError as e:
                self.warn("{}: While reading .netrc: {}".format(self, e))
                return urllib.request.build_opener()
            else:
                netrc_pw_mgr = _NetrcPasswordManager(netrc_config)
                http_auth = urllib.request.HTTPBasicAuthHandler(netrc_pw_mgr)
                ftp_handler = _NetrcFTPOpener(netrc_config)
                DownloadableFileSource.__urlopener = urllib.request.build_opener(http_auth, ftp_handler)
        return DownloadableFileSource.__urlopener
