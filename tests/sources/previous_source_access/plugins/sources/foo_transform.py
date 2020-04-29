"""
foo_transform - transform "file" from previous sources into "filetransform"
===========================================================================

This is a test source plugin that looks for a file named "file" staged by
previous sources, and copies its contents to a file called "filetransform".

"""

import os
import hashlib

from buildstream import Source, SourceError, utils


class FooTransformSource(Source):
    BST_MIN_VERSION = "2.0"

    # We need access to previous both at track time and fetch time
    BST_REQUIRES_PREVIOUS_SOURCES_TRACK = True
    BST_REQUIRES_PREVIOUS_SOURCES_FETCH = True
    BST_REQUIRES_PREVIOUS_SOURCES_CACHE = True

    @property
    def mirror(self):
        """Directory where this source should stage its files

        """
        path = os.path.join(self.get_mirror_directory(), self.name, self.ref.strip())
        os.makedirs(path, exist_ok=True)
        return path

    def configure(self, node):
        node.validate_keys(["ref", *Source.COMMON_CONFIG_KEYS])
        self.ref = node.get_str("ref", None)

    def preflight(self):
        pass

    def get_unique_key(self):
        return (self.ref,)

    def is_cached(self):
        # If we have a file called "filetransform", verify that its checksum
        # matches our ref. Otherwise, it is not cached.
        fpath = os.path.join(self.mirror, "filetransform")
        try:
            with open(fpath, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() == self.ref.strip():
                    return True
        except FileNotFoundError:
            pass

        return False

    def get_ref(self):
        return self.ref

    def set_ref(self, ref, node):
        self.ref = node["ref"] = ref

    def track(self, previous_sources_dir):
        # Store the checksum of the file from previous source as our ref
        fpath = os.path.join(previous_sources_dir, "file")
        with open(fpath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def fetch(self, previous_sources_dir):
        fpath = os.path.join(previous_sources_dir, "file")
        # Verify that the checksum of the file from previous source matches
        # our ref
        with open(fpath, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != self.ref.strip():
                raise SourceError("Element references do not match")

        # Copy "file" as "filetransform"
        newfpath = os.path.join(self.mirror, "filetransform")
        utils.safe_copy(fpath, newfpath)

    def stage(self, directory):
        # Simply stage the "filetransform" file
        utils.safe_copy(os.path.join(self.mirror, "filetransform"), os.path.join(directory, "filetransform"))


def setup():
    return FooTransformSource
