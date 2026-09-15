"""
Tests for streamed-log handling in the web runner.

Guards the log-streaming optimisation:

- **server**: lines live in one authoritative list; every client streams them
  exactly once (no replay/queue duplication) and batched (one event per
  ``_SSE_BATCH_LINES`` lines instead of one event per line);
- **client**: windowed rendering (spacer + translated viewport), rAF-throttled
  flush, fixed line height, follow-the-tail;
- **coexistence**: the Web Runner v2 features (run history, tag filter,
  favourites, run status, concurrency guard) must stay in place — an earlier
  "performance" change silently dropped them.
"""
import contextlib
import json
import threading
import urllib.request
from pathlib import Path

from lounger.web_runner import server as server_mod
from lounger.web_runner.html import _FALLBACK_HTML
from lounger.web_runner.state import _active_runs, _runs_lock

# ── helpers ───────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _serve():
    """Run the real request handler on an ephemeral port."""
    httpd = server_mod._ThreadingHTTPServer(("127.0.0.1", 0), server_mod._RequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post_run(port: int, nodeids=("test_x.py::test_y",)) -> str:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/run",
        data=json.dumps({"nodeids": list(nodeids), "verbosity": "quiet"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as resp:
        return json.loads(resp.read())["run_id"]


def _open_stream(port: int, run_id: str):
    return urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/stream/{run_id}", timeout=10
    )


def _read_events(resp) -> list[dict]:
    events = []
    for raw in resp:
        text = raw.decode("utf-8").strip()
        if not text.startswith("data: "):
            continue
        payload = json.loads(text[len("data: "):])
        events.append(payload)
        if payload.get("done"):
            break
    return events


def _lines_of(events: list[dict]) -> list[str]:
    return [line for event in events if event.get("lines") for line in event["lines"]]


def _forget(run_id: str) -> None:
    with _runs_lock:
        _active_runs.pop(run_id, None)


def _stub_executor(lines, on_run=None, writes_report=False):
    """Return a fake executor that appends ``lines`` then completes."""

    def fake_execute(run_id, nodeids, verbosity="verbose", html_report=False):
        if on_run is not None:
            on_run()
        with _runs_lock:
            info = _active_runs[run_id]
            logs = info["logs"]
            report_path = info.get("report_path")
        for line in lines:
            with _runs_lock:
                logs.append(line)
        if writes_report and html_report and report_path:
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("<html><body>report</body></html>", encoding="utf-8")
        with _runs_lock:
            info["status"] = "completed"
            info["exit_code"] = 0

    return fake_execute


# ── server: batched, exactly-once streaming ───────────────────────────────

def test_sse_stream_batches_log_lines(tmp_path, monkeypatch):
    """Logs arrive in batches and every line is delivered exactly once."""
    lines = [f"log line {i}" for i in range(200)]
    monkeypatch.setattr(server_mod, "_execute_tests", _stub_executor(lines))
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    with _serve() as port:
        run_id = _post_run(port)
        try:
            with _open_stream(port, run_id) as resp:
                events = _read_events(resp)
        finally:
            _forget(run_id)

    batched = [event for event in events if event.get("lines")]
    assert batched, f"expected batched log events, got {events!r}"
    assert any(len(event["lines"]) > 1 for event in batched), "log lines were not batched"
    # exactly once: no replay/queue duplication
    assert _lines_of(events) == lines
    assert events[-1]["done"] is True
    assert events[-1]["exit_code"] == 0


def test_sse_second_client_gets_each_line_once(tmp_path, monkeypatch):
    """Reconnecting (or a second tab) must not duplicate the lines."""
    lines = [f"log line {i}" for i in range(150)]
    monkeypatch.setattr(server_mod, "_execute_tests", _stub_executor(lines))
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    with _serve() as port:
        run_id = _post_run(port)
        try:
            with _open_stream(port, run_id) as first:
                first_events = _read_events(first)
            with _open_stream(port, run_id) as second:
                second_events = _read_events(second)
        finally:
            _forget(run_id)

    assert _lines_of(first_events) == lines
    assert _lines_of(second_events) == lines


def test_sse_streams_lines_produced_after_connect(tmp_path, monkeypatch):
    """Lines produced while a client is attached are streamed live, once."""
    lines = [f"live line {i}" for i in range(30)]
    start = threading.Event()
    monkeypatch.setattr(
        server_mod, "_execute_tests", _stub_executor(lines, on_run=start.wait)
    )
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    with _serve() as port:
        run_id = _post_run(port)
        try:
            with _open_stream(port, run_id) as resp:
                start.set()  # let the worker produce lines now
                events = _read_events(resp)
        finally:
            _forget(run_id)

    assert _lines_of(events) == lines
    assert events[-1]["done"] is True


def test_sse_concurrent_clients_both_get_full_log(tmp_path, monkeypatch):
    """Two attached clients each get the full log.

    The client that sees the run finish first archives it (dropping it from
    memory); the other must still receive the tail from the archived snapshot
    instead of losing lines or duplicating them.
    """
    lines = [f"log line {i}" for i in range(120)]
    start = threading.Event()
    monkeypatch.setattr(
        server_mod, "_execute_tests", _stub_executor(lines, on_run=start.wait)
    )
    monkeypatch.setattr(server_mod.state, "_scan_dir", str(tmp_path))

    collected: dict[str, list] = {}

    def reader(name, resp):
        try:
            collected[name] = _read_events(resp)
        finally:
            resp.close()

    with _serve() as port:
        run_id = _post_run(port)
        try:
            first = _open_stream(port, run_id)
            second = _open_stream(port, run_id)
            threads = [
                threading.Thread(target=reader, args=("first", first)),
                threading.Thread(target=reader, args=("second", second)),
            ]
            for thread in threads:
                thread.start()
            start.set()  # let the worker produce lines with both clients attached
            for thread in threads:
                thread.join(timeout=15)
        finally:
            _forget(run_id)

    assert _lines_of(collected["first"]) == lines
    assert _lines_of(collected["second"]) == lines


def test_sse_batch_size_constant():
    assert server_mod._SSE_BATCH_LINES > 1


# ── client: windowed log rendering ────────────────────────────────────────

def test_html_uses_windowed_log_rendering():
    """Both log panels render through a spacer + translated viewport."""
    assert 'class="log-spacer" id="logSpacer"' in _FALLBACK_HTML
    assert 'class="log-viewport" id="logViewport"' in _FALLBACK_HTML
    assert 'class="log-spacer" id="historyLogSpacer"' in _FALLBACK_HTML
    assert 'class="log-viewport" id="historyLogViewport"' in _FALLBACK_HTML

    assert "function createLogView(" in _FALLBACK_HTML
    assert "const LOG_LINE_HEIGHT = 21;" in _FALLBACK_HTML
    assert "const LOG_OVERSCAN " in _FALLBACK_HTML
    assert "const LOG_MAX_LINES " in _FALLBACK_HTML
    # rAF-throttled flush + frame-scheduled rendering
    assert "requestAnimationFrame(flush)" in _FALLBACK_HTML
    assert "requestAnimationFrame(render)" in _FALLBACK_HTML
    assert "viewport.style.transform = 'translateY('" in _FALLBACK_HTML
    assert "spacer.style.height = (lines.length * LOG_LINE_HEIGHT)" in _FALLBACK_HTML


def test_client_accepts_batched_and_single_line_events():
    """The stream handler accepts the batched shape and the legacy one."""
    assert "Array.isArray(msg.lines) ? msg.lines : (msg.line ? [msg.line] : [])" in _FALLBACK_HTML
    assert "liveLog.push(incoming)" in _FALLBACK_HTML


def test_copy_buttons_use_full_log_not_rendered_window():
    """Copying must use the backing array — innerText holds only the window."""
    assert "liveLog.getText()" in _FALLBACK_HTML
    assert "historyLog.getText()" in _FALLBACK_HTML
    assert r"lines.join('\n')" in _FALLBACK_HTML


def test_follow_tail_only_when_at_bottom():
    assert "function atBottom()" in _FALLBACK_HTML
    assert "follow = atBottom();" in _FALLBACK_HTML
    assert "const LOG_FOLLOW_SLACK = 24;" in _FALLBACK_HTML


def test_history_detail_reuses_windowed_view():
    assert "historyLog.setLines(data.logs || [])" in _FALLBACK_HTML


# ── coexistence: optimisation must not drop v2 features ───────────────────

def test_virtualization_keeps_v2_features():
    """Regression guard: the log optimisation must not remove v2 features."""
    # run history
    assert 'id="tabHistory"' in _FALLBACK_HTML
    assert "async function loadHistory()" in _FALLBACK_HTML
    assert "async function viewHistoryRun(" in _FALLBACK_HTML
    assert "async function deleteHistoryRun(" in _FALLBACK_HTML
    assert "/api/history" in _FALLBACK_HTML
    # tag filter + favourites
    assert 'id="tagBar"' in _FALLBACK_HTML
    assert "FAVORITES_KEY" in _FALLBACK_HTML
    assert "tag-chip" in _FALLBACK_HTML
    # run status + verbosity + sidebar + copy/clear
    assert 'id="runCounter"' in _FALLBACK_HTML
    assert "updateRunStatus()" in _FALLBACK_HTML
    assert "setRunButtonsDisabled(" in _FALLBACK_HTML
    assert "setVerbosity(" in _FALLBACK_HTML
    assert 'id="sidebarResizer"' in _FALLBACK_HTML
    assert 'id="copyBtn"' in _FALLBACK_HTML
    assert 'id="clearBtn"' in _FALLBACK_HTML


def test_server_keeps_concurrency_guard_and_history_api():
    """The server still guards concurrent runs and serves run history."""
    import inspect

    source = inspect.getsource(server_mod._RequestHandler)
    assert "有任务正在运行" in source
    assert "/api/history" in source
    assert "do_DELETE" in source
