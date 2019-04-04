##################################################################
#                      Private Entry Point                       #
##################################################################
#
# This allows running the cli when BuildStream is uninstalled,
# as long as BuildStream repo is in PYTHONPATH, one can run it
# with:
#
#    python3 -m buildstream [program args]
#
# This is used when we need to run BuildStream before installing,
# like when we build documentation.
#
if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    from ._frontend.cli import cli
    cli()
