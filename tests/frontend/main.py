import click
import pytest

from buildstream._frontend.app import _prefix_choice_value_proc


def test_prefix_choice_value_proc_full_match():
    value_proc = _prefix_choice_value_proc(["foo", "bar", "baz"])

    assert value_proc("foo") == "foo"
    assert value_proc("bar") == "bar"
    assert value_proc("baz") == "baz"


def test_prefix_choice_value_proc_prefix_match():
    value_proc = _prefix_choice_value_proc(["foo"])

    assert value_proc("f") == "foo"


def test_prefix_choice_value_proc_ambigous_match():
    value_proc = _prefix_choice_value_proc(["bar", "baz"])

    assert value_proc("bar") == "bar"
    assert value_proc("baz") == "baz"
    with pytest.raises(click.UsageError):
        value_proc("ba")


def test_prefix_choice_value_proc_value_not_in_choices():
    value_proc = _prefix_choice_value_proc(["bar", "baz"])

    with pytest.raises(click.UsageError):
        value_proc("foo")
