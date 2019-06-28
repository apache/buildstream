"""A base abstract class for source implementations which download a file"""

import os
import urllib.request
import urllib.error
import contextlib
import shutil
import netrc

from buildstream import Source, SourceError, Consistency
from buildstream import utils


class _NetrcFTPOpener(urllib.request.FTPHandler):

    def __init__(self, netrc_config):
        self.netrc = netrc_config

    def _split(self, netloc):
        userpass, hostport = urllib.parse.splituser(netloc)
        host, port = urllib.parse.splitport(hostport)
        if userpass:
            user, passwd = urllib.parse.splitpasswd(userpass)
        else:
            user = None
            passwd = None
        return host, port, user, passwd

    def _unsplit(self, host, port, user, passwd):
        if port:
            host = '{}:{}'.format(host, port)
        if user:
            if passwd:
                user = '{}:{}'.format(user, passwd)
            host = '{}@{}'.format(user, host)

        return host

    def ftp_open(self, req):
        host, port, user, passwd = self._split(req.host)

        if user is None and self.netrc:
            entry = self.netrc.authenticators(host)
            if entry:
                user, _, passwd = entry

        req.host = self._unsplit(host, port, user, passwd)

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


class DownloadableFileSource(Source):
    # pylint: disable=attribute-defined-outside-init

    COMMON_CONFIG_KEYS = Source.COMMON_CONFIG_KEYS + ['url', 'ref', 'etag', 'path']

    __urlopener = None

    def configure(self, node):
        self.original_url = self.node_get_member(node, str, 'url', None)
        self.original_path = self.node_get_member(node, str, 'path', None)
        self.ref = self.node_get_member(node, str, 'ref', None)
        self._warn_deprecated_etag(node)

        # XXX: Looks like this should be in preflight but child classes are not calling super()
        if self.original_url is None and self.original_path is None:
            raise SourceError("Please specify either a 'path' or a 'url'.")
        if self.original_url is not None and self.original_path is not None:
            self.url_provenance = self.node_provenance(node, member_name='url')
            self.path_provenance = self.node_provenance(node, member_name='path')

            raise SourceError("You cannot specify both 'path' ({}) and 'url' ({})"
                              .format(self.path_provenance, self.url_provenance))

        # If using path, use appropriate checks
        if self.original_url is None:
            self.path = self.node_get_project_path(node, 'path')
            self.fullpath = os.path.join(self.get_project_directory(), self.path)
            self.sha = unique_key(self.fullpath)

        # If using url, do checks
        if self.original_path is None:
            self.url = self.translate_url(self.original_url)

    def preflight(self):
        return

    def get_unique_key(self):
        if self.original_url is None:
            return [os.path.basename(self.original_path), self.sha]

        return [self.original_url, self.ref]

    def get_consistency(self):
        if self.original_url is None:
            return Consistency.CACHED

        if self.ref is None:
            return Consistency.INCONSISTENT

        if os.path.isfile(self._get_mirror_file()):
            return Consistency.CACHED

        else:
            return Consistency.RESOLVED

    def load_ref(self, node):
        if self.original_url is None:
            return

        self.ref = self.node_get_member(node, str, 'ref', None)
        self._warn_deprecated_etag(node)

    def get_ref(self):
        if self.original_url is None:
            return None

        return self.ref

    def set_ref(self, ref, node):
        if self.original_url is None:
            return

        node['ref'] = self.ref = ref

    def track(self):
        # there is no 'track' field in the source to determine what/whether
        # or not to update refs, because tracking a ref is always a conscious
        # decision by the user.
        if self.original_url is None:
            return

        with self.timed_activity("Tracking {}".format(self.url),
                                 silent_nested=True):
            new_ref = self._ensure_mirror()

            if self.ref != new_ref:
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
        if self.original_url is None:
            return

        if os.path.isfile(self._get_mirror_file()):
            return  # pragma: nocover

        # Download the file, raise hell if the sha256sums don't match,
        # and mirror the file otherwise.
        with self.timed_activity("Fetching {}".format(self.url), silent_nested=True):
            sha256 = self._ensure_mirror()
            if sha256 != self.ref:
                raise SourceError("File downloaded from {} has sha256sum '{}', not '{}'!"
                                  .format(self.url, sha256, self.ref))

    def _get_local_path(self):
        return self.path

    def _warn_deprecated_etag(self, node):
        etag = self.node_get_member(node, str, 'etag', None)
        if etag:
            provenance = self.node_provenance(node, member_name='etag')
            self.warn('{} "etag" is deprecated and ignored.'.format(provenance))

    def _get_etag(self, ref):
        etagfilename = os.path.join(self._get_mirror_dir(), '{}.etag'.format(ref))
        if os.path.exists(etagfilename):
            with open(etagfilename, 'r') as etagfile:
                return etagfile.read()

        return None

    def _store_etag(self, ref, etag):
        etagfilename = os.path.join(self._get_mirror_dir(), '{}.etag'.format(ref))
        with utils.save_file_atomic(etagfilename) as etagfile:
            etagfile.write(etag)

    def _ensure_mirror(self):
        # Downloads from the url and caches it according to its sha256sum.
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

                opener = self.__get_urlopener()
                with contextlib.closing(opener.open(request)) as response:
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
                              .format(self, self.url, e), temporary=True) from e

        except (urllib.error.URLError, urllib.error.ContentTooShortError, OSError, ValueError) as e:
            # Note that urllib.request.Request in the try block may throw a
            # ValueError for unknown url types, so we handle it here.
            raise SourceError("{}: Error mirroring {}: {}"
                              .format(self, self.url, e), temporary=True) from e

    def _get_mirror_dir(self):
        directory_name = utils.url_directory_name(self.original_url)
        return os.path.join(self.get_mirror_directory(),
                            directory_name)

    def _get_mirror_file(self, sha=None):
        return os.path.join(self._get_mirror_dir(), sha or self.ref)

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
                self.warn('{}: While reading .netrc: {}'.format(self, e))
                return urllib.request.build_opener()
            else:
                netrc_pw_mgr = _NetrcPasswordManager(netrc_config)
                http_auth = urllib.request.HTTPBasicAuthHandler(netrc_pw_mgr)
                ftp_handler = _NetrcFTPOpener(netrc_config)
                DownloadableFileSource.__urlopener = urllib.request.build_opener(http_auth, ftp_handler)
        return DownloadableFileSource.__urlopener


# Create a unique key for a file
def unique_key(filename):

    # Return some hard coded things for files which
    # have no content to calculate a key for
    if os.path.islink(filename):
        # For a symbolic link, use the link target as its unique identifier
        return os.readlink(filename)
    elif os.path.isdir(filename):
        return "0"

    return utils.sha256sum(filename)
