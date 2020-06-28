import os
import pytest
import sys
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils.runcli import cli


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "variables"
)


###############################################################
#  Test proper loading of some default commands from plugins  #
###############################################################
@pytest.mark.parametrize("target,varname,expected", [
    ('autotools.bst', 'make-install', "make -j1 DESTDIR=\"/buildstream-install\" install"),
    ('cmake.bst', 'cmake',
     "cmake -B_builddir -H. -G\"Unix Makefiles\" -DCMAKE_INSTALL_PREFIX:PATH=\"/usr\" \\\n" +
     "-DCMAKE_INSTALL_LIBDIR:PATH=\"lib\"   "),
    ('distutils.bst', 'python-install',
     "python3 setup.py install --prefix \"/usr\" \\\n" +
     "--root \"/buildstream-install\""),
    ('makemaker.bst', 'configure', "perl Makefile.PL PREFIX=/buildstream-install/usr"),
    ('modulebuild.bst', 'configure', "perl Build.PL --prefix \"/buildstream-install/usr\""),
    ('qmake.bst', 'make-install', "make -j1 INSTALL_ROOT=\"/buildstream-install\" install"),
])
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'defaults'))
def test_defaults(cli, datafiles, tmpdir, target, varname, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, silent=True, args=[
        'show', '--deps', 'none', '--format', '%{vars}', target
    ])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars[varname] == expected


################################################################
#  Test overriding of variables to produce different commands  #
################################################################
@pytest.mark.parametrize("target,varname,expected", [
    ('autotools.bst', 'make-install', "make -j1 DESTDIR=\"/custom/install/root\" install"),
    ('cmake.bst', 'cmake',
     "cmake -B_builddir -H. -G\"Ninja\" -DCMAKE_INSTALL_PREFIX:PATH=\"/opt\" \\\n" +
     "-DCMAKE_INSTALL_LIBDIR:PATH=\"lib\"   "),
    ('distutils.bst', 'python-install',
     "python3 setup.py install --prefix \"/opt\" \\\n" +
     "--root \"/custom/install/root\""),
    ('makemaker.bst', 'configure', "perl Makefile.PL PREFIX=/custom/install/root/opt"),
    ('modulebuild.bst', 'configure', "perl Build.PL --prefix \"/custom/install/root/opt\""),
    ('qmake.bst', 'make-install', "make -j1 INSTALL_ROOT=\"/custom/install/root\" install"),
])
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'overrides'))
def test_overrides(cli, datafiles, tmpdir, target, varname, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, silent=True, args=[
        'show', '--deps', 'none', '--format', '%{vars}', target
    ])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars[varname] == expected


@pytest.mark.parametrize(
    "element,provenance",
    [
        # This test makes a reference to an undefined variable in a build command
        ("manual.bst", "manual.bst [line 5 column 6]"),
        # This test makes a reference to an undefined variable by another variable,
        # ensuring that we validate variables even when they are unused
        ("manual2.bst", "manual2.bst [line 4 column 8]"),
        # This test uses a build command to refer to some variables which ultimately
        # refer to an undefined variable, testing a more complex case.
        ("manual3.bst", "manual3.bst [line 6 column 8]"),
    ],
    ids=["build-command", "variables", "complex"],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "missing_variables"))
def test_undefined(cli, datafiles, element, provenance):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.UNRESOLVED_VARIABLE)
    assert provenance in result.stderr


@pytest.mark.parametrize(
    "element,provenances",
    [
        # Test a simple a -> b and b -> a reference
        ("simple-cyclic.bst", ["simple-cyclic.bst [line 4 column 5]", "simple-cyclic.bst [line 5 column 5]"]),
        # Test a simple a -> b and b -> a reference with some text involved
        ("cyclic.bst", ["cyclic.bst [line 5 column 10]", "cyclic.bst [line 4 column 5]"]),
        # Test an indirect circular dependency
        (
            "indirect-cyclic.bst",
            [
                "indirect-cyclic.bst [line 5 column 5]",
                "indirect-cyclic.bst [line 6 column 5]",
                "indirect-cyclic.bst [line 7 column 5]",
                "indirect-cyclic.bst [line 8 column 5]",
            ],
        ),
        # Test an indirect circular dependency
        ("self-reference.bst", ["self-reference.bst [line 4 column 5]"]),
    ],
    ids=["simple", "simple-text", "indirect", "self-reference"],
)
@pytest.mark.timeout(15, method="signal")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "cyclic_variables"))
def test_circular_reference(cli, datafiles, element, provenances):
    print_warning("Performing cyclic test, if this test times out it will exit the test sequence")
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=["build", element])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE)
    for provenance in provenances:
        assert provenance in result.stderr


def print_warning(msg):
    RED, END = "\033[91m", "\033[0m"
    print(("\n{}{}{}").format(RED, msg, END), file=sys.stderr)


# Test that variables which refer to eachother very deeply are
# still resolved correctly, this ensures that we are not relying
# on a recursive algorithm limited by stack depth.
#
@pytest.mark.parametrize(
    "maxvars", [50, 500, 5000],
)
@pytest.mark.datafiles(os.path.join(DATA_DIR, "defaults"))
def test_deep_references(cli, datafiles, maxvars):
    project = str(datafiles)

    # Generate an element with very, very many variables to resolve,
    # each which expand to the value of the previous variable.
    #
    # The bottom variable defines a test value which we check for
    # in the top variable in `bst show` output.
    #
    topvar = "var{}".format(maxvars)
    bottomvar = "var0"
    testvalue = "testvalue {}".format(maxvars)

    # Generate
    variables = {"var{}".format(idx + 1): "%{var" + str(idx) + "}" for idx in range(maxvars)}
    variables[bottomvar] = testvalue
    element = {"kind": "manual", "variables": variables}
    _yaml.dump(element, os.path.join(project, "test.bst"))

    # Run `bst show`
    result = cli.run(project=project, args=["show", "--format", "%{vars}", "test.bst"])
    result.assert_success()

    # Test results
    result_vars = _yaml.load_data(result.output)
    assert result_vars[topvar] == testvalue


@pytest.mark.datafiles(os.path.join(DATA_DIR, "partial_context"))
def test_partial_context_junctions(cli, datafiles):
    project = str(datafiles)

    result = cli.run(project=project, args=["show", "--format", "%{vars}", "test.bst"])
    result.assert_success()
    result_vars = _yaml.load_data(result.output)
    assert result_vars["eltvar"] == "/bar/foo/baz"
