"""
Tests for streamed-log handling in the Web Runner.

These exercise the **production** surface only: the versioned platform API
(``/api/v1/runs/{id}/events``, ``/logs``) served by
:class:`lounger.web_runner.api.PlatformHandler`, backed by ``RunManager`` and its
SQLite store. The runner used to carry a second, unreachable implementation
(in-memory log lists + ``reports/runs/*.json``) that these tests covered instead;
it has been removed, so the assertions below guard the path that actually serves
the browser.
"""
import json
import threading

from tests.conftest import make_run, run_id, shell_assets

# ── helpers ───────────────────────────────────────────────────────────────

def _read_events(response, limit=500):
    """Read SSE frames until ``done`` (or the stream ends)."""
    events = []
    for raw in response:
        text = raw.decode("utf-8").strip()
        if not text.startswith("data: "):
            continue
        payload = json.loads(text[len("data: "):])
        events.append(payload)
        if payload.get("done") or len(events) >= limit:
            break
    return events


def _read_stream(response, limit=500):
    """Read the whole response body, returning ``(events, last_cursor)``.

    The body is consumed completely: stopping mid-response would leave bytes in
    the socket, which is a client bug rather than a server one.
    """
    events: list[dict] = []
    last_cursor = 0
    body = response.read().decode("utf-8")
    for block in body.split("\n\n"):
        cursor_line = next((line for line in block.splitlines() if line.startswith("id: ")), None)
        if cursor_line:
            last_cursor = int(cursor_line[len("id: "):])
        payload_line = next((line for line in block.splitlines() if line.startswith("data: ")), None)
        if payload_line:
            events.append(json.loads(payload_line[len("data: "):]))
        if len(events) >= limit:
            break
    return events, last_cursor


def _text_of(events) -> str:
    return "".join(event.get("text", "") for event in events)


def _lines_of(events) -> list[str]:
    lines: list[str] = []
    for event in events:
        for chunk in event.get("lines") or []:
            lines.extend(chunk.splitlines())
    return lines


# ── SSE against the production endpoint ───────────────────────────────────

def test_sse_stream_delivers_the_whole_log_once(runner):
    """Every byte of the log is delivered, exactly once, then ``done``."""
    client, manager = runner
    lines = [f"log line {i}" for i in range(200)]
    identifier = run_id("b")
    make_run(manager, identifier, log_text="\n".join(lines) + "\n")

    with client.open_stream(identifier) as response:
        events = _read_events(response)

    assert _text_of(events).splitlines() == lines
    assert _lines_of(events) == lines
    assert events[-1]["done"] is True
    assert events[-1]["exit_code"] == 0


def test_sse_emits_cursors_so_a_client_can_resume(runner):
    """The stream carries ``id:`` cursors; resuming from one replays nothing new."""
    client, manager = runner
    text = "".join(f"line {i}\n" for i in range(50))
    identifier = run_id("d")
    make_run(manager, identifier, log_text=text)

    with client.open_stream(identifier) as response:
        events, cursor = _read_stream(response)
    assert cursor > 0, "the stream must publish cursors"
    assert "line 49" in _text_of(events)

    # resume from the reported cursor: the log is drained, only ``done`` follows
    with client.open_stream(identifier, cursor=cursor) as response:
        resumed, _ = _read_stream(response)
    assert "line 49" not in _text_of(resumed)
    assert resumed[-1]["done"] is True


def test_sse_replays_from_an_earlier_cursor(runner):
    """Resuming mid-log replays exactly the tail from that byte offset."""
    client, manager = runner
    text = "".join(f"line {i}\n" for i in range(50))
    identifier = run_id("0")
    make_run(manager, identifier, log_text=text)

    midpoint = len(text.encode("utf-8")) // 2
    with client.open_stream(identifier, cursor=midpoint) as response:
        events, _ = _read_stream(response)

    replayed = _text_of(events)
    assert "line 49" in replayed
    assert "line 0\n" not in replayed, "bytes before the cursor must not be replayed"
    assert len(replayed) < len(text), "resuming mid-log must not resend the whole file"


def test_sse_handles_multibyte_log_text(runner):
    """A UTF-8 boundary must not split a character (the runner backtracks)."""
    client, manager = runner
    text = "".join(f"第{i}行 你好\n" for i in range(40))
    identifier = run_id("e")
    make_run(manager, identifier, log_text=text)

    with client.open_stream(identifier) as response:
        events = _read_events(response)

    collected = _text_of(events)
    assert "第39行 你好" in collected
    assert "\ufffd" not in collected, "a character was split across a read boundary"


def test_sse_two_clients_each_receive_the_full_log(runner):
    """Two attached clients must both get everything, with no duplication."""
    client, manager = runner
    lines = [f"log line {i}" for i in range(150)]
    identifier = run_id("f")
    make_run(manager, identifier, log_text="\n".join(lines) + "\n")

    collected: dict[str, list] = {}

    def reader(name):
        with client.open_stream(identifier) as response:
            collected[name] = _read_events(response)

    threads = [threading.Thread(target=reader, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not any(thread.is_alive() for thread in threads), "a stream did not finish"
    assert _lines_of(collected["first"]) == lines
    assert _lines_of(collected["second"]) == lines


def test_sse_streams_lines_that_appear_while_attached(runner):
    """A live run's new output is pushed to an attached client, once."""
    client, manager = runner
    identifier = run_id("1")
    make_run(manager, identifier, state="running", log_text="first\n")

    events: list[dict] = []

    def reader():
        with client.open_stream(identifier) as response:
            for raw in response:
                text = raw.decode("utf-8").strip()
                if not text.startswith("data: "):
                    continue
                payload = json.loads(text[len("data: "):])
                events.append(payload)
                if payload.get("done"):
                    return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    # wait for the first batch, then append output and wake the streams
    for _ in range(200):
        if _text_of(events):
            break
        threading.Event().wait(0.02)
    log_path = manager.directory(identifier) / "output.log"
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("live line\n")
    manager.events.publish()

    for _ in range(200):
        if "live line" in _text_of(events):
            break
        threading.Event().wait(0.02)

    manager.store.update_run(identifier, {"state": "completed", "outcome": "passed"})
    manager.events.publish()
    thread.join(timeout=15)

    assert "first" in _text_of(events)
    assert "live line" in _text_of(events)
    assert events[-1]["done"] is True


def test_log_endpoint_supports_tail_and_before_windows(runner):
    """The paginated log window (tail + upward paging) is the production API."""
    client, manager = runner
    # larger than one 64 KiB window, so the tail window really starts mid-file
    text = "".join(f"line {i:05d} {'x' * 60}\n" for i in range(2000))
    identifier = run_id("2")
    make_run(manager, identifier, log_text=text)

    status, tail = client.call(f"/api/v1/runs/{identifier}/logs?tail=1")
    assert status == 200
    assert "line 01999" in tail["text"]
    assert tail["start"] > 0, "a log bigger than the window must not start at byte 0"
    assert len(tail["text"].encode("utf-8")) <= 65536

    status, earlier = client.call(f"/api/v1/runs/{identifier}/logs?before={tail['start']}")
    assert status == 200
    assert earlier["cursor"] <= tail["start"]
    # paging back must not replay the tail window
    assert "line 01999" not in earlier["text"]
    # and it must reach back further than the tail window started
    assert earlier["start"] < tail["start"]


def test_log_endpoint_returns_the_whole_log_when_it_fits(runner):
    """A short log needs no paging: the window covers it entirely."""
    client, manager = runner
    identifier = run_id("5")
    make_run(manager, identifier, log_text="only line\n")

    status, window = client.call(f"/api/v1/runs/{identifier}/logs?tail=1")

    assert status == 200
    assert window["start"] == 0
    assert window["text"].splitlines() == ["only line"]
    assert window["size"] == len(b"only line\n")


def test_streaming_a_finished_run_ends_with_done(runner):
    """A terminal run streams its log and closes the connection politely."""
    client, manager = runner
    identifier = run_id("3")
    make_run(manager, identifier, state="completed", log_text="tail line\n")

    with client.open_stream(identifier) as response:
        events = _read_events(response)

    assert "tail line" in _text_of(events)
    assert events[-1]["done"] is True


# ── front-end log rendering (asserted against the shipped assets) ─────────

def test_shell_uses_windowed_log_rendering():
    """Both log panels render through a spacer + translated viewport."""
    assets = shell_assets()
    assert 'class="log-spacer" id="logSpacer"' in assets
    assert 'class="log-viewport" id="logViewport"' in assets
    assert 'class="log-spacer" id="historyLogSpacer"' in assets
    assert 'class="log-viewport" id="historyLogViewport"' in assets
    assert "function createLogView(" in assets
    assert "const LOG_LINE_HEIGHT = 21;" in assets
    assert "const LOG_OVERSCAN " in assets
    assert "const LOG_MAX_LINES " in assets
    assert "requestAnimationFrame(flush)" in assets
    assert "requestAnimationFrame(render)" in assets
    assert "viewport.style.transform = 'translateY('" in assets
    assert "spacer.style.height = (lines.length * LOG_LINE_HEIGHT)" in assets


def test_front_end_accepts_batched_and_single_line_events():
    assets = shell_assets()
    assert "Array.isArray(msg.lines) ? msg.lines : (msg.line ? [msg.line] : [])" in assets
    assert "liveLog.push(incoming)" in assets


def test_copy_buttons_use_the_backing_log_not_the_window():
    assets = shell_assets()
    assert "liveLog.getText()" in assets
    assert "historyLog.getText()" in assets
    assert r"lines.join('\n')" in assets


def test_follow_tail_only_when_at_bottom():
    assets = shell_assets()
    assert "function atBottom()" in assets
    assert "follow = atBottom();" in assets
    assert "const LOG_FOLLOW_SLACK = 24;" in assets


def test_virtualization_keeps_v2_features():
    """Regression guard: the log optimisation must not remove v2 features."""
    assets = shell_assets()
    assert 'id="tabHistory"' in assets
    assert "async function loadHistory()" in assets
    assert "async function viewHistoryRun(" in assets
    assert "/api/history" in assets
    assert 'id="tagBar"' in assets
    assert "FAVORITES_KEY" in assets
    assert "tag-chip" in assets
    assert 'id="runCounter"' in assets
    assert "updateRunStatus()" in assets
    assert "setRunButtonsDisabled(" in assets
    assert "setVerbosity(" in assets
    assert 'id="sidebarResizer"' in assets
    assert 'id="copyBtn"' in assets
    assert 'id="clearBtn"' in assets


def test_handler_exposes_the_production_route_surface():
    """The single handler serves both the versioned API and the compatibility layer."""
    from lounger.web_runner.api import PlatformHandler

    source = inspect_source(PlatformHandler)
    assert "do_GET" in source and "do_POST" in source and "do_PATCH" in source and "do_DELETE" in source
    assert "/api/v1/" in source or "versioned" in source
    assert "/api/history" in source


def inspect_source(obj) -> str:
    import inspect

    return inspect.getsource(obj)
