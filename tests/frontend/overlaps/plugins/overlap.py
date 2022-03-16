from buildstream import Element, OverlapAction


# A testing element to test the behavior of staging overlapping files
#
class OverlapElement(Element):

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        node.validate_keys(["action"])
        self.overlap_action = node.get_enum("action", OverlapAction)

    def configure_dependencies(self, dependencies):
        self.layout = {}

        for dep in dependencies:
            location = "/"
            if dep.config:
                dep.config.validate_keys(["location"])
                location = dep.config.get_str("location")
            try:
                element_list = self.layout[location]
            except KeyError:
                element_list = []
                self.layout[location] = element_list

            element_list.append((dep.element, dep.path))

    def preflight(self):
        pass

    def get_unique_key(self):
        sorted_locations = sorted(self.layout)
        layout_key = {
            location: [dependency_path for _, dependency_path in self.layout[location]]
            for location in sorted_locations
        }
        return {"action": str(self.overlap_action), "layout": layout_key}

    def configure_sandbox(self, sandbox):
        for location in self.layout:
            sandbox.mark_directory(location)

    def stage(self, sandbox):
        sorted_locations = sorted(self.layout)
        for location in sorted_locations:
            element_list = [element for element, _ in self.layout[location]]
            self.stage_dependency_artifacts(sandbox, element_list, path=location, action=self.overlap_action)

    def assemble(self, sandbox):
        return "/"


def setup():
    return OverlapElement
