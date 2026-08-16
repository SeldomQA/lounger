"""
Tests for the services layer and web_runner robustness
(docs/development_plan.md §3.8).

Covers:

- ``case_discovery``: YAML naming-rule pluginization (custom rule +
  fallback), structured errors on collection failure;
- ``test_execution``: pytest command building, payload writing, bounded
  run history (archive keeps most recent N, persists the rest to
  reports/runs/);
- ``html.py``: data-ids is encodeURIComponent-encoded so quotes in
  nodeids cannot break the HTML attribute.
"""
import json
import threading
from pathlib import Path

from lounger.services import case_discovery, test_execution
from lounger.web_runner import html

# ── case_discovery: naming-rule pluginization ─────────────────────────────

def test_discover_cases_custom_naming_rule(tmp_path, monkeypatch):
    """A project-provided naming rule overrides YAML-case fields."""
    collected = [
        {"nodeid": "test_api.py::test_api[foo::case_1_step_1]", "name": "x", "file": "test_api.py"},
    ]

    def fake_collect(scan_dir, timeout=30):
        return collected

    monkeypatch.setattr(case_discovery, "_collect_via_subprocess", fake_collect)
    monkeypatch.setattr(case_discovery, "_get_yaml_case_metadata", lambda sd: {
        "foo::case_1_step_1": {"file": "datas/foo.yaml", "name": "自定义名", "description": "desc"},
    })

    def my_rule(nodeid, metadata):
        # pluginized naming rule: extract the param key from the nodeid
        import re
        m = re.search(r"\[(.+?)\]$", nodeid)
        if m and m.group(1) in metadata:
            return metadata[m.group(1)]
        return None

    cases = case_discovery.discover_cases(str(tmp_path), yaml_naming_rule=my_rule)

    assert cases[0]["file"] == "datas/foo.yaml"
    assert cases[0]["name"] == "自定义名"
    assert cases[0]["description"] == "desc"


def test_discover_cases_fallback_rule_keeps_unmatched():
    """Cases that match no YAML metadata keep their collected fields."""
    cases = case_discovery._apply_naming_rule(
        {"nodeid": "test_plain.py::test_ok", "name": "plain"},
        {},
        case_discovery._yaml_metadata_rule,
    )
    assert cases["name"] == "plain"


def test_discover_cases_structured_error_on_timeout(monkeypatch):
    import subprocess

    def fake_collect(scan_dir, timeout=30):
        raise subprocess.TimeoutExpired(cmd=["pytest"], timeout=timeout)

    monkeypatch.setattr(case_discovery, "_collect_via_subprocess", fake_collect)

    result = case_discovery.discover_cases(".")

    assert isinstance(result, dict)
    assert "error" in result
    assert "timed out" in result["error"]


def test_discover_cases_structured_error_on_invalid_json(monkeypatch):
    def fake_collect(scan_dir, timeout=30):
        raise json.JSONDecodeError("bad", "doc", 0)

    monkeypatch.setattr(case_discovery, "_collect_via_subprocess", fake_collect)

    result = case_discovery.discover_cases(".")

    assert isinstance(result, dict)
    assert "error" in result
    assert "invalid JSON" in result["error"]


# ── test_execution: command / payload / archive ───────────────────────────

def test_build_pytest_command_includes_run_json_and_verbosity():
    cmd = test_execution.build_pytest_command("abc", Path("run.json"), "verbose")

    assert cmd[0:3] == [__import__("sys").executable, "-m", "pytest"]
    assert "--run-json" in cmd
    assert str(Path("run.json")) in cmd
    assert "-v" in cmd


def test_write_run_payload_creates_json_file(tmp_path):
    target = test_execution.write_run_payload(str(tmp_path), "run1", ["a::t1", "b::t2"])

    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == [{"nodeid": "a::t1"}, {"nodeid": "b::t2"}]


def test_archive_run_persists_and_bounds_memory(tmp_path):
    runs = {}
    lock = threading.Lock()

    for i in range(3):
        runs[f"r{i}"] = {
            "status": "completed",
            "logs": [f"log-{i}"],
            "nodeids": [f"n{i}"],
            "exit_code": 0,
            "queue": object(),  # non-serializable; must be dropped by archive
        }

    # archive the oldest run (r0)
    ok = test_execution.archive_run(runs, str(tmp_path), "r0", keep_recent=2, lock=lock)

    assert ok is True
    assert "r0" not in runs

    # r0 was persisted to reports/runs/
    persisted = tmp_path / "reports" / "runs" / "r0.json"
    assert persisted.exists()
    snapshot = json.loads(persisted.read_text(encoding="utf-8"))
    assert snapshot["logs"] == ["log-0"]
    assert snapshot["exit_code"] == 0
    assert "queue" not in snapshot


def test_archive_run_skips_running_and_unknown():
    runs = {"live": {"status": "running", "queue": object()}}
    lock = threading.Lock()

    assert test_execution.archive_run(runs, ".", "live", lock=lock) is False
    assert test_execution.archive_run(runs, ".", "nope", lock=lock) is False


def test_archive_run_trims_excess_finished_runs(tmp_path):
    runs = {}
    lock = threading.Lock()
    for i in range(5):
        runs[f"r{i}"] = {"status": "completed", "logs": [], "exit_code": 0}

    # archiving r4 with keep_recent=2 leaves at most 2 finished runs in memory
    test_execution.archive_run(runs, str(tmp_path), "r4", keep_recent=2, lock=lock)

    remaining = [rid for rid in runs if rid != "r4"]
    assert len(remaining) <= 2
    # the persisted dir contains the archived ones
    archived = list((tmp_path / "reports" / "runs").glob("*.json"))
    assert len(archived) >= 3


# ── html.py: data-ids encoding ────────────────────────────────────────────

def test_html_data_ids_uses_encode_uri_component():
    """nodeids with quotes must not break the data-ids attribute (3.8 §4)."""
    assert 'encodeURIComponent(JSON.stringify(node.cases.map(c => c.nodeid)))' in html._FALLBACK_HTML
    assert 'data-ids="\' + idsJson' in html._FALLBACK_HTML.replace("'", "\u0027") or \
        'data-ids="' in html._FALLBACK_HTML
    assert "JSON.parse(decodeURIComponent(nodeidsStr))" in html._FALLBACK_HTML


def test_run_file_decodes_encoded_ids():
    """runFile must decode the URI-encoded ids before JSON.parse."""
    assert "decodeURIComponent" in html._FALLBACK_HTML
