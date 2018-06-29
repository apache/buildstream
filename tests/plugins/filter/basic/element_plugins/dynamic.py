from buildstream import Element, Scope


# Copies files from the dependent element but inserts split-rules using dynamic data
class DynamicElement(Element):
    def configure(self, node):
        self.node_validate(node, ['split-rules'])
        self.split_rules = self.node_get_member(node, dict, 'split-rules')

    def preflight(self):
        pass

    def get_unique_key(self):
        return {'split-rules': self.split_rules}

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        with self.timed_activity("Staging artifact", silent_nested=True):
            for dep in self.dependencies(Scope.BUILD):
                dep.stage_artifact(sandbox)

        bstdata = self.get_public_data("bst")
        bstdata["split-rules"] = self.split_rules
        self.set_public_data("bst", bstdata)

        return ""


def setup():
    return DynamicElement
