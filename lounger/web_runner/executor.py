"""
Background test execution via pytest subprocess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from lounger.web_runner import state as _state
from lounger.web_runner.state import _active_runs, _runs_lock, _strip_ansi

VERBOSITY_FLAGS = {
    "quiet":   ["-q"],
    "normal":  [],
    "verbose": ["-v", "-s"],
    "full":    ["-vv", "-s"],
}


def _execute_tests(run_id: str, nodeids: list[str], verbosity: str = "verbose") -> None:
    """Run pytest in a subprocess, push lines into the run queue."""
    cwd = str(Path(_state._scan_dir).resolve())
    tmpdir = Path(cwd) / "collected_cases"
    tmpdir.mkdir(parents=True, exist_ok=True)
    target_file = tmpdir / f"_web_run_{run_id}.json"

    target_payload = [{"nodeid": nid} for nid in nodeids]
    target_file.write_text(json.dumps(target_payload, indent=2), encoding="utf-8")

    extra = VERBOSITY_FLAGS.get(verbosity, ["-v", "-s"])
    cmd = [
        sys.executable, "-m", "pytest",
        "--run-json", str(target_file),
        *extra,
        "--tb=short",
        "--color=yes",
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
        )
    except FileNotFoundError:
        with _runs_lock:
            _active_runs[run_id]["status"] = "error"
            _active_runs[run_id]["error"] = "pytest not found"
        return

    with _runs_lock:
        _active_runs[run_id]["_process"] = proc

    log_queue = _active_runs[run_id]["queue"]

    for raw_line in iter(proc.stdout.readline, ""):
        clean = _strip_ansi(raw_line)
        log_queue.put(clean)
        with _runs_lock:
            _active_runs[run_id]["logs"].append(clean)

    proc.wait()

    summary = f"\n── 执行完成 (exit code: {proc.returncode}) ──\n"
    log_queue.put(summary)
    with _runs_lock:
        _active_runs[run_id]["logs"].append(summary)
        _active_runs[run_id]["status"] = "completed"
        _active_runs[run_id]["exit_code"] = proc.returncode

    try:
        target_file.unlink()
    except OSError:
        pass
