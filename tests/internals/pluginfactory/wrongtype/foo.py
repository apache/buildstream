# Plugins are supposed to return a subclass type
# of Source or Element, depending on plugin type.
#
# This one fails the requirement


class Foo():
    pass


def setup():
    return Foo
