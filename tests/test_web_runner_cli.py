"""
Tests for the web runner entry point: URL building, auto-opening the runner in
the default browser, and the startup edge cases (busy port / no browser).
"""
import errno
import socket
import threading
import time

import pytest
from click.testing import CliRunner

import lounger.web_runner as web_runner_mod
from lounger import cli
from lounger.web_runner import browser_url, main


class _FakeServer:
    """Stands in for _ThreadingHTTPServer: records the bind address."""

    last = None

    def __init__(self, address, handler):
        self.address = address
        self.server_address = address
        self.handler = handler
        self.served = False
        self.shutdown_called = False
        _FakeServer.last = self

    def serve_forever(self):
        self.served = True

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def fake_server(monkeypatch):
    """Patch the HTTP server; tests assert on ``fake_server.last``."""
    _FakeServer.last = None
    monkeypatch.setattr(web_runner_mod, "_ThreadingHTTPServer", _FakeServer)
    monkeypatch.delenv("CI", raising=False)
    return _FakeServer


def _record_browser(monkeypatch):
    """Patch webbrowser.open; return the list it appends URLs to."""
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    return opened


# ── URL building ──────────────────────────────────────────────────────────

def test_browser_url_keeps_regular_hosts():
    assert browser_url("127.0.0.1", 5000) == "http://127.0.0.1:5000"
    assert browser_url("localhost", 8080) == "http://localhost:8080"


def test_browser_url_maps_wildcard_hosts():
    """A wildcard bind address is not a usable URL — map it to loopback."""
    assert browser_url("0.0.0.0", 5001) == "http://127.0.0.1:5001"
    assert browser_url("::", 5001) == "http://127.0.0.1:5001"
    assert browser_url("", 5001) == "http://127.0.0.1:5001"


def test_browser_url_brackets_ipv6_literals():
    assert browser_url("::1", 5002) == "http://[::1]:5002"


# ── auto-open behaviour ───────────────────────────────────────────────────

def test_main_opens_runner_in_default_browser(fake_server, monkeypatch):
    opened_event = threading.Event()
    opened: list[str] = []

    def fake_open(url):
        opened.append(url)
        opened_event.set()
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)

    main(host="127.0.0.1", port=5055, scan_dir=".")

    assert opened_event.wait(5), "the browser was not opened"
    assert opened == ["http://127.0.0.1:5055"]
    assert fake_server.last.address == ("127.0.0.1", 5055)
    assert fake_server.last.served is True


def test_main_opens_loopback_url_when_bound_to_wildcard(fake_server, monkeypatch):
    opened_event = threading.Event()
    opened: list[str] = []

    def fake_open(url):
        opened.append(url)
        opened_event.set()
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)

    main(host="0.0.0.0", port=5056, scan_dir=".")

    assert opened_event.wait(5)
    assert opened == ["http://127.0.0.1:5056"]
    # the real bind address is still used for the server
    assert fake_server.last.address == ("0.0.0.0", 5056)


def test_main_can_disable_browser(fake_server, monkeypatch):
    opened = _record_browser(monkeypatch)

    main(host="127.0.0.1", port=5057, scan_dir=".", open_browser=False)

    assert opened == []
    assert fake_server.last.served is True


def test_main_skips_browser_in_ci(fake_server, monkeypatch):
    """CI has no display — auto-open is skipped even when enabled."""
    opened = _record_browser(monkeypatch)
    monkeypatch.setenv("CI", "true")

    main(host="127.0.0.1", port=5058, scan_dir=".")

    assert opened == []
    assert fake_server.last.served is True


# ── edge case: no browser installed ───────────────────────────────────────

def test_browser_open_failure_does_not_stop_runner(fake_server, monkeypatch):
    """A browser launch that raises must never break the runner."""
    def boom(url):
        raise RuntimeError("no display")

    monkeypatch.setattr("webbrowser.open", boom)

    main(host="127.0.0.1", port=5059, scan_dir=".")

    assert fake_server.last.served is True


def test_open_browser_hints_when_none_available(monkeypatch):
    """`webbrowser.open` returning False (no browser) logs a hint, no crash."""
    from loguru import logger

    messages: list[str] = []
    sink = logger.add(
        lambda message: messages.append(message.record["message"]),
        format="{message}",
    )
    try:
        monkeypatch.setattr("webbrowser.open", lambda url: False)

        web_runner_mod._open_browser("http://127.0.0.1:5000")

        deadline = time.time() + 5
        while time.time() < deadline and not any("No browser" in m for m in messages):
            time.sleep(0.05)
    finally:
        logger.remove(sink)

    assert any("No browser could be opened automatically" in m for m in messages), messages


def test_main_keeps_serving_without_browser(fake_server, monkeypatch):
    """No usable browser → the runner still serves (the address is logged)."""
    monkeypatch.setattr("webbrowser.open", lambda url: False)

    main(host="127.0.0.1", port=5060, scan_dir=".")

    assert fake_server.last.served is True


# ── edge case: port already in use ────────────────────────────────────────

def test_main_falls_back_when_port_is_busy(tmp_path, monkeypatch):
    """A busy port no longer raises: the runner moves to the next free port."""
    real_server = web_runner_mod._ThreadingHTTPServer

    class RecordingServer(real_server):
        last = None

        def __init__(self, address, handler):
            super().__init__(address, handler)
            RecordingServer.last = self

        def serve_forever(self):
            pass

    monkeypatch.setattr(web_runner_mod, "_ThreadingHTTPServer", RecordingServer)
    monkeypatch.delenv("CI", raising=False)
    opened = _record_browser(monkeypatch)

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    busy_port = blocker.getsockname()[1]
    blocker.listen(1)
    try:
        main(host="127.0.0.1", port=busy_port, scan_dir=str(tmp_path))
    finally:
        blocker.close()
        RecordingServer.last.server_close()

    bound_port = RecordingServer.last.server_address[1]
    assert bound_port > busy_port, "should have moved to another port"
    # the browser (and the banner) must use the port actually bound
    assert opened == [f"http://127.0.0.1:{bound_port}"]


def test_port_zero_uses_os_assigned_port(monkeypatch):
    """port=0 means 'let the OS choose' and is reported as the real port."""
    class PortZeroServer:
        last = None

        def __init__(self, address, handler):
            self.address = address
            self.server_address = (address[0], 51234)  # OS assigned
            PortZeroServer.last = self

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

    monkeypatch.setattr(web_runner_mod, "_ThreadingHTTPServer", PortZeroServer)
    monkeypatch.delenv("CI", raising=False)
    opened = _record_browser(monkeypatch)

    main(host="127.0.0.1", port=0, scan_dir=".")

    assert opened == ["http://127.0.0.1:51234"]


def test_main_exits_cleanly_when_no_port_is_free(monkeypatch):
    """Every candidate busy → friendly exit, not an OSError traceback."""
    class AlwaysBusy:
        def __init__(self, address, handler):
            raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(web_runner_mod, "_ThreadingHTTPServer", AlwaysBusy)
    monkeypatch.setattr(web_runner_mod, "_PORT_ATTEMPTS", 2)
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        main(host="127.0.0.1", port=5000, scan_dir=".")

    assert excinfo.value.code == 1


def test_main_exits_cleanly_on_other_bind_errors(monkeypatch):
    """e.g. permission denied on a privileged port — same clean exit."""
    class Denied:
        def __init__(self, address, handler):
            raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(web_runner_mod, "_ThreadingHTTPServer", Denied)
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        main(host="127.0.0.1", port=80, scan_dir=".")

    assert excinfo.value.code == 1


# ── CLI wiring ────────────────────────────────────────────────────────────

def test_runner_cli_opens_browser_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "lounger.web_runner.main",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(cli.runner, ["--port", "6001", "--project", "myproj"])

    assert result.exit_code == 0, result.output
    assert captured == {
        "host": "127.0.0.1",
        "port": 6001,
        "scan_dir": "myproj",
        "open_browser": True,
    }


def test_runner_cli_no_browser_flag(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "lounger.web_runner.main",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(cli.runner, ["--no-browser"])

    assert result.exit_code == 0, result.output
    assert captured["open_browser"] is False
