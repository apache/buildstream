import os
import pytest

from tests.testutils import cli_integration as cli
from tests.testutils.site import IS_LINUX


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_fmt_single(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'fmt/bad-format.bst'
    good_element = 'fmt/good-format.bst'

    with open(os.path.join(project, 'elements', good_element)) as element:
        good = element.readlines()

    res = cli.run(project=project, args=['fmt', element_name])
    assert res.exit_code == 0

    with open(os.path.join(project, 'elements', element_name)) as element:
        final = element.readlines()

    # Have to test only the last line, rather than full file because of #767
    assert final[-1] == good[-1]


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_fmt_all(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    check_elements = ['fmt/bad-format.bst', 'fmt/except.bst']
    target = 'fmt/stack.bst'

    initial_lines = []
    for e in check_elements:
        with open(os.path.join(project, 'elements', e)) as element:
            initial_lines.append(element.readlines()[-1])

    with open(os.path.join(project, 'elements', 'fmt/good-format.bst')) as element:
        expected = element.readlines()[-1]

    res = cli.run(project=project, args=['fmt', '--all', target])
    assert res.exit_code == 0

    for i, _ in enumerate(initial_lines):
        with open(os.path.join(project, 'elements', check_elements[i])) as element:
            assert element.readlines()[-1] == expected


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_fmt_except(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bad_target = 'fmt/bad-format.bst'
    except_target = 'fmt/except.bst'
    target = 'fmt/stack.bst'

    with open(os.path.join(project, 'elements', 'fmt/good-format.bst')) as element:
        formatted = element.readlines()[-1]

    res = cli.run(project=project, args=['fmt', '--all', target, '--except', except_target])
    assert res.exit_code == 0

    with open(os.path.join(project, 'elements', except_target)) as element:
        assert formatted != element.readlines()[-1]

    with open(os.path.join(project, 'elements', bad_target)) as element:
        assert formatted == element.readlines()[-1]
