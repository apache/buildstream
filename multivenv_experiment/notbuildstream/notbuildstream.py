import builtins
import sys
import contextlib

import click

import pluginbase


# TODO: Make this work instead by overriding everything except BuildStream and
# the standard library.
@contextlib.contextmanager
def import_override(*override_modules):
    def myimport(name, globals_=None, locals_=None, fromlist=None, level=None):
        # XXX: In the case of 'from . import A, B' we run into trouble if
        # we remap the name. We should fully understand why and what
        # guarantees there are before considering using any of this.
        #
        # When this is the case, it seems that 'fromlist' will be an empty
        # list. Again, we need to know the guarantees here.
        #
        if fromlist != []:
            for m in override_modules:
                if name.startswith(m):
                    name = "notbuildstream.plugins." + name
        return builtins_import(name, globals_, locals_, fromlist, level)

    builtins_import = builtins.__import__
    try:
        builtins.__import__ = myimport
        yield
    finally:
        builtins.__import__ = builtins_import


@click.command("notbuildstream")
@click.argument(
    "plugin_venvs",
    nargs=-1,
    metavar="PATH",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def cli(plugin_venvs):

    pbase = pluginbase.PluginBase(package="notbuildstream.plugins")
    psource_list = []

    for venv in plugin_venvs:
        print(f"venv: {venv}")

        # XXX: We should determine this path using some standard mechanism.
        search_path = [venv + "/lib/python3.7/site-packages", venv]

        psource = pbase.make_plugin_source(searchpath=search_path, identifier=venv)
        psource_list.append(psource)

        with import_override("jinja2", "markupsafe"):
            with psource:
                # TODO: use entrypoints and lookup plugins with pkgconfig.
                plugin = psource.load_plugin("bstplugin")
                element = plugin.Element("a")
                jinja2 = psource.load_plugin("jinja2")
                print(f"main: jinja2: {jinja2}")
                print(f"main: jinja2.__version__: {jinja2.__version__}")
                print(f"main: jinja2.__file__: {jinja2.__file__}")
                print(
                    "main: Has evalcontextfilter:",
                    getattr(jinja2, "evalcontextfilter", None),
                )
                print()


if __name__ == "__main__":
    sys.exit(cli())
