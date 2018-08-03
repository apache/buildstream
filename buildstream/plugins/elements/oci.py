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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Chandan singh <csingh43@bloomberg.net>

"""
oci - Generate OCI Image
========================
Generate OCI image from its dependencies.

This element is normally used near the end of a pipeline to prepare an OCI
image that can be used for later deployment.

.. note::

   The ``oci`` element is available since :ref:`format version XX <project_format_version>`

Here is the default configuration for the ``oci`` element in full:
  .. literalinclude:: ../../../buildstream/plugins/elements/oci.yaml
     :language: yaml
"""

import gzip
import hashlib
import json
import os
import shutil
import tarfile

from buildstream import Element, Scope, utils

OCIIMAGE_SPEC_VERSION = '1.0.0'


################
# Helper classes
################

class Blob():

    size = None
    digest = None

    def __init__(self, basedir):
        self.basedir = basedir
        # FIXME consider supporting other hashing algorithms
        self._algorithm = hashlib.sha256
        self._algorithm_name = 'sha256'

    @property
    def path(self):
        blobs_dir = os.path.join(self.basedir, 'blobs', self._algorithm_name)
        os.makedirs(blobs_dir, exist_ok=True)
        return os.path.join(blobs_dir, self.digest)

    @property
    def digest_str(self):
        return '{}:{}'.format(self._algorithm_name, self.digest)


class RootfsBlob(Blob):

    diff_id = None

    def __init__(self, basedir, inputdir):
        super().__init__(basedir)
        self.inputdir = inputdir

        # Create uncompressed tar archive and calculate diff id
        with tarfile.TarFile(name='files.tar', mode='w') as tar:
            for f in os.listdir(inputdir):
                tar.add(os.path.join(inputdir, f), arcname=f)
        with open('files.tar', 'rb') as f:
            self.diff_id = self._algorithm(f.read()).hexdigest()

        # Now compress the tar archive and calculate layer data
        with open('files.tar', 'rb') as raw_archive:
            with gzip.open('files.tar.gz', 'w') as compressed_archive:
                compressed_archive.write(raw_archive.read())

        with open('files.tar.gz', 'rb') as f:
            self.digest = self._algorithm(f.read()).hexdigest()
        self.size = os.path.getsize('files.tar.gz')

        # Move the compressed tar archive into correct directory and clean up
        shutil.move('files.tar.gz', self.path)
        os.remove('files.tar')

    @property
    def diff_id_str(self):
        return '{}:{}'.format(self._algorithm_name, self.diff_id)


class StringBlob(Blob):

    def __init__(self, basedir, contents):
        super().__init__(basedir)
        self.contents = contents = contents.encode()
        self.size = len(contents)
        self.digest = self._algorithm(contents).hexdigest()

        # Write the blob
        with utils.save_file_atomic(self.path, 'wb') as f:
            f.write(contents)


###################
# OCI Image Element
###################

class OCIImageElement(Element):

    # The oci element's output is its dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    BST_STRICT_REBUILD = True

    # OCI artifacts must never have indirect dependencies,
    # so runtime dependencies are forbidden.
    BST_FORBID_RDEPENDS = True

    # This element ignores sources, so we should forbid them from being
    # added, to reduce the potential for confusion
    BST_FORBID_SOURCES = True

    def configure(self, node):
        # We don't need anything, yet...
        self.node_validate(node, [])

    def preflight(self):
        # All good!
        pass

    def get_unique_key(self):
        # All good! We don't need to rebuild if our dependencies haven't
        # changed
        return 1

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        basedir = sandbox.get_directory()
        inputdir = os.path.join(basedir, 'input')
        outputdir = os.path.join(basedir, 'output')
        os.makedirs(inputdir, exist_ok=True)
        os.makedirs(outputdir, exist_ok=True)

        # Stage deps in the sandbox root
        with self.timed_activity("Staging dependencies", silent_nested=True):
            self.stage_dependency_artifacts(sandbox, Scope.BUILD, path='/input')

        with self.timed_activity("Creating OCI image bundle", silent_nested=True):
            # Generate oci-layout
            with utils.save_file_atomic(os.path.join(outputdir, 'oci-layout'), 'w') as f:
                f.write(json.dumps(self._oci_layout()))

            # Generate blobs
            # 1. rootfs
            rootfs = RootfsBlob(outputdir, inputdir)
            # 2. config
            config_str = json.dumps(self._config(rootfs))
            config = StringBlob(outputdir, config_str)
            # 3. manifest
            manifest_str = json.dumps(self._manifest(config, rootfs))
            manifest = StringBlob(outputdir, manifest_str)

            # Generate index.json
            with utils.save_file_atomic(os.path.join(outputdir, 'index.json'), 'w') as f:
                f.write(json.dumps(self._image_index(manifest)))

        return '/output'

    def _image_index(self, manifest):
        index = {
            'schemaVersion': 2,
            'manifests': [{
                'mediaType': 'application/vnd.oci.image.manifest.v1+json',
                'size': manifest.size,
                'digest': manifest.digest_str
            }],
        }
        if self._annotations():
            index['annotations'] = self._annotations()
        return index

    def _oci_layout(self):
        return {
            'imageLayoutVersion': OCIIMAGE_SPEC_VERSION,
        }

    def _manifest(self, config, rootfs):
        return {
            'schemaVersion': 2,
            'config': {
                'mediaType': 'application/vnd.oci.image.config.v1+json',
                'digest': config.digest_str,
                'size': config.size
            },
            'layers': [{
                'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip',
                'digest': rootfs.digest_str,
                'size': rootfs.size
            }]
        }

    def _annotations(self):
        return []

    def _config(self, rootfs):
        return {
            'architecture': 'amd64',
            'os': 'linux',
            'rootfs': {
                'type': 'layers',
                'diff_ids': [rootfs.diff_id_str]
            }
        }


def setup():
    return OCIImageElement
