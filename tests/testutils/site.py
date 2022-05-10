# This function is used for pytest skipif() expressions.
#
# Tests which require our plugins in tests/plugins/pip-samples need
# to check if these plugins are installed, they are only guaranteed
# to be installed when running tox, but not when using pytest directly
# to test that BuildStream works when integrated in your system.
#
def pip_sample_packages():
    import pkg_resources

    required = {"sample-plugins"}
    installed = {pkg.key for pkg in pkg_resources.working_set}  # pylint: disable=not-an-iterable
    missing = required - installed

    if missing:
        return False

    return True


SAMPLE_PACKAGES_SKIP_REASON = """
The sample plugins package used to test pip plugin origins is not installed.

This is usually tested automatically with `tox`, if you are running
`pytest` directly then you can install these plugins directly using pip.

The plugins are located in the tests/plugins/sample-plugins directory
of your BuildStream checkout.
"""
