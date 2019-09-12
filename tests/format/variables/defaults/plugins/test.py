from buildstream import BuildElement, SandboxFlags


# Element implementation for the 'test' kind.
class TestElement(BuildElement):
    # Supports virtual directories (required for remote execution)
    BST_VIRTUAL_DIRECTORY = True

    # Enable command batching across prepare() and assemble()
    def configure_sandbox(self, sandbox):
        super().configure_sandbox(sandbox)
        self.batch_prepare_assemble(SandboxFlags.ROOT_READ_ONLY,
                                    collect=self.get_variable('install-root'))


# Plugin entry point
def setup():
    return TestElement
