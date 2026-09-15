"""
Test execution — run a set of nodeids via a pytest subprocess.

Shared by the web runner and the platform script (docs/development_plan.md
§3.8).  A run is identified by a ``run_id`` and its live state lives in the
provided ``runs`` dict (the web runner keeps it in ``web_runner.state``).

Run history is bounded: :func:`archive_run` keeps the most recent
``keep_recent`` runs in memory and persists the rest under
``<scan_dir>/reports/runs/`` so long-running services do not grow unbounded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

VERBOSITY_FLAGS = {
    "quiet":   ["-q"],
    "normal":  [],
    "verbose": ["-v"],
    "full":    ["-vv", "-s"],
}


def build_pytest_command(run_id: str, target_file: Path, verbosity: str = "normal") -> list[str]:
    """
    Build the pytest subprocess command for a run.

    :param run_id: Run identifier (used in the JSON filename only).
    :param target_file: Path to the ``--run-json`` payload file.
    :param verbosity: quiet | normal | verbose | full.
    """
    extra = VERBOSITY_FLAGS.get(verbosity, [])
    return [
        sys.executable, "-m", "pytest",
        "--run-json", str(target_file),
        *extra,
        "--tb=short",
        "--color=yes",
    ]


def write_run_payload(scan_dir: str, run_id: str, nodeids: list[str]) -> Path:
    """
    Write the ``--run-json`` payload file for a run.

    :return: Path to the created payload file (under ``<scan_dir>/collected_cases/``).
    """
    tmpdir = Path(scan_dir) / "collected_cases"
    tmpdir.mkdir(parents=True, exist_ok=True)
    target_file = tmpdir / f"_web_run_{run_id}.json"
    payload = [{"nodeid": nid} for nid in nodeids]
    target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target_file


def start_run(
    runs: dict,
    scan_dir: str,
    run_id: str,
    nodeids: list[str],
    verbosity: str = "normal",
    lock: threading.Lock | None = None,
    strip_ansi: Callable[[str], str] | None = None,
) -> None:
    """
    Start a run in a background thread (non-blocking).

    :param runs: The shared runs registry (mutated in place).
    :param scan_dir: Project root directory.
    :param run_id: Unique run identifier.
    :param nodeids: Test case nodeids to execute (in order).
    :param verbosity: pytest verbosity profile.
    :param lock: Lock guarding ``runs`` (created internally if ``None``).
    :param strip_ansi: Optional ``str -> str`` ANSI stripper for log lines.
    """
    if strip_ansi is None:
        strip_ansi = lambda text: text  # noqa: E731

    import queue as _queue
    log_queue: _queue.Queue = _queue.Queue()
    lock = lock or threading.Lock()

    with lock:
        runs[run_id] = {
            "queue": log_queue,
            "status": "running",
            "logs": [],
            "nodeids": nodeids,
            "exit_code": None,
        }

    thread = threading.Thread(
        target=_execute_in_thread,
        args=(runs, scan_dir, run_id, nodeids, verbosity, lock, strip_ansi),
        daemon=True,
    )
    thread.start()


def _execute_in_thread(
    runs: dict,
    scan_dir: str,
    run_id: str,
    nodeids: list[str],
    verbosity: str,
    lock: threading.Lock,
    strip_ansi: Callable[[str], str],
) -> None:
    """Run pytest in a subprocess and stream lines into the run's log queue."""
    try:
        target_file = write_run_payload(scan_dir, run_id, nodeids)
    except OSError as e:
        with lock:
            runs[run_id]["status"] = "error"
            runs[run_id]["error"] = f"failed to write run payload: {e}"
        return

    cmd = build_pytest_command(run_id, target_file, verbosity)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=scan_dir,
            env=env,
        )
    except FileNotFoundError:
        with lock:
            runs[run_id]["status"] = "error"
            runs[run_id]["error"] = "pytest not found"
        return

    with lock:
        runs[run_id]["_process"] = proc

    log_queue = runs[run_id]["queue"]

    stdout = proc.stdout
    if stdout is not None:
        for raw_line in iter(stdout.readline, ""):
            clean = strip_ansi(raw_line)
            log_queue.put(clean)
            with lock:
                runs[run_id]["logs"].append(clean)

    proc.wait()

    summary = f"\n── 执行完成 (exit code: {proc.returncode}) ──\n"
    log_queue.put(summary)
    with lock:
        runs[run_id]["logs"].append(summary)
        runs[run_id]["status"] = "completed"
        runs[run_id]["exit_code"] = proc.returncode

    try:
        target_file.unlink()
    except OSError:
        pass


# ── run history / archival (memory-bounded, §3.8) ─────────────────────────

def _serialize_run(info: dict) -> dict:
    """Extract serializable fields from a run entry (drop queue/process)."""
    return {
        "status": info.get("status"),
        "nodeids": info.get("nodeids"),
        "logs": info.get("logs", []),
        "exit_code": info.get("exit_code"),
        "error": info.get("error"),
    }


def _persist_run(scan_dir: str, run_id: str, snapshot: dict) -> None:
    """Write a run snapshot under <scan_dir>/reports/runs/."""
    reports_dir = Path(scan_dir) / "reports" / "runs"
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"{run_id}.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def archive_run(
    runs: dict,
    scan_dir: str,
    run_id: str,
    keep_recent: int = 20,
    lock: threading.Lock | None = None,
) -> bool:
    """
    Persist a finished run and trim in-memory history to ``keep_recent``.

    The run identified by ``run_id`` is written to
    ``<scan_dir>/reports/runs/<run_id>.json`` and removed from memory; then
    any remaining finished runs beyond the most recent ``keep_recent`` are
    persisted and dropped as well.

    :param runs: The shared runs registry (mutated in place).
    :param scan_dir: Project root directory.
    :param run_id: Run to archive.
    :param keep_recent: Number of most recent finished runs to keep in memory.
    :param lock: Lock guarding ``runs`` (created internally if ``None``).
    :return: True if the run was archived.
    """
    lock = lock or threading.Lock()

    with lock:
        if run_id not in runs:
            return False
        if runs[run_id].get("status") in ("running", "queued"):
            return False

        snapshot = _serialize_run(runs[run_id])
        _persist_run(scan_dir, run_id, snapshot)
        runs.pop(run_id, None)

        # keep only the most recent `keep_recent` finished runs in memory
        finished = [
            rid for rid, info in runs.items()
            if info.get("status") in ("completed", "error")
        ]
        # sort by insertion order of the dict (approximate finish order)
        excess = finished[: max(0, len(finished) - keep_recent)]
        for old_id in excess:
            _persist_run(scan_dir, old_id, _serialize_run(runs[old_id]))
            runs.pop(old_id, None)

        return True
