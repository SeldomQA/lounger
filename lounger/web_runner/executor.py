"""
Background test execution — thin web_runner wrapper over
lounger.services.test_execution.

Run history is memory-bounded: finished runs are archived to
``<scan_dir>/reports/runs/`` (see ``archive_run``), so a long-running web
server does not grow unbounded (3.8 §1).
"""

from lounger.services.test_execution import archive_run, start_run

from . import state

#: How many finished runs to keep in memory (older ones go to reports/runs/).
KEEP_RECENT_RUNS = 20


def _execute_tests(run_id: str, nodeids: list[str], verbosity: str = "verbose") -> None:
    """Run pytest in a background thread; archive the finished run."""
    start_run(
        runs=state._active_runs,
        scan_dir=state._scan_dir,
        run_id=run_id,
        nodeids=nodeids,
        verbosity=verbosity,
        lock=state._runs_lock,
        strip_ansi=state._strip_ansi,
    )


def archive_finished_runs() -> None:
    """
    Archive all finished runs that exceed the in-memory budget.

    Call after a run completes (or periodically) to keep memory bounded.
    """
    for run_id in list(state._active_runs):
        info = state._active_runs.get(run_id)
        if info is None:
            continue
        if info.get("status") in ("completed", "error"):
            archive_run(
                runs=state._active_runs,
                scan_dir=state._scan_dir,
                run_id=run_id,
                keep_recent=KEEP_RECENT_RUNS,
                lock=state._runs_lock,
            )
