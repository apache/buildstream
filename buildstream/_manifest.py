#
#  Copyright (C) 2018 Codethink Limited
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
#        Josh Smith <josh.smith@codethink.co.uk>

from ruamel import yaml
from . import __version__ as bst_version
from . import _yaml
from ._message import MessageType, Message

# generate():
#
# Generates a manfiest file from the collection of elements.
#
# Args:
#    context (Context): Application context
#    elements (list of Element): Collection of elements to build the manifest from
#    build_start_datetime (datetime): The start of the build assosciated with this manifest
#    manifest_path (str): Absolute path to write the manifest file to.
#
def generate(context, elements, build_start_datetime, manifest_path):
    with context.timed_activity("Building Manifest"):
        manifest = _build(elements, build_start_datetime)

    _yaml.dump(manifest, manifest_path)
    context.message(Message(None, MessageType.STATUS,
                            "Manifest saved to {}".format(manifest_path)))

# _build():
#
# Builds a manifest (dictionary) using the provided elements to be stored.
#
# Args:
#    elements (list of Element): Collection of elements to build the manifest from
#    build_start_datetime (datetime): The start of the build assosciated with this manifest
#
# Returns:
#    (CommentedMap): A dictionary containing the entire
#                    manifest produced from the provided elements.
#
def _build(elements, build_start_datetime):
    manifest = yaml.comments.CommentedMap()

    # Add BuildStream Version
    manifest['BuildStream_Version'] = "{}".format(bst_version)
    # Add Build Date
    manifest['Build_Date'] = build_start_datetime.isoformat()
    manifest['Elements'] = yaml.comments.CommentedMap()

    # Sort elements
    elements = sorted(elements, key=lambda e: e.normal_name)

    # Add Elements
    for elem in elements:
        manifest['Elements'][elem.normal_name] = _build_element(elem)

    return manifest

# _build_element():
#
# Builds a manifest segment for an individual element.
#
# Args:
#    element (Element): Element to extract information from
#
# Returns:
#    (CommentedMap): A dictionary containing the information
#                    extracted from the provided element
#
def _build_element(element):
    element_dict = yaml.comments.CommentedMap()
    sources = yaml.comments.CommentedMap()
    # Add Cache Key
    cache_key = element._get_cache_key()
    if cache_key:
        element_dict["Cache_Key"] = cache_key

    # Add sources
    for source in element.sources():
        src = _build_source(source)
        if src:
            source_desc = "{}({})".format(source._get_element_index(), type(source).__name__)
            sources[source_desc] = src
    if sources:
        element_dict['Sources'] = sources


    return element_dict

# _build_source():
#
# Builds a manifest segment for an individual source.
#
# Args:
#    source (Source): Source to extract information from
#
# Returns:
#    (CommentedMap): A dictionary containing the information
#                    extracted from the provided source
#
def _build_source(source):
    src = yaml.comments.CommentedMap()
    if hasattr(source, "url") and source.url:
        src["url"] = source.url
    if hasattr(source, "ref") and source.ref:
        src["ref"] = source.ref
    if hasattr(source, "path") and source.path:
        src["path"] = source.path

    return src if src else None
