# Local imports
from . import Queue
from ..resources import ResourceType


class FormatQueue(Queue):

    action_name = "Format"
    complete_name = "Formatted"
    resources = [ResourceType.PROCESS]

    def process(self, element):
        element._format()
