from buildstream._frontend.app import _prefix_choice_value_proc

import pytest
import click


def test_prefix_choice_value_proc_full_match():
    value_proc = _prefix_choice_value_proc(['foo', 'bar', 'baz'])

    assert("foo" == value_proc("foo"))
    assert("bar" == value_proc("bar"))
    assert("baz" == value_proc("baz"))


def test_prefix_choice_value_proc_prefix_match():
    value_proc = _prefix_choice_value_proc(['foo'])

    assert ("foo" == value_proc("f"))


def test_prefix_choice_value_proc_ambigous_match():
    value_proc = _prefix_choice_value_proc(['bar', 'baz'])

    assert ("bar" == value_proc("bar"))
    assert ("baz" == value_proc("baz"))
    with pytest.raises(click.UsageError):
        value_proc("ba")


def test_prefix_choice_value_proc_value_not_in_choices():
    value_proc = _prefix_choice_value_proc(['bar', 'baz'])

    with pytest.raises(click.UsageError):
        value_proc("foo")
