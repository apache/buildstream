from buildstream import Element


class ConfigSupported(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        pass

    def configure_dependencies(self, dependencies):
        self.configs = []

        for dep in dependencies:
            if dep.config:
                dep.config.validate_keys(["enabled"])
                self.configs.append(dep)

        self.info("TEST PLUGIN FOUND {} ENABLED DEPENDENCIES".format(len(self.configs)))

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return ConfigSupported
