import os
from buildstream._context import Context
from buildstream._project import Project
from buildstream._includes import Includes
from buildstream import _yaml


def make_includes(basedir):
    _yaml.dump({'name': 'test'},
               os.path.join(basedir, 'project.conf'))
    context = Context()
    project = Project(basedir, context)
    loader = project.loader
    return Includes(loader)


def test_main_has_prority(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml'],
                'test': ['main']},
               str(tmpdir.join('main.yml')))

    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': ['a']},
               str(tmpdir.join('a.yml')))

    includes.process(main)

    assert main['test'] == ['main']


def test_include_cannot_append(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml'],
                'test': ['main']},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': {'(>)': ['a']}},
               str(tmpdir.join('a.yml')))

    includes.process(main)

    assert main['test'] == ['main']


def test_main_can_append(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml'],
                'test': {'(>)': ['main']}},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': ['a']},
               str(tmpdir.join('a.yml')))

    includes.process(main)

    assert main['test'] == ['a', 'main']


def test_sibling_cannot_append_backward(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml', 'b.yml']},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': {'(>)': ['a']}},
               str(tmpdir.join('a.yml')))
    _yaml.dump({'test': ['b']},
               str(tmpdir.join('b.yml')))

    includes.process(main)

    assert main['test'] == ['b']


def test_sibling_can_append_forward(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml', 'b.yml']},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': ['a']},
               str(tmpdir.join('a.yml')))
    _yaml.dump({'test': {'(>)': ['b']}},
               str(tmpdir.join('b.yml')))

    includes.process(main)

    assert main['test'] == ['a', 'b']


def test_lastest_sibling_has_priority(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml', 'b.yml']},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': ['a']},
               str(tmpdir.join('a.yml')))
    _yaml.dump({'test': ['b']},
               str(tmpdir.join('b.yml')))

    includes.process(main)

    assert main['test'] == ['b']


def test_main_keeps_keys(tmpdir):
    includes = make_includes(str(tmpdir))

    _yaml.dump({'(@)': ['a.yml'],
                'something': 'else'},
               str(tmpdir.join('main.yml')))
    main = _yaml.load(str(tmpdir.join('main.yml')))

    _yaml.dump({'test': ['a']},
               str(tmpdir.join('a.yml')))

    includes.process(main)

    assert main['test'] == ['a']
    assert main['something'] == 'else'
