"""
Shared test helpers.

Some environments (restricted sandboxes, locked-down CI images) provide a temp
directory whose newly created children cannot be enumerated or written to again,
which makes pytest's ``tmp_path``/``tmp_path_factory`` unusable. Tests that need a
scratch directory with files in it should use :func:`scratch_dir` instead: it
prefers the process temp area, verifies it is actually usable, and otherwise
falls back to a git-ignored directory under the repository.

The ``runner_server`` fixture provides the *production* Web Runner HTTP surface
(the versioned platform API on the threading server), which browser-facing tests
use instead of instantiating an alternative route handler.
"""
from __future__ import annotations

import contextlib
import itertools
import json
import os
import secrets
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FALLBACK_ROOT = REPO_ROOT / ".run-tmp"
STATIC_ROOT = REPO_ROOT / "lounger" / "web_runner" / "static"

_counter = itertools.count()


def _usable_parent() -> Path:
    """Return a directory that supports create + list + write + delete."""
    try:
        candidate = Path(tempfile.mkdtemp(prefix="lounger-usable-check-"))
        (candidate / "probe").mkdir()
        (candidate / "probe" / "file").write_text("x", encoding="utf-8")
        os.listdir(candidate / "probe")
        shutil.rmtree(candidate, ignore_errors=True)
        return Path(tempfile.gettempdir())
    except OSError:
        FALLBACK_ROOT.mkdir(parents=True, exist_ok=True)
        return FALLBACK_ROOT


@contextlib.contextmanager
def scratch_dir(prefix: str = "scratch"):
    """
    Yield a fresh, writable, enumerable directory; it is removed afterwards.

    ``tempfile.mkdtemp`` is deliberately not used for the directory itself: it
    creates 0o700 directories that a restricted token may not be able to write
    into.
    """
    directory = _usable_parent() / f"{prefix}-{os.getpid()}-{next(_counter)}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def scratch():
    """Fixture form of :func:`scratch_dir`."""
    with scratch_dir("fixture") as directory:
        yield directory


# ── packaged front-end assets ──────────────────────────────────────────────

def shell_assets() -> str:
    """
    Return the runner page and its scripts as one string.

    The served page (``static/index.html``) references ``/static/*.js|css``; tests
    that assert on front-end behaviour need the page *and* the scripts. Reading the
    files directly keeps the assertions tied to what is actually shipped, instead
    of to a second copy inlined for tests.
    """
    parts = []
    for name in ("index.html", "runner.js", "platform.js", "runner.css", "platform.css"):
        parts.append(STATIC_ROOT.joinpath(name).read_text(encoding="utf-8"))
    return "\n".join(parts)


def static_asset(name: str) -> str:
    """Return one packaged front-end asset."""
    return STATIC_ROOT.joinpath(name).read_text(encoding="utf-8")


# ── production HTTP surface ────────────────────────────────────────────────

class RunnerClient:
    """Minimal HTTP client for the runner's versioned API."""

    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, path, method="GET", data=None, auth=True, headers=None, timeout=15):
        head = {"Content-Type": "application/json", **(headers or {})}
        if auth:
            head["X-Lounger-Token"] = self.token
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data or {}).encode() if method != "GET" else None,
            method=method,
            headers=head,
        )
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            return response.status, json.loads(raw) if "application/json" in content_type else raw

    def open_stream(self, run_id, cursor=None, timeout=15):
        """Open the SSE stream for a run (optionally resuming from ``cursor``)."""
        headers = {}
        if cursor is not None:
            headers["Last-Event-ID"] = str(cursor)
        request = urllib.request.Request(f"{self.base}/api/v1/runs/{run_id}/events", headers=headers)
        return urllib.request.urlopen(request, timeout=timeout)

    def open(self, path, token=True, timeout=15, headers=None):
        """Open an arbitrary runner URL (e.g. an artifact) with the session token."""
        head = dict(headers or {})
        if token:
            head["X-Lounger-Token"] = self.token
        request = urllib.request.Request(self.base + path if path.startswith("/") else path, headers=head)
        return urllib.request.urlopen(request, timeout=timeout)


@contextlib.contextmanager
def runner_server(project: Path):
    """Serve the production runner API for ``project`` on an ephemeral port."""
    from lounger.web_runner.api import PlatformHandler
    from lounger.web_runner.context import ProjectContext
    from lounger.web_runner.http_base import RunnerHTTPServer
    from lounger.web_runner.manager import RunManager

    manager = RunManager(ProjectContext.create(str(project)))
    server = RunnerHTTPServer(("127.0.0.1", 0), PlatformHandler)
    server.manager = manager
    server.session_token = secrets.token_urlsafe(32)
    manager.session_token = server.session_token
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = RunnerClient(f"http://127.0.0.1:{server.server_address[1]}", server.session_token)
    try:
        yield client, manager
    finally:
        server.shutdown()
        manager.close()
        server.server_close()
        thread.join(timeout=10)


@pytest.fixture
def runner_project():
    """A minimal runnable project served through the production runner API."""
    with scratch_dir("runner-project") as project:
        (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        (project / "test_demo.py").write_text(
            'def test_ok():\n    print("你好")\n    assert True\n', encoding="utf-8"
        )
        yield project


@pytest.fixture
def runner(runner_project):
    """``(client, manager)`` for the production runner API."""
    with runner_server(runner_project) as pair:
        yield pair


# ── synthetic runs (for log/SSE contracts that need no real pytest run) ────

def make_run(manager, run_id: str, *, state: str = "completed", log_text: str | bytes = "", **extra):
    """
    Create a run record plus its ``output.log``, and return the run dict.

    Used to exercise the streaming/window contracts deterministically, without
    paying for a real pytest subprocess. The log is written in **binary** so the
    file's byte size matches ``log_text`` exactly (text mode would rewrite
    ``\\n`` to ``\\r\\n`` on Windows and break byte-offset assertions).
    """
    item = {
        "id": run_id,
        "task_id": None,
        "state": state,
        "outcome": "passed" if state == "completed" else None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "exit_code": 0,
        "counts": {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0},
        "request": {"selection": {"type": "nodeids", "nodeids": []}, "options": {"verbosity": "quiet", "html_report": False}},
        **extra,
    }
    manager.store.create_run(item)
    directory = manager.directory(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    payload = log_text.encode("utf-8") if isinstance(log_text, str) else log_text
    (directory / "output.log").write_bytes(payload)
    return item


#: Convenience: a valid 32 hex-character run id.
def run_id(seed: str = "a") -> str:
    return (seed * 32)[:32]
