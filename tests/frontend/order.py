# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest
from buildstream.testing import create_repo
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# create_element()
#
# Args:
#    project (str): The project directory where testing is happening
#    name (str): The element name to create
#    dependencies (list): The list of dependencies to dump into YAML format
#
# Returns:
#    (Repo): The corresponding git repository created for the element
def create_element(project, name, dependencies):
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    repo = create_repo('git', project, "{}-repo".format(name))
    ref = repo.create(dev_files_path)

    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ],
        'depends': dependencies
    }
    _yaml.roundtrip_dump(element, os.path.join(element_path, name))

    return repo


# This tests a variety of scenarios and checks that the order in
# which things are processed remains stable.
#
# This is especially important in order to ensure that our
# depth sorting and optimization of which elements should be
# processed first is doing it's job right, and that we are
# promoting elements to the build queue as soon as possible
#
# Parameters:
#    targets (target elements): The targets to invoke bst with
#    template (dict): The project template dictionary, for create_element()
#    expected (list): A list of element names in the expected order
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("target,template,expected", [
    # First simple test
    ('3.bst', {
        '0.bst': ['1.bst'],
        '1.bst': [],
        '2.bst': ['0.bst'],
        '3.bst': ['0.bst', '1.bst', '2.bst']
    }, ['1.bst', '0.bst', '2.bst', '3.bst']),

    # A more complicated test with build of build dependencies
    ('target.bst', {
        'a.bst': [],
        'base.bst': [],
        'timezones.bst': [],
        'middleware.bst': [{'filename': 'base.bst', 'type': 'build'}],
        'app.bst': [{'filename': 'middleware.bst', 'type': 'build'}],
        'target.bst': ['a.bst', 'base.bst', 'middleware.bst', 'app.bst', 'timezones.bst']
    }, ['base.bst', 'middleware.bst', 'a.bst', 'app.bst', 'timezones.bst', 'target.bst']),
])
@pytest.mark.parametrize("operation", [('show'), ('fetch'), ('build')])
def test_order(cli, datafiles, operation, target, template, expected):
    project = str(datafiles)

    # Configure to only allow one fetcher at a time, make it easy to
    # determine what is being planned in what order.
    cli.configure({
        'scheduler': {
            'fetchers': 1,
            'builders': 1
        }
    })

    # Build the project from the template, make import elements
    # all with the same repo
    #
    for element, dependencies in template.items():
        create_element(project, element, dependencies)

    # Run test and collect results
    if operation == 'show':
        result = cli.run(args=['show', '--deps', 'plan', '--format', '%{name}', target], project=project, silent=True)
        result.assert_success()
        results = result.output.splitlines()
    else:
        if operation == 'fetch':
            result = cli.run(args=['source', 'fetch', target], project=project, silent=True)
        else:
            result = cli.run(args=[operation, target], project=project, silent=True)
        result.assert_success()
        results = result.get_start_order(operation)

    # Assert the order
    print("Expected order: {}".format(expected))
    print("Observed result order: {}".format(results))
    assert results == expected
