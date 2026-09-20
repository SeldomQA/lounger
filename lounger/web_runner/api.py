"""Versioned platform API and compatibility routes for the original runner."""

from __future__ import annotations

import json
import mimetypes
import secrets
import sqlite3
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .manager import ANSI, validate_definition
from .server import _RequestHandler
from .storage import TERMINAL, Problem
from .tree import _build_case_tree


class PlatformHandler(_RequestHandler):
    server: Any

    @property
    def manager(self):
        return self.server.manager

    def reply(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 2_000_000:
            raise Problem("invalid_body", "Request is too large", 413)
        result = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(result, dict):
            raise Problem("invalid_body", "Expected JSON object")
        return result

    def authorize(self):
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            raise Problem("forbidden", "Cross-origin mutations are not allowed", 403)
        token = self.headers.get("X-Lounger-Token", "")
        if not secrets.compare_digest(token, self.server.session_token):
            raise Problem("forbidden", "Refresh the runner page to obtain a session token", 403)

    @staticmethod
    def pagination(query):
        page, size = int(query.get("page", "1")), int(query.get("page_size", "20"))
        if page < 1 or not 1 <= size <= 100:
            raise Problem("invalid_pagination", "page >= 1 and page_size between 1 and 100 required")
        return dict(page=page, page_size=size)

    def dispatch(self, method):
        try:
            host = urlparse("//" + self.headers.get("Host", "")).hostname
            allowed = {"localhost", "127.0.0.1", "::1", self.server.server_address[0]}
            if host not in allowed:
                raise Problem("forbidden", "Host is not a runner bind address", 403)
            parsed = urlparse(self.path)
            path = unquote(parsed.path).rstrip("/") or "/"
            query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            if method != "GET":
                self.authorize()
            if path == "/" and method == "GET":
                page = files("lounger.web_runner").joinpath("static/index.html").read_text(encoding="utf-8")
                page = page.replace(
                    "</head>", '<meta name="lounger-token" content="' + self.server.session_token + '"></head>'
                )
                return self.send_bytes(page.encode(), "text/html; charset=utf-8")
            if path.startswith("/static/") and method == "GET":
                name = path.removeprefix("/static/")
                if name not in ("runner.js", "runner.css", "platform.js", "platform.css"):
                    raise Problem("not_found", "Static resource not found", 404)
                resource = files("lounger.web_runner").joinpath("static").joinpath(name)
                return self.send_bytes(
                    resource.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream"
                )
            if path.startswith("/api/v1/"):
                return self.versioned(method, path[8:].split("/"), query)
            return self.legacy(method, path, query)
        except Problem as exc:
            self.reply({"error": {"code": exc.code, "message": str(exc), "details": exc.details}}, exc.status)
        except (ValueError, TypeError, KeyError) as exc:
            self.reply({"error": {"code": "invalid_request", "message": str(exc)}}, 400)
        except (sqlite3.Error, OSError) as exc:
            if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                return
            self.reply({"error": {"code": "storage_unavailable", "message": str(exc)}}, 503)

        finally:
            if method != "GET":
                self.manager.events.publish()

    def send_bytes(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        # xhtml uses sessionStorage; block API requests, frames and form writes instead.
        self.send_header(
            "Content-Security-Policy",
            "sandbox allow-scripts allow-same-origin; default-src 'self' data: 'unsafe-inline'; "
            "connect-src 'none'; frame-src 'none'; object-src 'none'; worker-src 'none'; "
            "form-action 'none'; base-uri 'none'",
        )
        self.end_headers()
        with path.open("rb") as source:
            while chunk := source.read(65536):
                self.wfile.write(chunk)

    def versioned(self, method, parts, query):
        manager, store = self.manager, self.manager.store
        if parts == ["project"] and method == "GET":
            return self.reply(manager.project())
        if parts == ["project", "events"] and method == "GET":
            return self.project_stream()
        if parts in (["cases", "tree"], ["cases", "refresh"]):
            if (parts[-1] == "tree" and method == "GET") or (parts[-1] == "refresh" and method == "POST"):
                cases = manager.cases(refresh=method == "POST")
                return self.reply(dict(flat=cases, tree=_build_case_tree(cases, str(manager.context.root))))
        if parts == ["tasks", "validate"] and method == "POST":
            return self.reply(manager.validate_tasks(self.body().get("task_ids")))
        if parts == ["tasks"]:
            if method == "GET":
                return self.reply(store.tasks(**self.pagination(query), search=query.get("search", "")))
            if method == "POST":
                return self.reply(store.save_task(validate_definition(self.body(), task=True)), 201)
        if parts[0] == "tasks" and len(parts) >= 2:
            task_id = parts[1]
            if len(parts) == 2:
                if method == "GET":
                    return self.reply(store.task(task_id))
                if method == "PATCH":
                    patch = self.body()
                    data = {**store.task(task_id), **patch}
                    body_revision = patch.get("revision")
                    if body_revision is None:
                        raise Problem("revision_required", "revision is required")
                    return self.reply(store.save_task(validate_definition(data, task=True), task_id))
                if method == "DELETE":
                    store.delete_task(task_id)
                    return self.reply({"deleted": True})
            if parts[2:] == ["runs"] and method == "POST":
                data = self.body()
                return self.reply(
                    manager.start(
                        store.task(task_id),
                        task_id,
                        self.headers.get("Idempotency-Key"),
                        verbosity_override=data.get("verbosity", "quiet"),
                    ),
                    202,
                )
        if parts == ["runs"]:
            if method == "GET":
                filters = {k: query[k] for k in ("task_id", "state", "outcome", "date_from", "date_to") if query.get(k)}
                for field in ("date_from", "date_to"):
                    if field in filters:
                        date = datetime.fromisoformat(filters[field])
                        if len(filters[field]) == 10 and field == "date_to":
                            date = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                        filters[field] = (
                            date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
                        )
                return self.reply(store.runs(**self.pagination(query), **filters))
            if method == "POST":
                data = self.body()
                if data.get("rerun_id"):
                    data = store.run(data["rerun_id"])["request"]
                return self.reply(manager.start(data, key=self.headers.get("Idempotency-Key")), 202)
        if parts[0] == "runs" and len(parts) >= 2:
            run_id = parts[1]
            item = store.run(run_id)
            if len(parts) == 2:
                if method == "GET":
                    return self.reply(item)
                if method == "DELETE":
                    manager.delete(run_id)
                    return self.reply({"deleted": True})
            suffix = parts[2:]
            if suffix == ["acknowledge"] and method == "POST":
                if self.body().get("processes_inspected") is not True:
                    raise Problem("confirmation_required", "Confirm that previous test processes were inspected")
                return self.reply(manager.acknowledge(run_id))
            if suffix == ["stop"] and method == "POST":
                return self.reply(manager.stop(run_id))
            if method == "GET":
                if suffix == ["results"]:
                    return self.reply(store.results(run_id, **self.pagination(query), outcome=query.get("outcome")))
                if suffix == ["logs"]:
                    return self.reply(
                        manager.log_window(
                            run_id,
                            int(query.get("cursor", 0)),
                            before=int(query["before"]) if "before" in query else None,
                            tail=query.get("tail") == "1",
                        )
                    )
                if suffix == ["events"]:
                    return self.stream(run_id, query)
                if suffix and suffix[0] == "artifacts":
                    return self.send_file(manager.artifact(run_id, "/".join(suffix[1:])))
        raise Problem("not_found", "Endpoint not found", 404)

    def wait_for_events(self, revision):
        # Timeout only keeps the connection alive; it never re-reads project/log state.
        while not self.manager.closed and self.manager.events.wait(revision) == revision:
            self.wfile.write(b": keep-alive\n\n")
            self.wfile.flush()

    def project_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        previous = None
        try:
            while not self.manager.closed:
                revision = self.manager.events.revision
                snapshot = self.manager.project()
                if snapshot != previous:
                    self._sse_event(snapshot)
                    previous = snapshot
                self.wait_for_events(revision)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def stream(self, run_id, query):
        cursor = int(self.headers.get("Last-Event-ID") or query.get("cursor", 0))
        self.manager.logs(run_id, cursor)  # validate before committing response headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while not self.manager.closed:
                revision = self.manager.events.revision
                batch = self.manager.logs(run_id, cursor)
                item = self.manager.store.run(run_id)
                if batch["cursor"] != cursor:
                    cursor = batch["cursor"]
                    self.wfile.write(f"id: {cursor}\n".encode())
                    self._sse_event(
                        {"text": batch["text"], "lines": ANSI.sub("", batch["text"]).splitlines(True), "cursor": cursor}
                    )
                    continue
                if item["state"] in TERMINAL:
                    self._sse_event(
                        {
                            "done": True,
                            "status": item["state"],
                            "outcome": item.get("outcome"),
                            "exit_code": item.get("exit_code"),
                            "report_url": self.report_url(item),
                        }
                    )
                    break
                self._sse_event({"heartbeat": True, "status": item["state"]})
                self.wait_for_events(revision)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Problem as exc:
            if exc.status != 404:
                raise
            self._sse_event({"done": True, "status": "deleted", "outcome": "unknown"})

    @staticmethod
    def report_url(item):
        if item.get("report_path"):
            return f"/api/v1/runs/{item['id']}/artifacts/{item['report_path']}"
        if item.get("legacy_report"):
            return "/api/report/" + item["id"]
        return None

    def legacy_summary(self, item):
        def timestamp(value):
            return datetime.fromisoformat(value).timestamp() if value else None

        return dict(
            run_id=item["id"],
            status=item["state"],
            nodeids=item["request"]["selection"]["nodeids"],
            case_count=len(item["request"]["selection"]["nodeids"]),
            exit_code=item.get("exit_code"),
            started_at=timestamp(item.get("started_at")),
            finished_at=timestamp(item.get("finished_at")),
            report_path=self.report_url(item),
        )

    def legacy(self, method, path, query):
        manager, store = self.manager, self.manager.store
        if method == "GET" and path in ("/api/cases", "/api/tree"):
            cases = manager.cases()
            return self.reply(
                cases
                if path == "/api/cases"
                else dict(flat=cases, tree=_build_case_tree(cases, str(manager.context.root)))
            )
        if method == "POST" and path == "/api/refresh":
            return self.reply(dict(refreshed=True, count=len(manager.cases(True))))
        if method == "POST" and path in ("/api/run", "/api/run-all"):
            data = self.body()
            ids = data.get("nodeids") if path == "/api/run" else [c["nodeid"] for c in manager.cases()]
            item = manager.start(
                dict(
                    selection={"nodeids": ids},
                    options={"verbosity": data.get("verbosity", "verbose"), "html_report": bool(data.get("report"))},
                )
            )
            return self.reply(dict(run_id=item["id"], count=len(ids), status="running"))
        if method == "GET" and path == "/api/runs":
            active = {i["id"]: self.legacy_summary(i) for i in store.unfinished()}
            return self.reply(dict(active=active, active_count=len(active), running=manager.operation.locked()))
        if method == "GET" and path == "/api/history":
            return self.reply(
                [self.legacy_summary(i) for i in store.runs(page_size=100)["items"] if i["state"] in TERMINAL]
            )
        if path.startswith("/api/history/"):
            run_id = store.legacy_id(path.split("/")[-1])
            if method == "GET":
                item = self.legacy_summary(store.run(run_id))
                item["logs"] = manager.logs(run_id)["text"].splitlines(True)
                return self.reply(item)
            if method == "DELETE":
                manager.delete(run_id)
                return self.reply({"deleted": True, "run_id": run_id})
        if path.startswith("/api/stream/") and method == "GET":
            return self.stream(store.legacy_id(path.split("/")[-1]), query)
        if path.startswith("/api/report/") and method == "GET":
            parts = path.split("/")[3:]
            item = store.run(store.legacy_id(parts[0]))
            if item.get("report_path"):
                return self._redirect(self.report_url(item))
            if item.get("legacy_report"):
                from pathlib import Path

                original = Path(item["legacy_report"])
                if not original.is_absolute():
                    original = manager.context.root / original
                original = original.resolve()
                root = (manager.context.root / "reports").resolve()
                if not original.is_relative_to(root):
                    raise Problem("not_found", "Legacy report is outside project reports", 404)
                if len(parts) == 1:
                    return self._redirect("/api/report/" + item["id"] + "/" + original.name)
                target = (original.parent / "/".join(parts[1:])).resolve()
                if target.is_relative_to(original.parent) and target.is_file():
                    return self.send_file(target)
        raise Problem("not_found", "Endpoint not found", 404)
