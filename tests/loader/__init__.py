from buildstream._options import OptionPool


#
# This is used by the loader test modules, these should
# be removed in favor of testing the functionality via
# the CLI like in the frontend tests anyway.
#
def make_options(basedir):
    options = OptionPool(basedir)
    options.resolve()
    return options
