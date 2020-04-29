# A plugin's setup symbol is supposed to be a function
# which returns the plugin type, which should be a subclass
# of Source or Element depending on the plugin type.
#
# This plugin's setup function returns a different kind
# of type.


class Pony:
    def __init__(self):
        self.pony = 12


def setup():
    return Pony
