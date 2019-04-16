import sys

import jinja2


class Element:
    def __init__(self, bst_context):
        print("Beta")
        print(f"jinja2.__version__: {jinja2.__version__}")
        print("jinja2.evalcontextfilter:", getattr(jinja2, "evalcontextfilter", None))
