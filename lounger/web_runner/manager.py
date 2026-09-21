"""Project-scoped lifecycle: one worker, durable runs, no browser dependency."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any

from lounger.services.case_discovery import discover_cases
from lounger.services.test_execution import (
    build_pytest_command,
    launch_pytest,
    read_project_addopts,
    terminate_pytest,
    without_html_addopts,
)

from .context import ProjectContext, ProjectLock
from .events import Events, ProjectWatcher
from .results import parse_junit
from .storage import TERMINAL, Problem, Store, now

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def validate_definition(data, task=False):
    if not isinstance(data, dict):
        raise Problem("invalid_request", "Expected an object")
    selection = data.get("selection", {})
    if not isinstance(selection, dict) or selection.get("type", "nodeids") != "nodeids":
        raise Problem("invalid_selection", "Only explicit nodeids are supported")
    ids = selection.get("nodeids", [])
    if not isinstance(ids, list) or not ids or any(not isinstance(n, str) or not n or len(n) > 4096 for n in ids):
        raise Problem("invalid_selection", "Select at least one valid nodeid")
    options = data.get("options", {})
    if not isinstance(options, dict) or options.get("verbosity", "quiet") not in (
        "quiet",
        "normal",
        "verbose",
        "full",
    ):
        raise Problem("invalid_options", "Invalid verbosity")
    if not isinstance(options.get("html_report", False), bool):
        raise Problem("invalid_options", "html_report must be a boolean")
    item: dict[str, Any] = dict(
        selection={"type": "nodeids", "nodeids": list(dict.fromkeys(ids))},
        options={"verbosity": options.get("verbosity", "quiet"), "html_report": options.get("html_report", False)},
    )
    if task:
        name, description = data.get("name"), data.get("description", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise Problem("invalid_name", "Task name must contain 1–128 characters")
        if not isinstance(description, str) or len(description) > 10000:
            raise Problem("invalid_description", "Description is too long")
        item.update(name=name.strip(), description=description)
        if "revision" in data:
            item["revision"] = data["revision"]
    return item


def atomic_json(path, data):
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False)
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


class RunManager:
    def __init__(self, context: ProjectContext, collector=discover_cases):
        self.context = context
        self.owner = ProjectLock(context).acquire()
        self.data_owner = None
        try:
            if context.root != context.data_dir:
                self.data_owner = ProjectLock(ProjectContext(context.data_dir, context.data_dir)).acquire()
            self.store = Store(context.data_dir)
            self.collector = collector
            self.events = Events()
            self.watcher: ProjectWatcher | None = None
            self.operation = threading.Lock()
            self.control = threading.RLock()
            self.process: subprocess.Popen | None = None
            self.thread: threading.Thread | None = None
            self.active_id: str | None = None
            self.cancel = threading.Event()
            self.closed = False
            self.blocked: list[dict] = []
            self.warnings: list[str] = []
            self.cache: list[dict] | None = None
            self.cache_time: float | None = None
            self._recover()
            self._import_legacy()
        except Exception:
            if self.data_owner:
                self.data_owner.close()
            self.owner.close()
            raise

    def watch(self):
        if self.watcher is None:
            self.watcher = ProjectWatcher(self.context, self.sources_changed, self.events.publish)

    def sources_changed(self):
        with self.events.condition:
            self.cache_time = None
            self.events.publish(source=True)

    def project(self):
        return dict(
            id=self.store.project_id,
            name=self.context.root.name,
            path=str(self.context.root),
            python=self.context.python,
            data_dir=str(self.context.data_dir),
            busy=self.operation.locked(),
            active_run_id=self.active_id,
            warnings=list(self.warnings),
            blocked=list(self.blocked),
            sources_revision=self.events.sources,
        )

    def directory(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise Problem("not_found", "Invalid run ID", 404)
        directory = self.context.data_dir / "runs" / run_id
        if not directory.resolve().is_relative_to(self.context.data_dir.resolve()):
            raise Problem("invalid_path", "Artifact path is outside the data directory", 403)
        return directory

    def artifact(self, run_id, relative):
        self.store.run(run_id)
        base = self.directory(run_id).resolve()
        target = (base / relative).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise Problem("not_found", "Artifact not found", 404)
        return target

    @staticmethod
    def _alive(pid):
        if not pid:
            return False
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return getattr(ctypes, "get_last_error")() != 87  # access denied is uncertain, invalid PID is gone
            try:
                code = wintypes.DWORD()
                return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
            finally:
                kernel.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _recover(self):
        # Includes interrupted runs: a previous restart must not erase residual-process protection.
        with self.store.connection() as db:
            rows = db.execute("SELECT data FROM runs WHERE state NOT IN ('completed','error','cancelled')").fetchall()
        for row in rows:
            item = json.loads(row[0])
            if item.get("recovery_acknowledged"):
                continue
            directory = self.directory(item["id"])
            manifest = directory / "result.json"
            if manifest.is_file():
                try:
                    completed = json.loads(manifest.read_text(encoding="utf-8"))
                    if not completed["changes"].get("ownership_uncertain"):
                        self.store.update_run(item["id"], completed["changes"], completed["results"])
                        continue
                except (ValueError, KeyError, OSError) as exc:
                    self.warnings.append(f"Recovery failed for {item['id']}: {exc}")
            pid = item.get("pid")
            if not pid and (directory / "process.json").is_file():
                try:
                    pid = json.loads((directory / "process.json").read_text())["pid"]
                except (ValueError, KeyError, OSError):
                    pass
            # A worker may have exited while descendants remain in its process group.
            alive = self._alive(pid)
            if os.name != "nt" and pid:
                try:
                    os.killpg(pid, 0)
                    alive = True
                except ProcessLookupError:
                    pass
                except PermissionError:
                    alive = True
            if alive or (item.get("state") == "starting" and not pid) or item.get("ownership_uncertain"):
                self.blocked.append(
                    {
                        "run_id": item["id"],
                        "pid": pid,
                        "message": "Previous process ownership is uncertain; inspect before running again",
                    }
                )
            self.store.update_run(
                item["id"],
                dict(
                    state="interrupted",
                    outcome="unknown",
                    finished_at=now(),
                    pid=pid,
                    ownership_uncertain=item.get("ownership_uncertain", False)
                    or (item.get("state") == "starting" and not pid),
                    error_message="Runner stopped before completion",
                ),
            )

    def cases(self, refresh=False):
        if self.closed:
            raise Problem("shutting_down", "Runner is shutting down", 503)
        with self.events.condition:
            if (
                not refresh
                and self.cache is not None
                and self.cache_time is not None
                and time.monotonic() - self.cache_time < 300
            ):
                return self.cache
        if not self.operation.acquire(blocking=False):
            if not refresh and self.cache is not None:
                return self.cache
            raise Problem("project_busy", "Project is collecting or running", 409)
        try:
            self.events.publish()
            return self._collect()
        finally:
            self.operation.release()
            self.events.publish()

    def _collect(self):
        revision = self.events.sources
        cases = self.collector(str(self.context.root))
        if not isinstance(cases, list) or any(not isinstance(c, dict) or "error" in c for c in cases):
            raise Problem("collection_failed", str(cases), 400)
        with self.events.condition:
            self.cache, self.cache_time = cases, time.monotonic() if revision == self.events.sources else None
        return cases

    def validate_tasks(self, task_ids):
        """Check a batch against ONE fresh collection, never confuse collection errors with missing cases."""
        if not isinstance(task_ids, list) or len(task_ids) > 100 or any(not isinstance(i, str) for i in task_ids):
            raise Problem("invalid_request", "task_ids must contain at most 100 task IDs")
        tasks = [self.store.task(i) for i in dict.fromkeys(task_ids)]
        try:
            cases = self.cases(refresh=True)
        except Problem as exc:
            return {
                "checked_at": now(),
                "items": [
                    dict(
                        id=t["id"],
                        revision=t["revision"],
                        status="unknown",
                        reason=str(exc),
                        missing=[],
                        total=len(t["selection"]["nodeids"]),
                    )
                    for t in tasks
                ],
            }
        checked = now()
        known = {case["nodeid"] for case in cases if case.get("nodeid")}
        items = []
        for task in tasks:
            missing = []
            for nodeid in task["selection"]["nodeids"]:
                if nodeid in known:
                    continue
                source = (self.context.root / nodeid.split("::", 1)[0]).resolve()
                reason = "case_not_collected"
                if source.is_relative_to(self.context.root) and not source.exists():
                    reason = "file_missing"
                missing.append({"nodeid": nodeid, "reason": reason})
            items.append(
                dict(
                    id=task["id"],
                    revision=task["revision"],
                    status="invalid" if missing else "valid",
                    total=len(task["selection"]["nodeids"]),
                    missing=missing,
                    valid_count=len(task["selection"]["nodeids"]) - len(missing),
                )
            )
        return {"checked_at": checked, "items": items}

    def start(self, data, task_id=None, key=None, verbosity_override=None):
        if key and len(key) > 256:
            raise Problem("invalid_key", "Idempotency key exceeds 256 characters")
        definition = validate_definition(data)
        request = definition
        if verbosity_override is not None:
            request = validate_definition(
                {**definition, "options": {**definition["options"], "verbosity": verbosity_override}}
            )
        digest = hashlib.sha256(
            json.dumps({"request": request, "task_id": task_id}, sort_keys=True).encode()
        ).hexdigest()
        prior = self.store.request(key, digest)
        if prior:
            return prior
        if not self.operation.acquire(blocking=False):
            raise Problem("project_busy", "有任务正在运行或收集中，请等待完成后再试", 409)
        try:
            self.events.publish()
            if self.closed:
                raise Problem("shutting_down", "Runner is shutting down", 503)
            if self.blocked:
                raise Problem(
                    "residual_process", "Inspect previous test processes and restart runner", 409, self.blocked
                )
            prior = self.store.request(key, digest)
            if prior:
                self.operation.release()
                self.events.publish()
                return prior
            task = self.store.task(task_id) if task_id else None
            if task and definition != validate_definition(task):
                raise Problem("revision_conflict", "Task changed before execution; reload and retry", 409)
            known = {c.get("nodeid") for c in self._collect()}
            if self.closed:
                raise Problem("shutting_down", "Runner is shutting down", 503)
            missing = [n for n in request["selection"]["nodeids"] if n not in known]
            if missing:
                raise Problem("selection_stale", "Some selected cases no longer exist", 409, {"nodeids": missing})
            run_id = uuid.uuid4().hex
            item = dict(
                id=run_id,
                state="starting",
                outcome=None,
                result_status="pending",
                task_id=task_id,
                task_name_snapshot=task["name"] if task else None,
                task_revision=task["revision"] if task else None,
                source="task" if task else "manual",
                request=request,
                started_at=now(),
                finished_at=None,
                exit_code=None,
                python_path=self.context.python,
                git=self._git_info(),
                artifact_dir=f"runs/{run_id}",
                counts={},
                error_message=None,
            )
            self.store.create_run(item, key, digest)
            with self.control:
                self.active_id = run_id
                self.events.publish()
                self.cancel.clear()
                self.thread = threading.Thread(
                    target=self._execute, args=(item,), name=f"lounger-{run_id}", daemon=True
                )
                self.thread.start()
            return item
        except Exception:
            self.operation.release()
            self.events.publish()
            raise

    def _git_info(self):
        def git(*args):
            result = subprocess.run(
                ["git", "-C", str(self.context.root), *args], capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip() if result.returncode == 0 else None

        try:
            commit = git("rev-parse", "HEAD")
            return dict(
                commit=commit,
                branch=git("branch", "--show-current"),
                dirty=bool(git("status", "--porcelain")) if commit else None,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}

    def _execute(self, item):
        run_id = item["id"]
        start = time.monotonic()
        directory = self.directory(run_id)
        results, counts = [], {}
        changes: dict[str, Any] = dict(state="error", outcome="unknown", result_status="unavailable", exit_code=None)
        proc = None
        try:
            directory.mkdir(parents=True, exist_ok=False)
            atomic_json(directory / "request.json", item["request"])
            targets = directory / "targets.json"
            atomic_json(targets, [{"nodeid": n} for n in item["request"]["selection"]["nodeids"]])
            options = item["request"]["options"]
            html = directory / "html" / "report.html" if options["html_report"] else None
            if html:
                html.parent.mkdir()
            addopts = read_project_addopts(str(self.context.root))
            override = without_html_addopts(addopts) if not html else None
            cmd = build_pytest_command(run_id, targets, options["verbosity"], html, override)
            cmd[0] = self.context.python
            cmd.extend([f"--junit-xml={directory / 'junit.xml'}", "-o", "junit_logging=all"])
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
            # PYTEST_ADDOPTS can also request HTML output; obey the UI toggle there.
            if not html and env.get("PYTEST_ADDOPTS"):
                env["PYTEST_ADDOPTS"] = without_html_addopts(env["PYTEST_ADDOPTS"])
            with (directory / "output.log").open("wb", buffering=0) as log:
                with self.control:
                    if self.cancel.is_set():
                        changes.update(state="cancelled", outcome="unknown")
                    else:
                        # Drain bytes as they arrive; never wait for a newline or file watcher.
                        proc = launch_pytest(cmd, self.context.root, stdout=subprocess.PIPE, env=env)
                        self.process = proc
                        atomic_json(directory / "process.json", {"pid": proc.pid})
                        self.store.update_run(run_id, dict(state="running", pid=proc.pid))
                        self.events.publish()
                if proc:
                    code = self._stream_output(proc, log)
                    changes.update(
                        exit_code=code,
                        state="cancelled" if self.cancel.is_set() else ("completed" if code in (0, 1) else "error"),
                        outcome="unknown" if self.cancel.is_set() else {0: "passed", 1: "failed"}.get(code, "unknown"),
                    )
                    if code not in (0, 1) and not self.cancel.is_set():
                        changes["error_message"] = f"pytest exited with code {code}"
                log.write(f"\n── 执行完成 (exit code: {changes['exit_code']}) ──\n".encode())
                os.fsync(log.fileno())
            self.store.update_run(run_id, {"state": "finalizing"})
            self.events.publish()
            try:
                results, counts = parse_junit(directory / "junit.xml")
                for index, result in enumerate(results):
                    for field in ("stdout", "stderr"):
                        content = result.pop(field, "")
                        relative = f"case_{index}_{field}.log"
                        (directory / relative).write_text(content, encoding="utf-8")
                        result[field + "_path"] = relative
                        result[field] = content[:4096]
                    result["failure_text"] = result["failure_text"][:65536]
                changes["result_status"] = "ready" if changes["state"] == "completed" else "partial"
            except Exception as exc:
                # Parsing failures must preserve the pytest outcome and expose unavailable results.
                changes["error_message"] = f"{changes.get('error_message') or ''} Report unavailable: {exc}".strip()
            changes["report_path"] = "html/report.html" if html and html.is_file() else None
        except Exception as exc:
            changes.update(state="error", error_message=str(exc))
            if proc and proc.poll() is None:
                try:
                    self._terminate(proc)
                except Exception as stop_error:
                    changes["error_message"] += f"; process termination failed: {stop_error}"
        finally:
            if proc and proc.poll() is None:
                changes.update(state="interrupted", pid=proc.pid, ownership_uncertain=True)
                self.blocked.append({"run_id": run_id, "pid": proc.pid, "message": "Test process did not stop"})
            changes.update(finished_at=now(), duration_ms=round((time.monotonic() - start) * 1000), counts=counts)
            try:
                if directory.is_dir():
                    atomic_json(directory / "result.json", dict(changes=changes, results=results))
                self.store.update_run(run_id, changes, results)
            except Exception as exc:
                self.warnings.append(f"Run {run_id} could not be persisted: {exc}; restart to recover")
                self.blocked.append({"run_id": run_id, "message": "Run persistence failed; restart to recover"})
            finally:
                with self.control:
                    self.process = None
                    self.active_id = None
                self.operation.release()
                self.events.publish()

    def _stream_output(self, proc, log):
        errors = []

        def drain():
            try:
                while chunk := os.read(proc.stdout.fileno(), 65536):
                    log.write(chunk)
                    self.events.publish()
            except Exception as exc:
                errors.append(exc)
                self._terminate(proc)
            finally:
                proc.stdout.close()

        reader = threading.Thread(target=drain, name="lounger-log-stream", daemon=True)
        reader.start()
        code = proc.wait()
        reader.join(timeout=2)
        if reader.is_alive():
            # A descendant may keep stdout open after pytest exits. Stop the owned
            # process group rather than hanging finalization waiting for pipe EOF.
            self._terminate(proc)
            reader.join(timeout=5)
        if reader.is_alive():
            raise RuntimeError("Test output pipe did not close after process termination")
        if errors:
            raise RuntimeError(f"Could not persist test output: {errors[0]}")
        return code

    _terminate = staticmethod(terminate_pytest)

    def stop(self, run_id):
        with self.control:
            item = self.store.run(run_id)
            if item["state"] in TERMINAL:
                return item
            if run_id != self.active_id:
                raise Problem("not_active", "Run is not owned by this process", 409)
            if item["state"] == "finalizing":
                return item
            self.cancel.set()
            self.store.update_run(run_id, {"state": "stopping"})
            proc = self.process
            if proc:
                try:
                    self._terminate(proc)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise Problem("stop_failed", f"Test process could not be stopped: {exc}", 503) from exc
        return self.store.run(run_id)

    def logs(self, run_id, cursor=0, limit=65536):
        self.store.run(run_id)
        path = self.directory(run_id) / "output.log"
        if not path.exists():
            return dict(text="", cursor=0)
        with path.open("rb") as log:
            size = log.seek(0, 2)
            if cursor < 0 or cursor > size:
                raise Problem("invalid_cursor", "Log cursor is outside the file")
            log.seek(cursor)
            raw = log.read(limit)
            # Keep a split UTF-8 code point for the next batch; replace truly invalid output.
            import codecs

            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            text = decoder.decode(raw, final=cursor + len(raw) == size and self.store.run(run_id)["state"] in TERMINAL)
            pending = decoder.getstate()[0]
            return dict(text=text, cursor=cursor + len(raw) - len(pending))

    def log_window(self, run_id, cursor=0, before=None, tail=False, limit=65536):
        """Return a UTF-8-safe window. Tail first, with earlier windows available on scroll."""
        self.store.run(run_id)
        path = self.directory(run_id) / "output.log"
        if not path.exists():
            return {"text": "", "start": 0, "cursor": 0, "size": 0}
        size = path.stat().st_size
        if before is None and not tail:
            batch = self.logs(run_id, cursor, limit)
            return {**batch, "start": cursor, "size": size}
        end = size if tail else before
        if not isinstance(end, int) or not 0 <= end <= size:
            raise Problem("invalid_cursor", "Log window is outside the file")
        start = max(0, end - limit)
        with path.open("rb") as stream:
            stream.seek(start)
            raw = stream.read(end - start)
        # A previous window starts at a UTF-8 boundary; find one for this window too.
        skipped = 0
        while skipped < len(raw) and raw[skipped] & 0xC0 == 0x80:
            skipped += 1
        raw, start = raw[skipped:], start + skipped
        import codecs

        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        text = decoder.decode(raw, final=self.store.run(run_id)["state"] in TERMINAL)
        return {"text": text, "start": start, "cursor": end - len(decoder.getstate()[0]), "size": size}

    def delete(self, run_id):
        if any(block["run_id"] == run_id for block in self.blocked):
            raise Problem("residual_process", "Resolve recovery diagnostics before deleting this run", 409)
        item = self.store.run(run_id)
        if item["state"] not in TERMINAL:
            raise Problem("run_active", "Cannot delete an active run", 409)
        # Database-first deletion leaves only harmless orphaned files if cleanup fails.
        self.store.delete_run(run_id)
        directory = self.directory(run_id)
        if directory.exists():
            shutil.rmtree(directory)

    def close(self):
        self.closed = True
        self.events.close()
        if self.watcher:
            self.watcher.close()
        try:
            if self.active_id:
                self.stop(self.active_id)
            if self.thread:
                self.thread.join(timeout=20)
                if self.thread.is_alive():
                    raise RuntimeError("Test worker has not stopped; project lock retained")
            if not self.operation.acquire(timeout=35):
                raise RuntimeError("Project operation has not stopped; ownership locks retained")
            self.operation.release()
            self.events.publish()
        finally:
            if (not self.thread or not self.thread.is_alive()) and not self.operation.locked():
                if self.data_owner:
                    self.data_owner.close()
                self.owner.close()

    def acknowledge(self, run_id):
        """User explicitly verified uncertain process ownership before unblocking."""
        item = self.store.run(run_id)
        if item["state"] != "interrupted":
            raise Problem("invalid_state", "Only interrupted runs can be acknowledged", 409)
        pid = item.get("pid")
        alive = self._alive(pid)
        if os.name != "nt" and pid:
            try:
                os.killpg(pid, 0)
                alive = True
            except ProcessLookupError:
                pass
            except PermissionError:
                alive = True
        if alive:
            raise Problem("residual_process", "Previous process still exists", 409)
        item = self.store.update_run(run_id, {"ownership_uncertain": False, "pid": None, "recovery_acknowledged": True})
        self.blocked = [b for b in self.blocked if b["run_id"] != run_id]
        return item

    def _import_legacy(self):
        from datetime import datetime, timezone

        for path in sorted((self.context.root / "reports" / "runs").glob("*.json")):
            key = path.relative_to(self.context.root).as_posix()
            with self.store.connection() as db:
                # Older Windows imports used native backslashes in persisted keys.
                if db.execute(
                    "SELECT 1 FROM legacy_imports WHERE source_key IN (?, ?)", (key, key.replace("/", "\\"))
                ).fetchone():
                    continue
            try:
                raw = path.read_bytes()
                old = json.loads(raw)
                if not isinstance(old, dict) or not isinstance(old.get("logs", []), list):
                    raise ValueError("Invalid legacy run")
                run_id = uuid.uuid5(uuid.UUID(self.store.project_id), key).hex
                directory = self.directory(run_id)
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "output.log").write_bytes("".join(old.get("logs", [])).encode("utf-8"))
                started = old.get("started_at") or path.stat().st_mtime
                item = dict(
                    id=run_id,
                    legacy_id=path.stem,
                    state=old.get("status", "interrupted"),
                    outcome={0: "passed", 1: "failed"}.get(old.get("exit_code", -1), "unknown"),
                    result_status="unavailable",
                    started_at=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                    finished_at=(
                        datetime.fromtimestamp(old["finished_at"], timezone.utc).isoformat()
                        if old.get("finished_at")
                        else None
                    ),
                    duration_ms=(round((old["finished_at"] - started) * 1000) if old.get("finished_at") else None),
                    exit_code=old.get("exit_code"),
                    counts={},
                    source="legacy",
                    request={
                        "selection": {"type": "nodeids", "nodeids": old.get("nodeids", [])},
                        "options": {"verbosity": "verbose", "html_report": bool(old.get("report_path"))},
                    },
                    report_path=None,
                    legacy_report=old.get("report_path"),
                )
                if item["state"] not in TERMINAL:
                    item["state"] = "interrupted"
                with self.store.connection() as db:
                    db.execute(
                        "INSERT OR IGNORE INTO runs(id,state,outcome,started_at,data) VALUES(?,?,?,?,?)",
                        (run_id, item["state"], item["outcome"], item["started_at"], json.dumps(item)),
                    )
                    db.execute(
                        "INSERT INTO legacy_imports VALUES(?,?,?,?)",
                        (key, hashlib.sha256(raw).hexdigest(), run_id, "imported"),
                    )
            except (OSError, ValueError, TypeError, OverflowError) as exc:
                self.warnings.append(f"Could not import {key}: {exc}")
