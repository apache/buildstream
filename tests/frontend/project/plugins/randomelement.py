import os

from buildstream import Element


class RandomElement(Element):

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        pass

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        rootdir = sandbox.get_virtual_directory()
        outputdir = rootdir.open_directory("output", create=True)

        # Generate non-reproducible output
        with outputdir.open_file("random", mode="wb") as f:
            f.write(os.urandom(64))

        return "/output"


def setup():
    return RandomElement
