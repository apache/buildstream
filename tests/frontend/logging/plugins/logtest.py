from buildstream import Element


class LogTest(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        # Here we stage the artifacts of dependencies individually without
        # using a timed activity or suppressing the logging.
        #
        # This allows us to test the logging behavior when log lines are
        # triggered by an element which is not the element being processed.
        #
        #   * The master build log should show the element name and cache key
        #     of the task element, i.e. the element currently being built, not
        #     the element issuing the message.
        #
        #   * In the individual task log, we expect to see the name and cache
        #     key of the element issuing messages, since the entire log file
        #     is contextual to the task, it makes more sense to provide the
        #     full context of the element issuing the log in this case.
        #
        for dep in self.dependencies():
            dep.stage_artifact(sandbox)

    def assemble(self, sandbox):
        return "/"


# Plugin entry point
def setup():
    return LogTest
