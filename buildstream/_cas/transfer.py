#
#  Copyright (C) 2017-2018 Codethink Limited
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
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>

from ..utils import _message_digest


def cas_directory_download(caslocal, casremote, root_digest, excluded_subdirs):
    for blob_digest in casremote.yield_directory_digests(
            root_digest, excluded_subdirs=excluded_subdirs):
        if caslocal.check_blob(blob_digest):
            continue
        casremote.request_blob(blob_digest)
        for blob_file in casremote.get_blobs():
            caslocal.add_object(path=blob_file.name, link_directly=True)

    # Request final CAS batch
    for blob_file in casremote.get_blobs(complete_batch=True):
        caslocal.add_object(path=blob_file.name, link_directly=True)


def cas_tree_download(caslocal, casremote, tree_digest):
    tree = casremote.get_tree_blob(tree_digest)
    for blob_digest in casremote.yield_tree_digests(tree):
        if caslocal.check_blob(blob_digest):
            continue
        casremote.request_blob(blob_digest)
        for blob_file in casremote.get_blobs():
            caslocal.add_object(path=blob_file.name, link_directly=True)

    # Get the last batch
    for blob_file in casremote.get_blobs(complete_batch=True):
        caslocal.add_object(path=blob_file.name, link_directly=True)

    # get root digest from tree and return that
    return _message_digest(tree.root.SerializeToString())
