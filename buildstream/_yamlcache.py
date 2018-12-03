#
#  Copyright 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

import os
import pickle
import hashlib
import io

import sys

from contextlib import contextmanager
from collections import namedtuple

from ._context import Context
from . import _yaml


YAML_CACHE_FILENAME = "yaml_cache.pickle"


# YamlCache()
#
# A cache that wraps around the loading of yaml in projects.
#
# The recommended way to use a YamlCache is:
#   with YamlCache.open(context) as yamlcache:
#     # Load all the yaml
#     ...
#
# Args:
#    context (Context): The invocation Context
#
class YamlCache():

    def __init__(self, context):
        self._project_caches = {}
        self._context = context

    ##################
    # Public Methods #
    ##################

    # is_cached():
    #
    # Checks whether a file is cached.
    #
    # Args:
    #    project (Project): The project this file is in.
    #    filepath (str): The path to the file, *relative to the project's directory*.
    #
    # Returns:
    #    (bool): Whether the file is cached.
    def is_cached(self, project, filepath):
        cache_path = self._get_filepath(project, filepath)
        project_name = self.get_project_name(project)
        try:
            project_cache = self._project_caches[project_name]
            if cache_path in project_cache.elements:
                return True
        except KeyError:
            pass
        return False

    # open():
    #
    # Return an instance of the YamlCache which writes to disk when it leaves scope.
    #
    # Args:
    #    context (Context): The context.
    #    cachefile (str): The path to the cache file.
    #
    # Returns:
    #    (YamlCache): A YamlCache.
    @staticmethod
    @contextmanager
    def open(context, cachefile):
        # Try to load from disk first
        cache = None
        if os.path.exists(cachefile):
            try:
                with open(cachefile, "rb") as f:
                    cache = BstUnpickler(f, context).load()
            except EOFError:
                # The file was empty
                pass
            except pickle.UnpicklingError as e:
                sys.stderr.write("Failed to load YamlCache, {}\n".format(e))

        # Failed to load from disk, create a new one
        if not cache:
            cache = YamlCache(context)

        yield cache

        cache._write(cachefile)

    # get_cache_file():
    #
    # Retrieves a path to the yaml cache file.
    #
    # Returns:
    #   (str): The path to the cache file
    @staticmethod
    def get_cache_file(top_dir):
        return os.path.join(top_dir, ".bst", YAML_CACHE_FILENAME)

    # get():
    #
    # Gets a parsed file from the cache.
    #
    # Args:
    #    project (Project) or None: The project this file is in, if it exists.
    #    filepath (str): The absolute path to the file.
    #    contents (str): The contents of the file to be cached
    #    copy_tree (bool): Whether the data should make a copy when it's being generated
    #                      (i.e. exactly as when called in yaml)
    #
    # Returns:
    #    (decorated dict): The parsed yaml from the cache, or None if the file isn't in the cache.
    #    (str):            The key used to look up the parsed yaml in the cache
    def get(self, project, filepath, contents, copy_tree):
        key = self._calculate_key(contents, copy_tree)
        data = self._get(project, filepath, key)
        return data, key

    # put():
    #
    # Puts a parsed file into the cache.
    #
    # Args:
    #    project (Project): The project this file is in.
    #    filepath (str): The path to the file.
    #    contents (str): The contents of the file that has been cached
    #    copy_tree (bool): Whether the data should make a copy when it's being generated
    #                      (i.e. exactly as when called in yaml)
    #    value (decorated dict): The data to put into the cache.
    def put(self, project, filepath, contents, copy_tree, value):
        key = self._calculate_key(contents, copy_tree)
        self.put_from_key(project, filepath, key, value)

    # put_from_key():
    #
    # Put a parsed file into the cache when given a key.
    #
    # Args:
    #    project (Project): The project this file is in.
    #    filepath (str): The path to the file.
    #    key (str): The key to the file within the cache. Typically, this is the
    #               value of `calculate_key()` with the file's unparsed contents
    #               and any relevant metadata passed in.
    #    value (decorated dict): The data to put into the cache.
    def put_from_key(self, project, filepath, key, value):
        cache_path = self._get_filepath(project, filepath)
        project_name = self.get_project_name(project)
        try:
            project_cache = self._project_caches[project_name]
        except KeyError:
            project_cache = self._project_caches[project_name] = CachedProject({})

        project_cache.elements[cache_path] = CachedYaml(key, value)

    ###################
    # Private Methods #
    ###################

    # Writes the yaml cache to the specified path.
    #
    # Args:
    #    path (str): The path to the cache file.
    def _write(self, path):
        parent_dir = os.path.dirname(path)
        os.makedirs(parent_dir, exist_ok=True)
        with open(path, "wb") as f:
            BstPickler(f).dump(self)

    # _get_filepath():
    #
    # Returns a file path relative to a project if passed, or the original path if
    # the project is None
    #
    # Args:
    #    project (Project) or None: The project the filepath exists within
    #    full_path (str): The path that the returned path is based on
    #
    # Returns:
    #    (str): The path to the file, relative to a project if it exists
    def _get_filepath(self, project, full_path):
        if project:
            assert full_path.startswith(project.directory)
            filepath = os.path.relpath(full_path, project.directory)
        else:
            filepath = full_path
        return filepath

    # _calculate_key():
    #
    # Calculates a key for putting into the cache.
    #
    # Args:
    #    (basic object)... : Any number of strictly-ordered basic objects
    #
    # Returns:
    #   (str): A key made out of every arg passed in
    @staticmethod
    def _calculate_key(*args):
        string = pickle.dumps(args)
        return hashlib.sha1(string).hexdigest()

    # _get():
    #
    # Gets a parsed file from the cache when given a key.
    #
    # Args:
    #    project (Project): The project this file is in.
    #    filepath (str): The path to the file.
    #    key (str): The key to the file within the cache. Typically, this is the
    #               value of `calculate_key()` with the file's unparsed contents
    #               and any relevant metadata passed in.
    #
    # Returns:
    #    (decorated dict): The parsed yaml from the cache, or None if the file isn't in the cache.
    def _get(self, project, filepath, key):
        cache_path = self._get_filepath(project, filepath)
        project_name = self.get_project_name(project)
        try:
            project_cache = self._project_caches[project_name]
            try:
                cachedyaml = project_cache.elements[cache_path]
                if cachedyaml._key == key:
                    # We've unpickled the YamlCache, but not the specific file
                    if cachedyaml._contents is None:
                        cachedyaml._contents = BstUnpickler.loads(cachedyaml._pickled_contents, self._context)
                    return cachedyaml._contents
            except KeyError:
                pass
        except KeyError:
            pass
        return None

    # get_project_name():
    #
    # Gets a name appropriate for Project. Projects must use their junction's
    # name if present, otherwise elements with the same contents under the
    # same path with identically-named projects are considered the same yaml
    # object, despite existing in different Projects.
    #
    # Args:
    #    project (Project): The project this file is in, or None.
    #
    # Returns:
    #    (str): The project's junction's name if present, the project's name,
    #           or an empty string if there is no project
    @staticmethod
    def get_project_name(project):
        if project:
            if project.junction:
                project_name = project.junction.name
            else:
                project_name = project.name
        else:
            project_name = ""
        return project_name


CachedProject = namedtuple('CachedProject', ['elements'])


class CachedYaml():
    def __init__(self, key, contents):
        self._key = key
        self.set_contents(contents)

    # Sets the contents of the CachedYaml.
    #
    # Args:
    #    contents (provenanced dict): The contents to put in the cache.
    #
    def set_contents(self, contents):
        self._contents = contents
        self._pickled_contents = BstPickler.dumps(contents)

    # Pickling helper method, prevents 'contents' from being serialised
    def __getstate__(self):
        data = self.__dict__.copy()
        data['_contents'] = None
        return data


# In _yaml.load, we have a ProvenanceFile that stores the project the file
# came from. Projects can't be pickled, but it's always going to be the same
# project between invocations (unless the entire project is moved but the
# file stayed in the same place)
class BstPickler(pickle.Pickler):
    def persistent_id(self, obj):
        if isinstance(obj, _yaml.ProvenanceFile):
            if obj.project:
                # ProvenanceFile's project object cannot be stored as it is.
                project_tag = YamlCache.get_project_name(obj.project)
                # ProvenanceFile's filename must be stored relative to the
                # project, as the project dir may move.
                name = os.path.relpath(obj.name, obj.project.directory)
            else:
                project_tag = None
                name = obj.name
            return ("ProvenanceFile", name, obj.shortname, project_tag)
        elif isinstance(obj, Context):
            return ("Context",)
        else:
            return None

    @staticmethod
    def dumps(obj):
        stream = io.BytesIO()
        BstPickler(stream).dump(obj)
        stream.seek(0)
        return stream.read()


class BstUnpickler(pickle.Unpickler):
    def __init__(self, file, context):
        super().__init__(file)
        self._context = context

    def persistent_load(self, pid):
        if pid[0] == "ProvenanceFile":
            _, tagged_name, shortname, project_tag = pid

            if project_tag is not None:
                for p in self._context.get_projects():
                    if YamlCache.get_project_name(p) == project_tag:
                        project = p
                        break

                name = os.path.join(project.directory, tagged_name)

                if not project:
                    projects = [YamlCache.get_project_name(p) for p in self._context.get_projects()]
                    raise pickle.UnpicklingError("No project with name {} found in {}"
                                                 .format(project_tag, projects))
            else:
                project = None
                name = tagged_name

            return _yaml.ProvenanceFile(name, shortname, project)
        elif pid[0] == "Context":
            return self._context
        else:
            raise pickle.UnpicklingError("Unsupported persistent object, {}".format(pid))

    @staticmethod
    def loads(text, context):
        stream = io.BytesIO()
        stream.write(bytes(text))
        stream.seek(0)
        return BstUnpickler(stream, context).load()
