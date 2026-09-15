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

import configparser
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

VERBOSITY_FLAGS = {
    "quiet":   ["-q"],
    "normal":  [],
    "verbose": ["-v", "-s"],
    "full":    ["-vv", "-s"],
}

#: pytest options that produce an HTML report (``--html=PATH`` / ``--html PATH``
#: and ``--self-contained-html``). Used to strip report generation from a
#: project's ``addopts`` when the user unticks the report checkbox.
_HTML_OPTION_RE = re.compile(r"(?:^|\s)--html(?:=\S+|\s+\S+)?|(?:^|\s)--self-contained-html\b")

#: Where run snapshots (history) are persisted, relative to the project root.
RUNS_DIR = ("reports", "runs")


def report_path(scan_dir: str, run_id: str) -> Path:
    """
    Return the HTML report path for a run.

    Reports are per-run (``reports/result_<run_id>.html``) so that every entry
    in the run history keeps pointing at its own report instead of all sharing
    one overwritten file.

    :param scan_dir: Project root directory.
    :param run_id: Unique run identifier.
    :return: The path the report will be written to.
    """
    return Path(scan_dir) / "reports" / f"result_{run_id}.html"


def read_project_addopts(scan_dir: str) -> str:
    """
    Best-effort read of the project's pytest ``addopts``.

    Looks at ``pytest.ini`` / ``tox.ini`` / ``setup.cfg`` (``[pytest]`` or
    ``[tool:pytest]``) and ``pyproject.toml`` (``[tool.pytest.ini_options]``).

    :param scan_dir: Project root directory.
    :return: The ``addopts`` string, or ``""`` when it cannot be determined.
    """
    root = Path(scan_dir)

    for name in ("pytest.ini", "tox.ini", "setup.cfg"):
        path = root / name
        if not path.is_file():
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        for section in ("pytest", "tool:pytest"):
            if parser.has_option(section, "addopts"):
                return parser.get(section, "addopts").strip()

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib
        except ModuleNotFoundError:  # pragma: no cover — Python < 3.11
            return ""
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        value = (
            data.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("addopts")
        )
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return " ".join(str(item) for item in value).strip()

    return ""


def without_html_addopts(addopts: str) -> str:
    """
    Remove HTML-report options from an ``addopts`` string.

    Only the report tokens are dropped; every other option is preserved
    verbatim (the string is not re-quoted, so project-specific flags keep
    working).

    :param addopts: The original ``addopts`` value.
    :return: ``addopts`` without ``--html`` / ``--self-contained-html``.
    """
    return " ".join(_HTML_OPTION_RE.sub(" ", addopts).split())


def build_pytest_command(
    run_id: str,
    target_file: Path,
    verbosity: str = "verbose",
    html_report: Path | None = None,
    addopts_override: str | None = None,
) -> list[str]:
    """
    Build the pytest subprocess command for a run.

    :param run_id: Run identifier (used in the JSON filename only).
    :param target_file: Path to the ``--run-json`` payload file.
    :param verbosity: quiet | normal | verbose | full.
    :param html_report: When given, pass ``--html=<path>``. Command-line options
        are parsed after the ini's ``addopts``, so this overrides a report path
        configured in the project.
    :param addopts_override: When given, replaces the project's ``addopts``
        (used to drop report generation when the user unticks it).
    """
    extra = VERBOSITY_FLAGS.get(verbosity, ["-v", "-s"])
    cmd = [
        sys.executable, "-m", "pytest",
        "--run-json", str(target_file),
        *extra,
        "--tb=short",
        "--color=yes",
    ]
    if html_report is not None:
        cmd.append(f"--html={html_report}")
    if addopts_override is not None:
        cmd += ["-o", f"addopts={addopts_override}"]
    return cmd


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
    verbosity: str = "verbose",
    lock: threading.Lock | None = None,
    strip_ansi: Callable[[str], str] | None = None,
    html_report: bool = False,
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
    :param html_report: Generate an HTML report for this run and expose it to
        the web runner (the report path is recorded on the run entry).
    """
    if strip_ansi is None:
        strip_ansi = lambda text: text  # noqa: E731

    lock = lock or threading.Lock()

    report_file = report_path(scan_dir, run_id) if html_report else None
    addopts_override = None
    if report_file is not None:
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            report_file = None
    else:
        # Unticked: drop report generation from the project's own addopts,
        # otherwise pytest.ini would still write a report.
        project_addopts = read_project_addopts(scan_dir)
        if _HTML_OPTION_RE.search(project_addopts):
            addopts_override = without_html_addopts(project_addopts)

    with lock:
        # Register (or update in place) the run entry. The dict identity is
        # kept stable because streaming clients hold a reference to it.
        entry = runs.get(run_id)
        if entry is None:
            entry = {}
            runs[run_id] = entry
        entry.update({
            "status": "running",
            "logs": [],
            "nodeids": nodeids,
            "exit_code": None,
            "started_at": time.time(),
            "html_report": report_file is not None,
            "report_path": str(report_file) if report_file is not None else None,
        })

    thread = threading.Thread(
        target=_execute_in_thread,
        args=(runs, scan_dir, run_id, nodeids, verbosity, lock, strip_ansi,
              report_file, addopts_override),
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
    report_file: Path | None = None,
    addopts_override: str | None = None,
) -> None:
    """Run pytest in a subprocess and stream lines into the run's log queue."""
    try:
        target_file = write_run_payload(scan_dir, run_id, nodeids)
    except OSError as e:
        with lock:
            runs[run_id]["status"] = "error"
            runs[run_id]["error"] = f"failed to write run payload: {e}"
        return

    cmd = build_pytest_command(
        run_id, target_file, verbosity,
        html_report=report_file, addopts_override=addopts_override,
    )
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

    stdout = proc.stdout
    if stdout is not None:
        for raw_line in iter(stdout.readline, ""):
            clean = strip_ansi(raw_line)
            with lock:
                runs[run_id]["logs"].append(clean)

    proc.wait()

    summary = f"\n\u2500\u2500 \u6267\u884c\u5b8c\u6210 (exit code: {proc.returncode}) \u2500\u2500\n"
    with lock:
        runs[run_id]["logs"].append(summary)
        runs[run_id]["status"] = "completed"
        runs[run_id]["exit_code"] = proc.returncode
        runs[run_id]["finished_at"] = time.time()
        # a requested report may still be missing (pytest-html unavailable)
        if report_file is not None and not report_file.is_file():
            runs[run_id]["html_report"] = False
            runs[run_id]["report_path"] = None

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
        "html_report": bool(info.get("html_report")),
        "report_path": info.get("report_path"),
        "started_at": info.get("started_at"),
        "finished_at": info.get("finished_at"),
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


# ── run history queries (web runner v2) ───────────────────────────────────

def _runs_dir(scan_dir: str) -> Path:
    """Return the ``reports/runs/`` directory for a project."""
    return Path(scan_dir) / "reports" / "runs"


def list_archived_runs(scan_dir: str) -> list[dict]:
    """
    List all archived run snapshots under ``<scan_dir>/reports/runs/``.

    Returns a list of summary dicts sorted by modification time (newest first).
    Each summary contains: run_id, status, exit_code, case_count,
    started_at, finished_at.
    """
    runs_dir = _runs_dir(scan_dir)
    if not runs_dir.is_dir():
        return []

    results: list[dict] = []
    for fp in sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        results.append({
            "run_id": fp.stem,
            "status": data.get("status"),
            "exit_code": data.get("exit_code"),
            "case_count": len(data.get("nodeids", [])),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
        })
    return results


def load_archived_run(scan_dir: str, run_id: str) -> dict | None:
    """
    Load a single archived run's full data (including logs).

    :return: The run snapshot dict, or None if not found.
    """
    fp = _runs_dir(scan_dir) / f"{run_id}.json"
    if not fp.is_file():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_archived_run(scan_dir: str, run_id: str) -> bool:
    """
    Delete an archived run file.

    :return: True if the file was deleted, False if not found.
    """
    fp = _runs_dir(scan_dir) / f"{run_id}.json"
    if not fp.is_file():
        return False
    try:
        fp.unlink()
        return True
    except OSError:
        return False
