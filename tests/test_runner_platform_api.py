"""Real HTTP contracts: authorization, task CRUD, execution and streaming."""

import json
import re
import secrets
import threading
import urllib.error
import urllib.request

import pytest

from lounger.web_runner.api import PlatformHandler
from lounger.web_runner.context import ProjectContext
from lounger.web_runner.manager import RunManager
from lounger.web_runner.server import _ThreadingHTTPServer


@pytest.fixture
def http(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_demo.py").write_text('def test_ok():\n    print("你好")\n    assert True\n', encoding="utf-8")
    manager = RunManager(ProjectContext.create(str(tmp_path)))
    server = _ThreadingHTTPServer(("127.0.0.1", 0), PlatformHandler)
    server.manager, server.session_token = manager, secrets.token_urlsafe(32)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, method="GET", data=None, auth=True, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if auth:
            h["X-Lounger-Token"] = server.session_token
        request = urllib.request.Request(
            base + path, data=json.dumps(data or {}).encode() if method != "GET" else None, method=method, headers=h
        )
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if "application/json" in response.headers.get(
                "Content-Type", ""
            ) else raw

    yield call, manager, base
    server.shutdown()
    manager.close()
    server.server_close()
    thread.join()


def definition():
    return dict(
        name="Smoke",
        selection=dict(type="nodeids", nodeids=["test_demo.py::test_ok"]),
        options=dict(verbosity="verbose", html_report=False),
    )


def test_session_token_and_origin_required(http):
    call, manager, base = http
    status, page = call("/")
    assert status == 200 and re.search(b'<meta name="lounger-token"', page)
    assert call("/api/v1/tasks", "POST", definition(), auth=False)[0] == 403
    assert call("/api/v1/tasks", "POST", definition(), headers={"Origin": "https://evil.example"})[0] == 403
    assert call("/api/v1/project", headers={"Host": "evil.example"})[0] == 403
    assert call("/api/v1/tasks", "POST", definition())[0] == 201


def test_task_crud_revision_and_pagination(http):
    call, _, _ = http
    _, task = call("/api/v1/tasks", "POST", definition())
    path = "/api/v1/tasks/" + task["id"]
    assert call(path, "PATCH", {"name": "New"})[0] == 400
    status, new = call(path, "PATCH", {"name": "New", "revision": 1})
    assert status == 200 and new["revision"] == 2
    assert call(path, "PATCH", {"name": "Stale", "revision": 1})[0] == 409
    assert call("/api/v1/tasks?page_size=0")[0] == 400
    assert call("/api/v1/tasks")[1]["total"] == 1
    assert call(path, "DELETE")[0] == 200
    assert call(path)[0] == 404


def test_execution_stream_results_and_history(http, monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    call, manager, base = http
    status, cases = call("/api/v1/cases/tree")
    assert status == 200 and cases["flat"][0]["nodeid"] == "test_demo.py::test_ok"
    _, task = call("/api/v1/tasks", "POST", definition())
    status, run = call(
        "/api/v1/tasks/" + task["id"] + "/runs", "POST", {"verbosity": "verbose"}, headers={"Idempotency-Key": "one"}
    )
    assert status == 202
    manager.thread.join(15)
    rid = run["id"]
    assert call("/api/v1/runs/" + rid)[1]["outcome"] == "passed"
    assert call("/api/v1/runs/" + rid + "/results")[1]["total"] == 1
    status, log = call("/api/v1/runs/" + rid + "/logs")
    assert "你好" in log["text"]
    assert call("/api/v1/runs?outcome=passed")[1]["total"] == 1
    assert call("/api/v1/runs?outcome=failed")[1]["total"] == 0
    with urllib.request.urlopen(base + "/api/v1/runs/" + rid + "/events", timeout=10) as stream:
        events = stream.read().decode()
    assert "你好" in events and '"done": true' in events and "id: " in events
    with urllib.request.urlopen(
        urllib.request.Request(base + "/api/v1/runs/" + rid + "/events", headers={"Last-Event-ID": str(log["cursor"])}),
        timeout=10,
    ) as stream:
        resumed = stream.read().decode()
    assert "你好" not in resumed and '"done": true' in resumed
    assert call("/api/history")[1][0]["run_id"] == rid
    assert call("/api/history/" + rid)[1]["logs"]
    assert call("/api/v1/runs/" + rid + "/artifacts/../../runner.db")[0] == 404
    assert call("/api/v1/runs/" + rid, "DELETE")[0] == 200
    assert call("/api/v1/runs/" + rid)[0] == 404


def test_packaged_static_resources(http):
    call, _, _ = http
    for name in ["runner.css", "runner.js", "platform.css", "platform.js"]:
        status, body = call("/static/" + name)
        assert status == 200 and body
    assert call("/static/../manager.py")[0] == 404


@pytest.mark.parametrize("stored_separator", ["/", "\\"])
def test_old_history_bookmarks_resolve_after_import(http, stored_separator):
    call, manager, _ = http
    directory = manager.context.root / "reports" / "runs"
    directory.mkdir(parents=True)
    (directory / "old123.json").write_text(json.dumps({"status": "completed", "logs": ["old log\n"], "nodeids": []}))
    manager._import_legacy()
    with manager.store.connection() as db:
        key = db.execute("SELECT source_key FROM legacy_imports").fetchone()[0]
        assert key == "reports/runs/old123.json"
        db.execute("UPDATE legacy_imports SET source_key=?", (key.replace("/", stored_separator),))
    manager._import_legacy()
    assert manager.store.runs()["total"] == 1
    with manager.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM legacy_imports").fetchone()[0] == 1
    status, data = call("/api/history/old123")
    assert status == 200 and data["logs"] == ["old log\n"]
    assert call("/api/history/old123", "DELETE")[0] == 200
    manager._import_legacy()
    assert manager.store.runs()["total"] == 0
    assert call("/api/history/old123")[0] == 404


def test_task_validation_endpoint_and_recheck_on_execution(http):
    call, manager, _ = http
    _, task = call("/api/v1/tasks", "POST", definition())
    status, result = call("/api/v1/tasks/validate", "POST", {"task_ids": [task["id"]]})
    assert status == 200 and result["items"][0]["status"] == "valid"
    (manager.context.root / "test_demo.py").write_text("def test_renamed():\n    pass\n")
    status, result = call("/api/v1/tasks/validate", "POST", {"task_ids": [task["id"]]})
    assert result["items"][0]["status"] == "invalid"
    status, error = call("/api/v1/tasks/" + task["id"] + "/runs", "POST")
    assert status == 409 and error["error"]["code"] == "selection_stale"
    assert manager.store.runs()["total"] == 0
    assert call("/api/v1/tasks/validate", "POST", {"task_ids": "bad"})[0] == 400
