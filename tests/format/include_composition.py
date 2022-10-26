#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import os

from contextlib import contextmanager

from buildstream._project import Project
from buildstream._includes import Includes
from buildstream import _yaml

from tests.testutils import dummy_context


@contextmanager
def make_includes(basedir):
    _yaml.roundtrip_dump({"name": "test", "min-version": "2.0"}, os.path.join(basedir, "project.conf"))
    with dummy_context() as context:
        project = Project(basedir, context)
        loader = project.loader
        yield Includes(loader)


def test_main_has_priority(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml"], "test": ["main"]}, str(tmpdir.join("main.yml")))

        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": ["a"]}, str(tmpdir.join("a.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["main"]


def test_include_cannot_append(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml"], "test": ["main"]}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": {"(>)": ["a"]}}, str(tmpdir.join("a.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["main"]


def test_main_can_append(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml"], "test": {"(>)": ["main"]}}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": ["a"]}, str(tmpdir.join("a.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["a", "main"]


def test_sibling_cannot_append_backward(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml", "b.yml"]}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": {"(>)": ["a"]}}, str(tmpdir.join("a.yml")))
        _yaml.roundtrip_dump({"test": ["b"]}, str(tmpdir.join("b.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["b"]


def test_sibling_can_append_forward(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml", "b.yml"]}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": ["a"]}, str(tmpdir.join("a.yml")))
        _yaml.roundtrip_dump({"test": {"(>)": ["b"]}}, str(tmpdir.join("b.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["a", "b"]


def test_lastest_sibling_has_priority(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml", "b.yml"]}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": ["a"]}, str(tmpdir.join("a.yml")))
        _yaml.roundtrip_dump({"test": ["b"]}, str(tmpdir.join("b.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["b"]


def test_main_keeps_keys(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump({"(@)": ["a.yml"], "something": "else"}, str(tmpdir.join("main.yml")))
        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        _yaml.roundtrip_dump({"test": ["a"]}, str(tmpdir.join("a.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["a"]
        assert main.get_str("something") == "else"


def test_overwrite_directive_on_later_composite(tmpdir):
    with make_includes(str(tmpdir)) as includes:

        _yaml.roundtrip_dump(
            {"(@)": ["a.yml", "b.yml"], "test": {"(=)": ["Overwritten"]}}, str(tmpdir.join("main.yml"))
        )

        main = _yaml.load(str(tmpdir.join("main.yml")), shortname=None)

        # a.yml
        _yaml.roundtrip_dump(
            {"test": ["some useless", "list", "to be overwritten"], "foo": "should not be present"},
            str(tmpdir.join("a.yml")),
        )

        # b.yaml isn't going to have a 'test' node to overwrite
        _yaml.roundtrip_dump({"foo": "should be present"}, str(tmpdir.join("b.yml")))

        includes.process(main)

        assert main.get_str_list("test") == ["Overwritten"]
        assert main.get_str("foo") == "should be present"
