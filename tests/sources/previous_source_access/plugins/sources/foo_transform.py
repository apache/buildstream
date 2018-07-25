"""
foo_transform - transform "file" from previous sources into "filetransform"
===========================================================================

This is a test source plugin that looks for a file named "file" staged by
previous sources, and copies its contents to a file called "filetransform".

"""

import os
import hashlib

from buildstream import Consistency, Source, SourceError, utils


class FooTransformSource(Source):

    # We need access to previous both at track time and fetch time
    BST_REQUIRES_PREVIOUS_SOURCES_TRACK = True
    BST_REQUIRES_PREVIOUS_SOURCES_FETCH = True

    @property
    def mirror(self):
        """Directory where this source should stage its files

        """
        path = os.path.join(self.get_mirror_directory(), self.name,
                            self.ref.strip())
        os.makedirs(path, exist_ok=True)
        return path

    def configure(self, node):
        self.node_validate(node, ['ref'] + Source.COMMON_CONFIG_KEYS)
        self.ref = self.node_get_member(node, str, 'ref', None)

    def preflight(self):
        pass

    def get_unique_key(self):
        return (self.ref,)

    def get_consistency(self):
        if self.ref is None:
            return Consistency.INCONSISTENT
        # If we have a file called "filetransform", verify that its checksum
        # matches our ref. Otherwise, it resolved but not cached.
        fpath = os.path.join(self.mirror, 'filetransform')
        try:
            with open(fpath, 'rb') as f:
                if hashlib.sha256(f.read()).hexdigest() == self.ref.strip():
                    return Consistency.CACHED
        except Exception:
            pass
        return Consistency.RESOLVED

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        self.ref = node['ref'] = ref

    def track(self, previous_sources_dir):
        # Store the checksum of the file from previous source as our ref
        fpath = os.path.join(previous_sources_dir, 'file')
        with open(fpath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    def fetch(self, previous_sources_dir):
        fpath = os.path.join(previous_sources_dir, 'file')
        # Verify that the checksum of the file from previous source matches
        # our ref
        with open(fpath, 'rb') as f:
            if hashlib.sha256(f.read()).hexdigest() != self.ref.strip():
                raise SourceError("Element references do not match")

        # Copy "file" as "filetransform"
        newfpath = os.path.join(self.mirror, 'filetransform')
        utils.safe_copy(fpath, newfpath)

    def stage(self, directory):
        # Simply stage the "filetransform" file
        utils.safe_copy(os.path.join(self.mirror, 'filetransform'),
                        os.path.join(directory, 'filetransform'))


def setup():
    return FooTransformSource
