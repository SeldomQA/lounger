"""HTTP server, request handler, and SSE streaming."""

import http.server
import json
import queue
import threading
import uuid
from urllib.parse import urlparse

from lounger.services.test_execution import (
    delete_archived_run,
    list_archived_runs,
    load_archived_run,
)

from . import state
from .collect import get_test_cases
from .executor import _execute_tests, archive_finished_runs
from .html import _FALLBACK_HTML
from .state import _active_runs, _runs_lock
from .tree import _build_case_tree

# HTML page cache (module-local)
_HTML_PAGE: str | None = None


def _load_html() -> str:
    """Load the HTML page (lazy, once)."""
    global _HTML_PAGE
    if _HTML_PAGE is None:
        _HTML_PAGE = _FALLBACK_HTML
    return _HTML_PAGE


class _RequestHandler(http.server.BaseHTTPRequestHandler):
    """Single handler for all routes."""

    def log_message(self, format, *args):
        if self.path.startswith("/api/stream"):
            return
        super().log_message(format, *args)

    # ── routing ──

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_html()
        elif path == "/api/cases":
            self._serve_json(get_test_cases())
        elif path == "/api/tree":
            cases = get_test_cases()
            tree = _build_case_tree(cases, state._scan_dir)
            self._serve_json({"tree": tree, "flat": cases})
        elif path == "/api/runs":
            self._serve_runs()
        elif path == "/api/history":
            self._serve_history_list()
        elif path.startswith("/api/history/"):
            run_id = path.split("/")[-1]
            self._serve_history_detail(run_id)
        elif path.startswith("/api/stream/"):
            self._serve_stream(path.split("/")[-1])
        else:
            self._serve_404()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/run":
            self._handle_run()
        elif path == "/api/run-all":
            self._handle_run_all()
        elif path == "/api/refresh":
            self._serve_refresh()
        else:
            self._serve_404()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path.startswith("/api/history/"):
            run_id = path.split("/")[-1]
            self._handle_delete_history(run_id)
        else:
            self._serve_404()

    # ── handlers ──

    def _serve_html(self):
        html = _load_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_runs(self):
        with _runs_lock:
            runs = {}
            for rid, info in _active_runs.items():
                runs[rid] = {
                    "status": info["status"],
                    "nodeids": info["nodeids"],
                    "log_count": len(info["logs"]),
                    "exit_code": info.get("exit_code"),
                    "started_at": info.get("started_at"),
                }
        self._serve_json({
            "active": runs,
            "active_count": state.active_run_count(),
            "running": state.is_any_run_active(),
        })

    def _serve_refresh(self):
        state.clear_caches()
        cases = get_test_cases()
        self._serve_json({"refreshed": True, "count": len(cases)})

    # ── history handlers ──

    def _serve_history_list(self):
        runs = list_archived_runs(state._scan_dir)
        self._serve_json(runs)

    def _serve_history_detail(self, run_id: str):
        data = load_archived_run(state._scan_dir, run_id)
        if data is None:
            self._serve_404()
            return
        self._serve_json(data)

    def _handle_delete_history(self, run_id: str):
        ok = delete_archived_run(state._scan_dir, run_id)
        self._serve_json({"deleted": ok, "run_id": run_id})

    def _serve_404(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Not Found")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    def _handle_run(self):
        body = self._read_body()
        nodeids = body.get("nodeids", [])
        if not nodeids:
            self._serve_json({"error": "No test cases selected"})
            return

        if state.is_any_run_active():
            self._serve_json({"error": "有任务正在运行，请等待完成后再试"})
            return

        verbosity = body.get("verbosity", "verbose")
        run_id = uuid.uuid4().hex[:8]
        self._start_run_with_id(run_id, nodeids, verbosity)

    def _handle_run_all(self):
        cases = get_test_cases()
        all_nodeids = [c["nodeid"] for c in cases if c.get("nodeid")]
        if not all_nodeids:
            self._serve_json({"error": "No test cases found"})
            return

        if state.is_any_run_active():
            self._serve_json({"error": "有任务正在运行，请等待完成后再试"})
            return

        body = self._read_body()
        verbosity = body.get("verbosity", "verbose")
        run_id = uuid.uuid4().hex[:8]
        self._start_run_with_id(run_id, all_nodeids, verbosity)

    def _start_run_with_id(self, run_id: str, nodeids: list[str], verbosity: str = "verbose"):
        """Start a run immediately (assumes concurrency check passed)."""
        log_queue: queue.Queue = queue.Queue()

        with _runs_lock:
            _active_runs[run_id] = {
                "queue": log_queue,
                "status": "running",
                "logs": [],
                "nodeids": nodeids,
                "exit_code": None,
                "started_at": __import__("time").time(),
            }

        t = threading.Thread(
            target=_execute_tests,
            args=(run_id, nodeids, verbosity),
            daemon=True,
        )
        t.start()
        self._serve_json({"run_id": run_id, "count": len(nodeids), "status": "running"})

    # ── SSE streaming ──

    def _serve_stream(self, run_id: str):
        with _runs_lock:
            run_info = _active_runs.get(run_id)

        if run_info is None:
            self._serve_404()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        log_queue = run_info["queue"]
        sent_count = 0

        with _runs_lock:
            existing = list(run_info["logs"])

        try:
            for line in existing[sent_count:]:
                self._sse_event({"line": line})
                sent_count += 1

            while True:
                try:
                    line = log_queue.get(timeout=1)
                    self._sse_event({"line": line})
                    sent_count += 1
                except queue.Empty:
                    with _runs_lock:
                        status = run_info["status"]
                    if status in ("completed", "error"):
                        self._sse_event({
                            "line": "",
                            "done": True,
                            "exit_code": run_info.get("exit_code", -1),
                            "status": status,
                        })
                        # archive finished runs to keep memory bounded (3.8 §1)
                        archive_finished_runs()
                        break
                    self._sse_event({"heartbeat": True})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _sse_event(self, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()


class _ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
