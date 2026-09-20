"""SQLite repositories. Connections are local to each short transaction."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TERMINAL = ("completed", "error", "cancelled", "interrupted")


def now():
    return datetime.now(timezone.utc).isoformat()


class Problem(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details or {}


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "runner.db"
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Runner database is newer than this Lounger version")
            db.execute("PRAGMA journal_mode=WAL")
            if version == 0:
                if self.path.stat().st_size:
                    backup = sqlite3.connect(str(self.path) + ".v0.bak")
                    try:
                        db.backup(backup)
                    finally:
                        backup.close()
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT);
                    CREATE TABLE IF NOT EXISTS project_meta(id TEXT PRIMARY KEY);
                    CREATE TABLE IF NOT EXISTS tasks(
                        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, deleted_at TEXT, data TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS runs(
                        id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id), state TEXT NOT NULL,
                        outcome TEXT, started_at TEXT NOT NULL, request_key TEXT UNIQUE,
                        request_hash TEXT, data TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS runs_time ON runs(started_at, id);
                    CREATE INDEX IF NOT EXISTS runs_task ON runs(task_id, started_at);
                    CREATE INDEX IF NOT EXISTS runs_state ON runs(state, started_at);
                    CREATE TABLE IF NOT EXISTS case_results(
                        run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
                        ordinal INTEGER, outcome TEXT, data TEXT NOT NULL,
                        PRIMARY KEY(run_id, ordinal));
                    CREATE INDEX IF NOT EXISTS results_outcome ON case_results(run_id, outcome);
                    CREATE TABLE IF NOT EXISTS legacy_imports(
                        source_key TEXT PRIMARY KEY, source_hash TEXT, run_id TEXT, status TEXT);
                    PRAGMA user_version=1;
                    COMMIT;
                """)
                db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1, ?)", (now(),))
            row = db.execute("SELECT id FROM project_meta LIMIT 1").fetchone()
            self.project_id = row[0] if row else uuid.uuid4().hex
            if not row:
                db.execute("INSERT INTO project_meta VALUES(?)", (self.project_id,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def task(self, task_id):
        with self.connection() as db:
            row = db.execute("SELECT data FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone()
        if not row:
            raise Problem("not_found", "Task not found", 404)
        return json.loads(row[0])

    def save_task(self, data, task_id=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if task_id:
                row = db.execute("SELECT data FROM tasks WHERE id=? AND deleted_at IS NULL", (task_id,)).fetchone()
                if not row:
                    raise Problem("not_found", "Task not found", 404)
                old = json.loads(row[0])
                if data.get("revision") != old["revision"]:
                    raise Problem("revision_conflict", "Task has changed; reload before saving", 409)
                item = {**old, **data, "id": task_id, "revision": old["revision"] + 1, "updated_at": now()}
                db.execute(
                    "UPDATE tasks SET revision=?, data=? WHERE id=?", (item["revision"], json.dumps(item), task_id)
                )
            else:
                item = {**data, "id": uuid.uuid4().hex, "revision": 1, "created_at": now(), "updated_at": now()}
                db.execute("INSERT INTO tasks(id,revision,data) VALUES(?,?,?)", (item["id"], 1, json.dumps(item)))
        return item

    def delete_task(self, task_id):
        self.task(task_id)
        with self.connection() as db:
            db.execute("UPDATE tasks SET deleted_at=? WHERE id=?", (now(), task_id))

    def tasks(self, page=1, page_size=20, search=""):
        with self.connection() as db:
            rows = db.execute("SELECT data FROM tasks WHERE deleted_at IS NULL ORDER BY rowid DESC").fetchall()
            items = [json.loads(row[0]) for row in rows]
            if search:
                items = [
                    t for t in items if search.casefold() in (t["name"] + " " + t.get("description", "")).casefold()
                ]
            total = len(items)
            items = items[(page - 1) * page_size : page * page_size]
            for item in items:
                latest = db.execute(
                    "SELECT data FROM runs WHERE task_id=? ORDER BY started_at DESC,id DESC LIMIT 1", (item["id"],)
                ).fetchone()
                run = json.loads(latest[0]) if latest else None
                item["last_run"] = (
                    {k: run.get(k) for k in ("id", "state", "outcome", "started_at", "duration_ms", "counts")}
                    if run
                    else None
                )
        return dict(items=items, total=total, page=page, page_size=page_size)

    @staticmethod
    def page(rows, total, page, page_size):
        return dict(items=[json.loads(r[0]) for r in rows], total=total, page=page, page_size=page_size)

    def run(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise Problem("not_found", "Run not found", 404)
        return json.loads(row[0])

    def legacy_id(self, old_id):
        """Resolve bookmarked pre-SQLite URLs without resurrecting deleted imports."""
        with self.connection() as db:
            row = db.execute(
                "SELECT runs.id FROM legacy_imports JOIN runs ON runs.id=legacy_imports.run_id "
                "WHERE legacy_imports.source_key=?",
                (f"reports/runs/{old_id}.json",),
            ).fetchone()
        return row[0] if row else old_id

    def request(self, key, digest):
        if not key:
            return None
        with self.connection() as db:
            row = db.execute("SELECT request_hash,data FROM runs WHERE request_key=?", (key,)).fetchone()
        if row:
            if row[0] != digest:
                raise Problem("idempotency_conflict", "Key was already used for another request", 409)
            return json.loads(row[1])
        return None

    def create_run(self, item, key=None, digest=None):
        with self.connection() as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                (
                    item["id"],
                    item.get("task_id"),
                    item["state"],
                    item.get("outcome"),
                    item["started_at"],
                    key,
                    digest,
                    json.dumps(item),
                ),
            )
        return item

    def update_run(self, run_id, changes, results=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise Problem("not_found", "Run not found", 404)
            item = {**json.loads(row[0]), **changes}
            db.execute(
                "UPDATE runs SET state=?,outcome=?,data=? WHERE id=?",
                (item["state"], item.get("outcome"), json.dumps(item), run_id),
            )
            if results is not None:
                db.execute("DELETE FROM case_results WHERE run_id=?", (run_id,))
                db.executemany(
                    "INSERT INTO case_results VALUES(?,?,?,?)",
                    [(run_id, i, r["outcome"], json.dumps(r)) for i, r in enumerate(results)],
                )
        return item

    def runs(self, page=1, page_size=20, **filters):
        clauses, args = [], []
        for key in ("task_id", "state", "outcome"):
            if filters.get(key):
                clauses.append(f"{key}=?")
                args.append(filters[key])
        for key, op in [("date_from", ">="), ("date_to", "<=")]:
            if filters.get(key):
                clauses.append(f"started_at {op} ?")
                args.append(filters[key])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as db:
            total = db.execute("SELECT count(*) FROM runs" + where, args).fetchone()[0]
            rows = db.execute(
                "SELECT data FROM runs" + where + " ORDER BY started_at DESC,id DESC LIMIT ? OFFSET ?",
                [*args, page_size, (page - 1) * page_size],
            ).fetchall()
        return self.page(rows, total, page, page_size)

    def results(self, run_id, page=1, page_size=50, outcome=None):
        self.run(run_id)
        where, args = " WHERE run_id=?", [run_id]
        if outcome == "unsuccessful":
            where += " AND outcome IN ('failed','error')"
        elif outcome:
            where += " AND outcome=?"
            args.append(outcome)
        with self.connection() as db:
            total = db.execute("SELECT count(*) FROM case_results" + where, args).fetchone()[0]
            rows = db.execute(
                "SELECT data FROM case_results" + where + " ORDER BY ordinal LIMIT ? OFFSET ?",
                [*args, page_size, (page - 1) * page_size],
            ).fetchall()
        return self.page(rows, total, page, page_size)

    def unfinished(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT data FROM runs WHERE state NOT IN ('completed','error','cancelled','interrupted')"
            )
            return [json.loads(row[0]) for row in rows]

    def delete_run(self, run_id):
        item = self.run(run_id)
        if item["state"] not in TERMINAL:
            raise Problem("run_active", "Cannot delete an active run", 409)
        with self.connection() as db:
            db.execute("DELETE FROM runs WHERE id=?", (run_id,))
