"""
Tests for the HTML report feature of the web runner:

- the report checkbox is sent with the run request and controls whether pytest
  writes a report (including overriding ``--html`` from the project's pytest.ini);
- a finished run exposes its report, served over HTTP so it can be opened in a
  new browser tab (``file://`` links are blocked from an ``http://`` page);
- run history keeps each run's own report path.

The HTTP assertions run against the production platform API
(``/api/v1/runs/{id}/artifacts/...``). They used to run against a second,
unreachable route handler that kept its own in-memory run model.
"""

import json
import shlex

import pytest

from lounger.services import test_execution
from tests.conftest import make_run, run_id, shell_assets

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


# ── platform API: serving the report over HTTP ────────────────────────────


def test_report_artifact_is_served_with_its_assets(runner_project):
    """A finished run's report (and relative assets) are reachable over HTTP."""
    from tests.conftest import runner_server

    with runner_server(runner_project) as (client, manager):
        identifier = run_id("a")
        directory = manager.directory(identifier)
        (directory / "html" / "assets").mkdir(parents=True)
        (directory / "html" / "report.html").write_text(
            '<html><head><link rel="stylesheet" href="assets/style.css"></head>'
            "<body>lounger report</body></html>",
            encoding="utf-8",
        )
        (directory / "html" / "assets" / "style.css").write_text("body{color:red}", encoding="utf-8")
        make_run(manager, identifier, report_path="html/report.html")

        status, run = client.call(f"/api/v1/runs/{identifier}")
        assert status == 200 and run["report_path"] == "html/report.html"

        with client.open(f"/api/v1/runs/{identifier}/artifacts/html/report.html") as response:
            assert response.status == 200
            assert b"lounger report" in response.read()

        with client.open(f"/api/v1/runs/{identifier}/artifacts/html/assets/style.css") as response:
            assert response.status == 200
            assert "text/css" in response.headers["Content-Type"]
            assert response.read() == b"body{color:red}"


def test_report_artifact_rejects_unknown_run(runner):
    client, _ = runner

    status, error = client.call("/api/v1/runs/" + run_id("9") + "/artifacts/html/report.html")

    assert status == 404
    assert error["error"]["code"] == "not_found"


def test_report_artifact_blocks_path_traversal(runner_project):
    """A crafted relative path must not escape the run directory."""
    from tests.conftest import runner_server

    with runner_server(runner_project) as (client, manager):
        identifier = run_id("8")
        make_run(manager, identifier)
        secret = runner_project / "secret.txt"
        secret.write_text("top secret", encoding="utf-8")

        for attempt in (
            "html/../../secret.txt",
            "../../secret.txt",
            "..%2F..%2Fsecret.txt",
        ):
            status, _ = client.call(f"/api/v1/runs/{identifier}/artifacts/{attempt}")
            assert status == 404, f"traversal via {attempt!r} was not blocked"


def test_done_event_carries_the_report_url(runner_project):
    """The stream's terminal event advertises the artifact URL for the toggle."""
    from tests.conftest import runner_server

    with runner_server(runner_project) as (client, manager):
        identifier = run_id("7")
        directory = manager.directory(identifier)
        (directory / "html").mkdir(parents=True)
        (directory / "html" / "report.html").write_text("<html>report</html>", encoding="utf-8")
        make_run(manager, identifier, state="completed", report_path="html/report.html")

        with client.open_stream(identifier) as response:
            events = []
            for raw in response:
                text = raw.decode("utf-8").strip()
                if text.startswith("data: "):
                    payload = json.loads(text[len("data: "):])
                    events.append(payload)
                    if payload.get("done"):
                        break

        expected = f"/api/v1/runs/{identifier}/artifacts/html/report.html"
        assert events[-1]["done"] is True
        assert events[-1]["report_url"] == expected

        with client.open(events[-1]["report_url"]) as response:
            assert b"report" in response.read()


def test_run_without_a_report_has_no_report_url(runner):
    client, manager = runner
    identifier = run_id("6")
    make_run(manager, identifier, state="completed", report_path=None)

    with client.open_stream(identifier) as response:
        events = []
        for raw in response:
            text = raw.decode("utf-8").strip()
            if text.startswith("data: "):
                payload = json.loads(text[len("data: "):])
                events.append(payload)
                if payload.get("done"):
                    break

    assert events[-1]["done"] is True
    assert events[-1]["report_url"] is None


# ── client UI ─────────────────────────────────────────────────────────────


def test_html_has_report_toggle_and_button():
    assets = shell_assets()
    assert 'id="reportToggle"' in assets
    assert 'id="reportGroup"' in assets
    assert 'id="reportBtn"' in assets
    assert "REPORT_ENABLED_KEY" in assets
    assert "lounger.webRunner.reportEnabled" in assets
    assert "function setReportEnabled(" in assets
    assert "function showReportButton(" in assets
    assert "function openReport(" in assets
    # the request carries the checkbox state, the done event drives the button
    assert "report: reportEnabled" in assets
    assert "showReportButton(msg.report_url || null)" in assets
    assert "window.open(currentReportUrl, '_blank'" in assets
    # history detail can open the archived run's report too
    assert 'id="historyReportBtn"' in assets
    assert "function openHistoryReport(" in assets


def test_report_toggle_preserves_quoted_project_options():
    cleaned = test_execution.without_html_addopts('--html="reports/my report.html" -k "some test" --base-url "a b"')
    assert shlex.split(cleaned) == ["-k", "some test", "--base-url", "a b"]


def test_pyproject_list_preserves_argument_boundaries(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = ["-k", "some test", "--html=a b.html"]\n'
    )
    options = test_execution.read_project_addopts(str(tmp_path))
    assert shlex.split(options) == ["-k", "some test", "--html=a b.html"]
