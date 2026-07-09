"""
Post-run hook registry for lounger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class TestRunSummary:
    """
    Summary of a pytest session.
    """

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    exitstatus: int = 0
    __test__ = False

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(((self.passed + self.skipped) / self.total) * 100, 2)


AfterSessionFinishHook = Callable[[TestRunSummary], None]
AfterRunFinishHook = Callable[[Optional[str], TestRunSummary], None]

_after_session_finish_hooks: list[AfterSessionFinishHook] = []
_after_run_finish_hooks: list[AfterRunFinishHook] = []


def register_after_session_finish(func: AfterSessionFinishHook) -> AfterSessionFinishHook:
    """
    Register a hook called after pytest session finishes.
    """
    _after_session_finish_hooks.append(func)
    return func


def register_after_run_finish(func: AfterRunFinishHook) -> AfterRunFinishHook:
    """
    Register a hook called after run summary and report path are available.
    """
    _after_run_finish_hooks.append(func)
    return func


def run_after_session_finish(summary: TestRunSummary) -> None:
    """
    Trigger all after-session hooks.
    """
    for hook in list(_after_session_finish_hooks):
        hook(summary)


def run_after_run_finish(report_path: Optional[str], summary: TestRunSummary) -> None:
    """
    Trigger all after-run hooks.
    """
    for hook in list(_after_run_finish_hooks):
        hook(report_path, summary)


def build_test_run_summary(terminalreporter, exitstatus: int) -> TestRunSummary:
    """
    Build a summary object from pytest terminalreporter.
    """
    if terminalreporter is None:
        return TestRunSummary(exitstatus=exitstatus)

    stats = getattr(terminalreporter, "stats", {})
    return TestRunSummary(
        total=getattr(terminalreporter, "_numcollected", 0),
        passed=len(stats.get("passed", [])),
        failed=len(stats.get("failed", [])),
        errors=len(stats.get("error", [])),
        skipped=len(stats.get("skipped", [])),
        exitstatus=exitstatus,
    )


def reset_hooks() -> None:
    """
    Clear registered hooks. Primarily for tests.
    """
    _after_session_finish_hooks.clear()
    _after_run_finish_hooks.clear()
