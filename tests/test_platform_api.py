"""
Tests for the platform API (docs/development_plan.md §F1).

Covers:

- case collection emits tags/author/priority parsed from docstring/markers;
- result payload building (summary + per-case results);
- --result-file writes the payload;
- --result-callback POSTs the payload (best-effort).
"""
import json
from types import SimpleNamespace

from lounger.plugin import _build_result_payload, _post_result_callback, _write_result_file
from lounger.plugin_hooks import TestRunResult
from lounger.utils import collect

# ── doc metadata parsing ──────────────────────────────────────────────────

def test_parse_doc_metadata_full():
    doc = """
    Verify creating a post.

    author: tom
    priority: P1
    tags: smoke, regression
    """
    meta = collect._parse_doc_metadata(doc)

    assert meta["author"] == "tom"
    assert meta["priority"] == "P1"
    assert meta["tags"] == ["smoke", "regression"]


def test_parse_doc_metadata_partial_and_case_insensitive():
    doc = "priority: p2\ntag: api"
    meta = collect._parse_doc_metadata(doc)

    assert meta["priority"] == "P2"
    assert meta["tags"] == ["api"]
    assert "author" not in meta


def test_parse_doc_metadata_empty():
    assert collect._parse_doc_metadata("just a description") == {}
    assert collect._parse_doc_metadata(None) == {}


def test_split_tags():
    assert collect._split_tags("smoke, api") == ["smoke", "api"]
    assert collect._split_tags("a b;c,d") == ["a", "b", "c", "d"]


# ── collection metadata emission ──────────────────────────────────────────

def _fake_item(nodeid, doc="", markers=None):
    return SimpleNamespace(
        fspath=SimpleNamespace(__str__=lambda self: "test_x.py"),
        nodeid=nodeid,
        name=nodeid.split("::")[-1],
        parent=SimpleNamespace(name="test_x.py"),
        obj=SimpleNamespace(__doc__=doc),
        own_markers=[SimpleNamespace(name=m) for m in (markers or [])],
    )


def test_json_collector_emits_platform_fields():
    collector = collect.JsonCollector()

    collector.pytest_collection_modifyitems(
        [
            _fake_item(
                "test_x.py::test_ok",
                doc="""\n    does a thing\n\n    author: alice\n    priority: P0\n    tags: core\n    """,
                markers=["parametrize", "smoke"],
            ),
            _fake_item("test_x.py::test_plain", doc="plain"),
        ]
    )

    ok = collector.test_data[0]
    assert ok["author"] == "alice"
    assert ok["priority"] == "P0"
    # docstring tags + extra marker(s) merged, no duplicates
    assert ok["tags"] == ["core", "smoke"]
    assert ok["markers"] == ["parametrize", "smoke"]

    plain = collector.test_data[1]
    assert plain["author"] == ""
    assert plain["priority"] == ""
    assert plain["tags"] == []


# ── result payload / file / callback ──────────────────────────────────────

def _summary(**kw):
    base = dict(total=3, passed=2, failed=1, errors=0, skipped=0, exitstatus=1)
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_result_payload_shape():
    payload = _build_result_payload(
        _summary(),
        "reports/result.html",
        [
            TestRunResult(nodeid="a::t1", status="passed", duration=0.1, description="d1"),
            TestRunResult(nodeid="a::t2", status="failed", duration=0.2, description=""),
        ],
    )

    assert payload["summary"]["passed"] == 2
    assert payload["summary"]["failed"] == 1
    assert payload["report_path"] == "reports/result.html"
    assert payload["results"][0]["nodeid"] == "a::t1"
    assert payload["results"][1]["status"] == "failed"


def test_write_result_file(tmp_path):
    out = tmp_path / "result.json"
    _write_result_file(str(out), {"summary": {"passed": 1}, "results": []})

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == 1


def test_post_result_callback_success(monkeypatch):
    import requests as real_requests

    calls = {}

    class FakeResp:
        ok = True
        status_code = 200
        text = ""

    def fake_post(url, json=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        return FakeResp()

    monkeypatch.setattr(real_requests, "post", fake_post)

    _post_result_callback("https://platform.example.com/cb", {"summary": {"passed": 1}})

    assert calls["url"] == "https://platform.example.com/cb"
    assert calls["json"]["summary"]["passed"] == 1


def test_post_result_callback_failure_no_raise(monkeypatch):
    import requests as real_requests

    def fake_post(url, json=None, timeout=None):
        raise ConnectionError("down")

    monkeypatch.setattr(real_requests, "post", fake_post)

    # must not raise — best-effort callback
    _post_result_callback("https://platform.example.com/cb", {"summary": {}})
