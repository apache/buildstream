from buildstream import Element, FastEnum


class AnimalEnum(FastEnum):
    PONY = "pony"
    HORSY = "horsy"
    ZEBRY = "zebry"


class Config(Element):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        self.animal = node.get_enum("animal", AnimalEnum)
        self.sleepy = node.get_bool("sleepy")

    def preflight(self):
        pass

    def get_unique_key(self):
        return {}


# Plugin entry point
def setup():
    return Config
