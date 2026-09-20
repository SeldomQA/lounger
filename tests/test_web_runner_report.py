"""
Tests for the HTML report feature of the web runner:

- the report checkbox is sent with the run request and controls whether pytest
  writes a report (including overriding ``--html`` from the project's pytest.ini);
- a finished run exposes its report, served over HTTP so it can be opened in a
  new browser tab (``file://`` links are blocked from an ``http://`` page);
- run history keeps each run's own report path.
"""

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lounger.services import test_execution
from lounger.web_runner import server as server_mod
from lounger.web_runner.html import _FALLBACK_HTML
from lounger.web_runner.state import _active_runs, _runs_lock

# ── service layer: report path & addopts handling ─────────────────────────


def test_report_path_is_per_run(tmp_path):
    path = test_execution.report_path(str(tmp_path), "abc123")

    assert path == tmp_path / "reports" / "result_abc123.html"


def test_read_project_addopts_from_pytest_ini(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = --html=./reports/result.html -p no:cacheprovider\n",
        encoding="utf-8",
    )

    addopts = test_execution.read_project_addopts(str(tmp_path))

    assert "--html=./reports/result.html" in addopts
    assert "-p no:cacheprovider" in addopts


def test_read_project_addopts_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--html=reports/r.html -q"\n',
        encoding="utf-8",
    )

    assert "--html=reports/r.html" in test_execution.read_project_addopts(str(tmp_path))


def test_read_project_addopts_absent(tmp_path):
    assert test_execution.read_project_addopts(str(tmp_path)) == ""


@pytest.mark.parametrize(
    "addopts, expected_has_html",
    [
        ("--html=raports/result.html", False),
        ("--html reports/result.html", False),
        ("--html=result.html --self-contained-html", False),
        ("-q --html=result.html -p no:cacheprovider", False),
        ("-q -p no:cacheprovider", False),
    ],
)
def test_without_html_addopts(addopts, expected_has_html):
    cleaned = test_execution.without_html_addopts(addopts)

    assert "--html" not in cleaned
    assert "--self-contained-html" not in cleaned
    assert cleaned == cleaned.strip()
    assert ("--html" in cleaned) is expected_has_html
    # unrelated options survive verbatim
    for token in ("-q", "-p", "no:cacheprovider"):
        if token in addopts:
            assert token in cleaned


def test_build_pytest_command_with_report(tmp_path):
    target = tmp_path / "_web_run_x.json"
    report = tmp_path / "reports" / "result_x.html"

    cmd = test_execution.build_pytest_command("x", target, "verbose", html_report=report)

    assert f"--html={report}" in cmd
    assert "--run-json" in cmd


def test_build_pytest_command_without_report_overrides_addopts(tmp_path):
    target = tmp_path / "_web_run_x.json"

    cmd = test_execution.build_pytest_command("x", target, "quiet", addopts_override="-p no:cacheprovider")

    assert not any(str(part).startswith("--html") for part in cmd)
    assert "-o" in cmd
    assert "addopts=-p no:cacheprovider" in cmd


# ── service layer: start_run records the report ───────────────────────────


def test_start_run_enables_report(tmp_path, monkeypatch):
    """With the checkbox on, the run records its report path and disables nothing."""
    captured = {}

    def fake_execute(*args, **kwargs):
        captured["report_file"] = kwargs.get("report_file", args[-2] if args else None)
        captured["addopts_override"] = kwargs.get("addopts_override", args[-1] if args else None)

    monkeypatch.setattr(test_execution, "_execute_in_thread", fake_execute)
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --html=./reports/result.html\n", encoding="utf-8")
    runs: dict = {}

    test_execution.start_run(runs, str(tmp_path), "run1", ["a::b"], html_report=True)

    assert runs["run1"]["html_report"] is True
    assert runs["run1"]["report_path"] == str(tmp_path / "reports" / "result_run1.html")
    assert (tmp_path / "reports").is_dir()
    # the project's own --html is left alone (ours wins by being later on the CLI)
    assert captured["addopts_override"] is None


def test_start_run_disables_project_report(tmp_path, monkeypatch):
    """With the checkbox off, the project's ``--html`` is stripped from addopts."""
    captured = {}

    def fake_execute(*args, **kwargs):
        captured["addopts_override"] = kwargs.get("addopts_override", args[-1] if args else None)
        captured["report_file"] = kwargs.get("report_file", args[-2] if args else None)

    monkeypatch.setattr(test_execution, "_execute_in_thread", fake_execute)
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = --html=./reports/result.html -p no:cacheprovider\n",
        encoding="utf-8",
    )
    runs: dict = {}

    test_execution.start_run(runs, str(tmp_path), "run2", ["a::b"], html_report=False)

    assert runs["run2"]["html_report"] is False
    assert runs["run2"]["report_path"] is None
    assert captured["report_file"] is None
    assert captured["addopts_override"] == "-p no:cacheprovider"


def test_serialize_run_keeps_report_fields():
    snapshot = test_execution._serialize_run({"status": "completed", "html_report": True, "report_path": "/tmp/r.html"})

    assert snapshot["html_report"] is True
    assert snapshot["report_path"] == "/tmp/r.html"


# ── server: serving the report over HTTP ──────────────────────────────────


def _with_server():
    httpd = server_mod._ThreadingHTTPServer(("127.0.0.1", 0), server_mod._RequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _get(url, redirect=True):
    if redirect:
        return urllib.request.urlopen(url, timeout=5)
    opener = urllib.request.build_opener(
        type(
            "NoRedirect",
            (urllib.request.HTTPRedirectHandler,),
            {"redirect_request": lambda *a, **k: None},
        )
    )
    return opener.open(url, timeout=5)


def test_report_is_served_and_assets_resolve(tmp_path, monkeypatch):
    """A finished run's report is reachable over HTTP (new-tab friendly)."""
    report_dir = tmp_path / "reports"
    (report_dir / "assets").mkdir(parents=True)
    report = report_dir / "result_run1.html"
    report.write_text(
        '<html><head><link rel="stylesheet" href="assets/style.css"></head><body>lounger report</body></html>',
        encoding="utf-8",
    )
    (report_dir / "assets" / "style.css").write_text("body{color:red}", encoding="utf-8")

    with _runs_lock:
        _active_runs["run1"] = {"status": "completed", "logs": [], "report_path": str(report)}
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    httpd = _with_server()
    port = httpd.server_address[1]
    try:
        # the short URL redirects into the report directory so relative assets work
        with _get(f"http://127.0.0.1:{port}/api/report/run1") as resp:
            assert resp.status == 200
            assert b"lounger report" in resp.read()
            assert resp.url.endswith("/api/report/run1/result_run1.html")

        with _get(f"http://127.0.0.1:{port}/api/report/run1/assets/style.css") as resp:
            assert resp.status == 200
            assert "text/css" in resp.headers["Content-Type"]
            assert resp.read() == b"body{color:red}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        with _runs_lock:
            _active_runs.pop("run1", None)


def test_report_route_rejects_unknown_run(tmp_path, monkeypatch):
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))
    httpd = _with_server()
    port = httpd.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(f"http://127.0.0.1:{port}/api/report/nope")
        assert excinfo.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_report_route_blocks_path_traversal(tmp_path, monkeypatch):
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report = report_dir / "result_run1.html"
    report.write_text("<html>ok</html>", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")

    with _runs_lock:
        _active_runs["run1"] = {"status": "completed", "logs": [], "report_path": str(report)}
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    httpd = _with_server()
    port = httpd.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(f"http://127.0.0.1:{port}/api/report/run1/../secret.txt")
        assert excinfo.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
        with _runs_lock:
            _active_runs.pop("run1", None)


def test_run_request_with_report_reports_url(tmp_path, monkeypatch):
    """POST /api/run {"report": true} → the done event carries report_url."""
    lines = ["running…"]

    def fake_execute(run_id, nodeids, verbosity="verbose", html_report=False):
        with _runs_lock:
            info = _active_runs[run_id]
            report_path = info.get("report_path")
        if html_report and report_path:
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("<html>report</html>", encoding="utf-8")
        with _runs_lock:
            info["logs"].extend(lines)
            info["status"] = "completed"
            info["exit_code"] = 0

    monkeypatch.setattr(server_mod, "_execute_tests", fake_execute)
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    httpd = _with_server()
    port = httpd.server_address[1]
    run_id = None
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/run",
            data=json.dumps({"nodeids": ["a::b"], "verbosity": "quiet", "report": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as resp:
            run_id = json.loads(resp.read())["run_id"]

        events = []
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stream/{run_id}", timeout=10) as resp:
            for raw in resp:
                text = raw.decode().strip()
                if text.startswith("data: "):
                    payload = json.loads(text[len("data: ") :])
                    events.append(payload)
                    if payload.get("done"):
                        break

        assert events[-1]["done"] is True
        assert events[-1]["report_url"] == f"/api/report/{run_id}"

        # and the URL actually serves the generated report
        with _get(f"http://127.0.0.1:{port}{events[-1]['report_url']}") as resp:
            assert b"report" in resp.read()
    finally:
        httpd.shutdown()
        httpd.server_close()
        if run_id is not None:
            with _runs_lock:
                _active_runs.pop(run_id, None)


def test_run_without_report_has_no_report_url(tmp_path, monkeypatch):
    def fake_execute(run_id, nodeids, verbosity="verbose", html_report=False):
        with _runs_lock:
            info = _active_runs[run_id]
            info["status"] = "completed"
            info["exit_code"] = 0

    monkeypatch.setattr(server_mod, "_execute_tests", fake_execute)
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    httpd = _with_server()
    port = httpd.server_address[1]
    run_id = None
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/run",
            data=json.dumps({"nodeids": ["a::b"], "report": False}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as resp:
            run_id = json.loads(resp.read())["run_id"]

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stream/{run_id}", timeout=10) as resp:
            for raw in resp:
                text = raw.decode().strip()
                if not text.startswith("data: "):
                    continue
                payload = json.loads(text[len("data: ") :])
                if payload.get("done"):
                    assert payload["report_url"] is None
                    break
    finally:
        httpd.shutdown()
        httpd.server_close()
        if run_id is not None:
            with _runs_lock:
                _active_runs.pop(run_id, None)


# ── client UI ─────────────────────────────────────────────────────────────


def test_html_has_report_toggle_and_button():
    assert 'id="reportToggle"' in _FALLBACK_HTML
    assert 'id="reportGroup"' in _FALLBACK_HTML
    assert 'id="reportBtn"' in _FALLBACK_HTML
    assert "REPORT_ENABLED_KEY" in _FALLBACK_HTML
    assert "lounger.webRunner.reportEnabled" in _FALLBACK_HTML
    assert "function setReportEnabled(" in _FALLBACK_HTML
    assert "function showReportButton(" in _FALLBACK_HTML
    assert "function openReport(" in _FALLBACK_HTML
    # the request carries the checkbox state, the done event drives the button
    assert "report: reportEnabled" in _FALLBACK_HTML
    assert "showReportButton(msg.report_url || null)" in _FALLBACK_HTML
    assert "window.open(currentReportUrl, '_blank'" in _FALLBACK_HTML
    # history detail can open the archived run's report too
    assert 'id="historyReportBtn"' in _FALLBACK_HTML
    assert "function openHistoryReport(" in _FALLBACK_HTML


def test_report_toggle_preserves_quoted_project_options():
    import shlex

    cleaned = test_execution.without_html_addopts('--html="reports/my report.html" -k "some test" --base-url "a b"')
    assert shlex.split(cleaned) == ["-k", "some test", "--base-url", "a b"]


def test_pyproject_list_preserves_argument_boundaries(tmp_path):
    import shlex

    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = ["-k", "some test", "--html=a b.html"]\n'
    )
    options = test_execution.read_project_addopts(str(tmp_path))
    assert shlex.split(options) == ["-k", "some test", "--html=a b.html"]
