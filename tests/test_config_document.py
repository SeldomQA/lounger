"""The editor works with YAML values, independent of environment/service schemas."""
import pytest
import yaml

from lounger.web_runner.config_document import ConfigDocument
from lounger.web_runner.storage import Problem


def document(tmp_path, text):
    directory = tmp_path / "config"
    directory.mkdir(exist_ok=True)
    (directory / "config.yaml").write_text(text)
    return ConfigDocument.load(tmp_path)


@pytest.mark.parametrize("source,action,path,value,key,expected", [
    ("host: old\n", "set", ["host"], "new", None, {"host": "new"}),
    ("service.auth: old\n", "set", ["service.auth"], "new", None, {"service.auth": "new"}),
    ("servers:\n  - one\n  - two\n", "set", ["servers", 1], "updated", None, {"servers": ["one", "updated"]}),
    ("a: {b: 1, c: 2}\n", "set", ["a", "b"], False, None, {"a": {"b": False, "c": 2}}),
    ("a:\n  b: 1\nother: yes\n", "add", ["a"], "value", "new", {"a": {"b": 1, "new": "value"}, "other": True}),
    ("a: {}\n", "add", ["a"], [1, 2], "list", {"a": {"list": [1, 2]}}),
    ("a: []\n", "add", ["a"], {"nested": "yes"}, None, {"a": [{"nested": "yes"}]}),
    ("a:\n  - one\nother: value\n", "add", ["a"], "two", None, {"a": ["one", "two"], "other": "value"}),
    ("a:\n  b: 1\n  c: 2\nother: 3\n", "delete", ["a", "b"], None, None, {"a": {"c": 2}, "other": 3}),
    ("a:\n  b: 1\nother: 3\n", "delete", ["a", "b"], None, None, {"a": {}, "other": 3}),
    ("root:\n  a:\n    b: 1\n  sibling: 3\n", "delete", ["root", "a", "b"], None, None, {"root": {"a": {}, "sibling": 3}}),
    ("a: [one, two]\n", "delete", ["a", 0], None, None, {"a": ["two"]}),
    ("a:\n  - one\n  - two\n", "delete", ["a", 1], None, None, {"a": ["one"]}),
    ("a:\n  - one\nother: 3\n", "delete", ["a", 0], None, None, {"a": [], "other": 3}),
    ("- one\n- two\n", "add", [], "three", None, ["one", "two", "three"]),
    ("- one\n- two\n", "delete", [0], None, None, ["two"]),
    ("single-value\n", "set", [], {"new": 10}, None, {"new": 10}),
    ("a: |\n  hello\n  world\nother: 3\n", "set", ["a"], "changed", None, {"a": "changed", "other": 3}),
    ("a: |\n  hello\n  world\nother: 3\n", "delete", ["a"], None, None, {"other": 3}),
    ("a:\n  b: |\n    hello\n  c: 3\n", "delete", ["a", "b"], None, None, {"a": {"c": 3}}),
    ("a:\n  b: |\n    hello\nother: 3\n", "add", ["a"], "new", "c", {"a": {"b": "hello\n", "c": "new"}, "other": 3}),
    ("a: 1", "add", [], "x", "b", {"a": 1, "b": "x"}),
])
def test_edit_various_structures(tmp_path, source, action, path, value, key, expected):
    doc = document(tmp_path, source)
    doc.mutate(action, path, value, doc.revision, key)
    assert yaml.safe_load(doc.path.read_text()) == expected


def test_preserves_comments_and_unrelated_compatibility_block(tmp_path):
    source = "# first\na:\n  auth: original # auth comment\n  other: keep\n# legacy\nlegacy: {value: unchanged}\n"
    doc = document(tmp_path, source)
    doc.mutate("set", ["a", "auth"], "new # ': value", doc.revision)
    text = doc.path.read_text()
    assert text.startswith("# first\n") and "# auth comment" in text
    assert text.endswith("# legacy\nlegacy: {value: unchanged}\n")
    assert yaml.safe_load(text)["a"]["auth"] == "new # ': value"


def test_view_shows_values_directly_and_supports_lists(tmp_path):
    doc = document(tmp_path, "custom:\n  users:\n    - name: Alice\n      token: do-not-expose-token\n")
    tree = doc.view()["tree"]
    field = tree["children"][0]["children"][0]["children"][0]["children"][1]
    assert field["path"] == ["custom", "users", 0, "token"]
    assert field["value"] == "do-not-expose-token"
    assert "masked" not in field and "secret" not in field


def test_missing_file_can_be_created_without_a_template(tmp_path):
    doc = ConfigDocument.load(tmp_path)
    assert doc.view()["exists"] is False
    doc.mutate("add", [], "https://example.test", doc.revision, "host")
    assert yaml.safe_load(doc.path.read_text()) == {"host": "https://example.test"}


def test_comment_only_file_keeps_comments_when_adding_first_entry(tmp_path):
    doc = document(tmp_path, "# Initial settings\n")
    doc.mutate("add", [], "https://example.test", doc.revision, "host")
    assert doc.path.read_text().startswith("# Initial settings\n")
    assert yaml.safe_load(doc.path.read_text()) == {"host": "https://example.test"}


def test_external_edit_conflicts_without_overwrite(tmp_path):
    doc = document(tmp_path, "a: original\n")
    doc.path.write_text("a: manual\n")
    with pytest.raises(Problem) as exc:
        doc.mutate("set", ["a"], "old-editor", doc.revision)
    assert exc.value.status == 409
    assert doc.path.read_text() == "a: manual\n"


@pytest.mark.parametrize("action,path,value,key", [
    ("set", ["missing"], "new", None),
    ("add", [], "new", "a"),
    ("delete", [], None, None),
    ("add", ["a"], "new", "b"),
    ("set", ["a"], float("inf"), None),
])
def test_invalid_operations_leave_file_intact(tmp_path, action, path, value, key):
    doc = document(tmp_path, "a: original\n")
    with pytest.raises((ValueError, TypeError)):
        doc.mutate(action, path, value, doc.revision, key)
    assert doc.path.read_text() == "a: original\n"


def test_shared_alias_cannot_change_another_location(tmp_path):
    source = "first: &shared\n  auth: original\nsecond: *shared\n"
    doc = document(tmp_path, source)
    with pytest.raises(ValueError, match="共享"):
        doc.mutate("set", ["second", "auth"], "new", doc.revision)
    assert doc.path.read_text() == source
