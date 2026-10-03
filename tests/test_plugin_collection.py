"""
Tests for the collection hook that annotates parameterized cases.

Regression context: ``pytest_collection_modifyitems`` only looked at the
parametrize argument named ``params`` (used by ``@data`` / ``@file_data``). YAML
cases arrive through ``@load_teststeps()``, which parametrizes ``teststeps``, so
every YAML case silently kept the entry function's generic docstring instead of
being labelled with its own case name.
"""
import json
from types import SimpleNamespace

import pytest

from lounger import plugin


def _fake_config(run_json_path=None):
    return SimpleNamespace(getoption=lambda name: run_json_path if name == "--run-json" else None)


def _make_function(doc, name="test_yaml"):
    """Build a real function object, as a collected pytest item would hold."""
    def template(teststeps=None):
        return None

    template.__doc__ = doc
    template.__name__ = name
    return template


def _item(nodeid, params=None, doc="entry doc", name="test_yaml"):
    """Build an item shaped like a real collected pytest item."""
    item = SimpleNamespace(nodeid=nodeid, _obj=_make_function(doc, name))
    if params is not None:
        item.callspec = SimpleNamespace(params=params)
    return item


@pytest.fixture(autouse=True)
def _no_manifest(monkeypatch):
    """The hook also writes a case manifest; keep the filesystem out of these tests."""
    monkeypatch.setattr(plugin, "write_case_manifest", lambda items: None)


YAML_CASE = {
    "name": "datas/sample/test_alpha.yaml::case_1_Getting a resource",
    "steps": [{"step": "Getting a resource", "request": {"method": "GET", "url": "/a"}}],
    "file": "datas/sample/test_alpha.yaml",
}


# ── A5: YAML cases are labelled ────────────────────────────────────────────

def test_yaml_parametrized_case_gets_a_description():
    """The YAML argument name (``teststeps``) must be recognised."""
    item = _item("test_api.py::test_api[datas/sample/test_alpha.yaml::case_1_Getting a resource]",
                 {"teststeps": YAML_CASE})

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert "Getting a resource" in item._obj.__doc__
    assert item._obj.__doc__.startswith("entry doc")


def test_each_yaml_case_gets_its_own_description():
    first = _item("t.py::test_api[a::case_1_first]", {"teststeps": dict(YAML_CASE)})
    second_case = dict(YAML_CASE, name="datas/sample/test_alpha.yaml::case_2_Creating a resource")
    second = _item("t.py::test_api[a::case_2_second]", {"teststeps": second_case})

    plugin.pytest_collection_modifyitems(_fake_config(), [first, second])

    assert "case_1" in first._obj.__doc__
    assert "case_2" in second._obj.__doc__
    assert first._obj.__doc__ != second._obj.__doc__


def test_case_payload_recognises_both_argument_names():
    yaml_item = _item("x::y[a]", {"teststeps": YAML_CASE})
    data_item = _item("x::y[b]", {"params": ["row", 1]})

    assert plugin._case_payload(yaml_item) is YAML_CASE
    assert plugin._case_payload(data_item) == ["row", 1]


def test_case_payload_ignores_project_parametrize_names():
    """A project's own parametrize argument must not be hijacked."""
    item = _item("x::y[z]", {"whatever": {"name": "not ours"}})

    assert plugin._case_payload(item) is None


def test_case_payload_handles_items_without_callspec():
    assert plugin._case_payload(_item("plain.py::test_ok")) is None
    assert plugin._case_payload(SimpleNamespace(callspec=SimpleNamespace(params=None))) is None


# ── existing behaviour for @data / @file_data ─────────────────────────────

def test_list_case_uses_first_value_as_name():
    item = _item("x::y[1]", {"params": ["alice", "secret"]})

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__doc__.endswith("alice")


def test_dict_case_prefers_explicit_business_fields():
    item = _item("x::y[1]", {"params": {"test_case": "login ok", "other": "x"}})

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__doc__.endswith("login ok")


def test_scalar_case_falls_back_to_its_value():
    assert plugin._case_display_name("value") == "value"
    assert plugin._case_display_name(None) == "none"
    assert plugin._case_display_name([]) == ""


def test_unparametrized_item_is_untouched():
    item = _item("plain.py::test_ok")

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__doc__ == "entry doc"


def test_bound_method_is_rewritten_without_losing_self():
    class Suite:
        def test_yaml(self, teststeps):
            """suite doc"""

    suite = Suite()
    item = _item("t.py::Suite::test_yaml[case]", {"teststeps": YAML_CASE})
    item._obj = suite.test_yaml

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert item._obj.__self__ is suite
    assert "case_1" in item._obj.__doc__


def test_non_function_callable_is_skipped():
    """functools.partial-like objects must not crash collection."""
    obj = SimpleNamespace(__doc__="partial doc", __call__=lambda *a: None)
    item = _item("t.py::test_x[a]", {"teststeps": YAML_CASE})
    item._obj = obj

    plugin.pytest_collection_modifyitems(_fake_config(), [item])

    assert obj.__doc__ == "partial doc"


# ── --run-json still works alongside the annotation ───────────────────────

def test_run_json_reordering_is_unaffected(scratch):
    run_json = scratch / "run.json"
    run_json.write_text(json.dumps([{"nodeid": "b::t2"}, {"nodeid": "a::t1"}]), encoding="utf-8")

    items = [_item("a::t1"), _item("b::t2")]
    plugin.pytest_collection_modifyitems(_fake_config(str(run_json)), items)

    assert [item.nodeid for item in items] == ["b::t2", "a::t1"]
