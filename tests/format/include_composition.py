import os

from contextlib import contextmanager

from buildstream._project import Project
from buildstream._includes import Includes
from buildstream import _yaml

from tests.testutils import dummy_context


@contextmanager
def make_includes(basedir):
    _yaml.dump({'name': 'test'},
               os.path.join(basedir, 'project.conf'))
    with dummy_context() as context:
        project = Project(basedir, context)
        loader = project.loader
        yield Includes(loader)


def test_main_has_prority(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml'],
                    'test': ['main']},
                   str(tmpdir.join('main.yml')))

        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': ['a']},
                   str(tmpdir.join('a.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['main']


def test_include_cannot_append(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml'],
                    'test': ['main']},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': {'(>)': ['a']}},
                   str(tmpdir.join('a.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['main']


def test_main_can_append(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml'],
                    'test': {'(>)': ['main']}},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': ['a']},
                   str(tmpdir.join('a.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['a', 'main']


def test_sibling_cannot_append_backward(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml', 'b.yml']},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': {'(>)': ['a']}},
                   str(tmpdir.join('a.yml')))
        _yaml.dump({'test': ['b']},
                   str(tmpdir.join('b.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['b']


def test_sibling_can_append_forward(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml', 'b.yml']},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': ['a']},
                   str(tmpdir.join('a.yml')))
        _yaml.dump({'test': {'(>)': ['b']}},
                   str(tmpdir.join('b.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['a', 'b']


def test_lastest_sibling_has_priority(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml', 'b.yml']},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': ['a']},
                   str(tmpdir.join('a.yml')))
        _yaml.dump({'test': ['b']},
                   str(tmpdir.join('b.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['b']


def test_main_keeps_keys(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml'],
                    'something': 'else'},
                   str(tmpdir.join('main.yml')))
        main = _yaml.load(str(tmpdir.join('main.yml')))

        _yaml.dump({'test': ['a']},
                   str(tmpdir.join('a.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['a']
        assert _yaml.node_get(main, str, 'something') == 'else'


def test_overwrite_directive_on_later_composite(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.dump({'(@)': ['a.yml', 'b.yml'],
                    'test': {'(=)': ['Overwritten']}},
                   str(tmpdir.join('main.yml')))

        main = _yaml.load(str(tmpdir.join('main.yml')))

        # a.yml
        _yaml.dump({'test': ['some useless', 'list', 'to be overwritten'],
                    'foo': 'should not be present'},
                   str(tmpdir.join('a.yml')))

        # b.yaml isn't going to have a 'test' node to overwrite
        _yaml.dump({'foo': 'should be present'},
                   str(tmpdir.join('b.yml')))

        includes.process(main)

        assert _yaml.node_get(main, list, 'test') == ['Overwritten']
        assert _yaml.node_get(main, str, 'foo') == 'should be present'
