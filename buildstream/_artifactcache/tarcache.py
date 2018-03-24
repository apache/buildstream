#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import shutil
import tarfile
import subprocess

from .. import utils, ProgramNotFoundError
from .._exceptions import ArtifactError

from . import ArtifactCache


class TarCache(ArtifactCache):

    def __init__(self, context):

        super().__init__(context)

        self.tardir = os.path.join(context.artifactdir, 'tar')
        os.makedirs(self.tardir, exist_ok=True)

    ################################################
    #     Implementation of abstract methods       #
    ################################################
    def contains(self, element, key):
        path = os.path.join(self.tardir, _tarpath(element, key))
        return os.path.isfile(path)

    # remove()
    #
    # Implements artifactcache.remove().
    #
    def remove(self, ref):
        artifact = os.path.join(self.tardir, ref + '.tar.bz2')
        size = os.stat(artifact, follow_symlinks=False).st_size
        os.remove(artifact)
        return size

    def commit(self, element, content, keys):
        os.makedirs(os.path.join(self.tardir, element._get_project().name, element.normal_name), exist_ok=True)

        with utils._tempdir() as temp:
            for key in keys:
                ref = _tarpath(element, key)

                refdir = os.path.join(temp, key)
                shutil.copytree(content, refdir, symlinks=True)

                _Tar.archive(os.path.join(self.tardir, ref), key, temp)

    def extract(self, element, key):

        fullname = self.get_artifact_fullname(element, key)
        path = _tarpath(element, key)

        if not os.path.isfile(os.path.join(self.tardir, path)):
            raise ArtifactError("Artifact missing for {}".format(fullname))

        # If the destination already exists, the artifact has been extracted
        dest = os.path.join(self.extractdir, fullname)
        if os.path.isdir(dest):
            return dest

        os.makedirs(self.extractdir, exist_ok=True)

        with utils._tempdir(dir=self.extractdir) as tmpdir:
            _Tar.extract(os.path.join(self.tardir, path), tmpdir)

            os.makedirs(os.path.join(self.extractdir, element._get_project().name, element.normal_name),
                        exist_ok=True)
            try:
                os.rename(os.path.join(tmpdir, key), dest)
            except OSError as e:
                # With rename, it's possible to get either ENOTEMPTY or EEXIST
                # in the case that the destination path is a not empty directory.
                #
                # If rename fails with these errors, another process beat
                # us to it so just ignore.
                if e.errno not in [os.errno.ENOTEMPTY, os.errno.EEXIST]:
                    raise ArtifactError("Failed to extract artifact '{}': {}"
                                        .format(fullname, e)) from e

        return dest


# _tarpath()
#
# Generate a relative tarball path for a given element and it's cache key
#
# Args:
#    element (Element): The Element object
#    key (str): The element's cache key
#
# Returns:
#    (str): The relative path to use for storing tarballs
#
def _tarpath(element, key):
    project = element._get_project()
    return os.path.join(project.name, element.normal_name, key + '.tar.bz2')


# A helper class that contains tar archive/extract functions
class _Tar():

    # archive()
    #
    # Attempt to archive the given tarfile with the `tar` command,
    # falling back to python's `tarfile` if this fails.
    #
    # Args:
    #     location (str): The path to the tar to create
    #     content (str): The path to the content to archvive
    #     cwd (str): The cwd
    #
    # This is done since AIX tar does not support 2G+ files.
    #
    @classmethod
    def archive(cls, location, content, cwd=os.getcwd()):

        try:
            cls._archive_with_tar(location, content, cwd)
            return
        except tarfile.TarError:
            pass
        except ProgramNotFoundError:
            pass

        # If the former did not complete successfully, we try with
        # python's tar implementation (since it's hard to detect
        # specific issues with specific tar implementations - a
        # fallback).

        try:
            cls._archive_with_python(location, content, cwd)
        except tarfile.TarError as e:
            raise ArtifactError("Failed to archive {}: {}"
                                .format(location, e)) from e

    # extract()
    #
    # Attempt to extract the given tarfile with the `tar` command,
    # falling back to python's `tarfile` if this fails.
    #
    # Args:
    #     location (str): The path to the tar to extract
    #     dest (str): The destination path to extract to
    #
    # This is done since python tarfile extraction is horrendously
    # slow (2 hrs+ for base images).
    #
    @classmethod
    def extract(cls, location, dest):

        try:
            cls._extract_with_tar(location, dest)
            return
        except tarfile.TarError:
            pass
        except ProgramNotFoundError:
            pass

        try:
            cls._extract_with_python(location, dest)
        except tarfile.TarError as e:
            raise ArtifactError("Failed to extract {}: {}"
                                .format(location, e)) from e

    # _get_host_tar()
    #
    # Get the host tar command.
    #
    # Raises:
    #     ProgramNotFoundError: If the tar executable cannot be
    #                           located
    #
    @classmethod
    def _get_host_tar(cls):
        tar_cmd = None

        for potential_tar_cmd in ['gtar', 'tar']:
            try:
                tar_cmd = utils.get_host_tool(potential_tar_cmd)
                break
            except ProgramNotFoundError:
                continue

        # If we still couldn't find tar, raise the ProgramNotfounderror
        if tar_cmd is None:
            raise ProgramNotFoundError("Did not find tar in PATH: {}"
                                       .format(os.environ.get('PATH')))

        return tar_cmd

    # _archive_with_tar()
    #
    # Archive with an implementation of the `tar` command
    #
    # Args:
    #     location (str): The path to the tar to create
    #     content (str): The path to the content to archvive
    #     cwd (str): The cwd
    #
    # Raises:
    #     TarError: If an error occurs during extraction
    #     ProgramNotFoundError: If the tar executable cannot be
    #                           located
    #
    @classmethod
    def _archive_with_tar(cls, location, content, cwd):
        tar_cmd = cls._get_host_tar()

        process = subprocess.Popen(
            [tar_cmd, 'jcaf', location, content],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        _, err = process.communicate()
        if process.poll() != 0:
            # Clean up in case the command failed in a broken state
            try:
                os.remove(location)
            except FileNotFoundError:
                pass

            raise tarfile.TarError("Failed to archive '{}': {}"
                                   .format(content, err.decode('utf8')))

    # _archive_with_python()
    #
    # Archive with the python `tarfile` module
    #
    # Args:
    #     location (str): The path to the tar to create
    #     content (str): The path to the content to archvive
    #     cwd (str): The cwd
    #
    # Raises:
    #     TarError: If an error occurs during extraction
    #
    @classmethod
    def _archive_with_python(cls, location, content, cwd):
        with tarfile.open(location, mode='w:bz2') as tar:
            tar.add(os.path.join(cwd, content), arcname=content)

    # _extract_with_tar()
    #
    # Extract with an implementation of the `tar` command
    #
    # Args:
    #     location (str): The path to the tar to extract
    #     dest (str): The destination path to extract to
    #
    # Raises:
    #     TarError: If an error occurs during extraction
    #
    @classmethod
    def _extract_with_tar(cls, location, dest):
        tar_cmd = cls._get_host_tar()

        # Some tar implementations do not support '-C'
        process = subprocess.Popen(
            [tar_cmd, 'jxf', location],
            cwd=dest,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        _, err = process.communicate()
        if process.poll() != 0:
            raise tarfile.TarError("Failed to extract '{}': {}"
                                   .format(location, err.decode('utf8')))

    # _extract_with_python()
    #
    # Extract with the python `tarfile` module
    #
    # Args:
    #     location (str): The path to the tar to extract
    #     dest (str): The destination path to extract to
    #
    # Raises:
    #     TarError: If an error occurs during extraction
    #
    @classmethod
    def _extract_with_python(cls, location, dest):
        with tarfile.open(location) as tar:
            tar.extractall(path=dest)
