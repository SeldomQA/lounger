"""
Lounger hook registry: post-run hooks and execution-chain hooks.

Two families of extension points are provided:

1. Run-level hooks (session / run summaries):
   - ``register_after_session_finish`` — after the whole pytest session;
   - ``register_after_run_finish`` — after the run summary + report path exist.

2. Case / execution-chain hooks (business logic around request steps):
   - ``register_before_execute_step`` — before a YAML step is dispatched
     (request / centrifuge);
   - ``register_after_execute_step`` — after a step dispatched successfully;
   - ``register_on_execute_step_error`` — when a step raises;
   - ``register_after_case_finish`` — after each pytest test item finishes
     (fired from ``pytest_runtest_makereport`` before the report is written).

Registration order = invocation order.  Hooks are plain callables; use the
``@register_*`` decorator or pass a function explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


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


@dataclass
class TestRunResult:
    """
    Result of a single pytest test item (case).

    Passed to ``after_case_finish`` hooks.
    """

    nodeid: str = ""
    status: str = "unknown"  # passed | failed | skipped
    duration: float = 0.0
    description: str = ""
    __test__ = False


AfterSessionFinishHook = Callable[[TestRunSummary], None]
AfterRunFinishHook = Callable[[Optional[str], TestRunSummary], None]
BeforeExecuteStepHook = Callable[[dict], None]
AfterExecuteStepHook = Callable[[dict, Any], None]
OnExecuteStepErrorHook = Callable[[dict, Exception], None]
AfterCaseFinishHook = Callable[[TestRunResult], None]

_after_session_finish_hooks: list[AfterSessionFinishHook] = []
_after_run_finish_hooks: list[AfterRunFinishHook] = []
_before_execute_step_hooks: list[BeforeExecuteStepHook] = []
_after_execute_step_hooks: list[AfterExecuteStepHook] = []
_on_execute_step_error_hooks: list[OnExecuteStepErrorHook] = []
_after_case_finish_hooks: list[AfterCaseFinishHook] = []


# ── run-level hooks ────────────────────────────────────────────────────────

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


# ── execution-chain hooks (case.py::execute_step) ─────────────────────────

def register_before_execute_step(func: BeforeExecuteStepHook) -> BeforeExecuteStepHook:
    """
    Register a hook called before each YAML step is dispatched.

    :param func: ``func(case_step: dict) -> None``
    """
    _before_execute_step_hooks.append(func)
    return func


def register_after_execute_step(func: AfterExecuteStepHook) -> AfterExecuteStepHook:
    """
    Register a hook called after each YAML step dispatched successfully.

    :param func: ``func(case_step: dict, resp) -> None``
    """
    _after_execute_step_hooks.append(func)
    return func


def register_on_execute_step_error(func: OnExecuteStepErrorHook) -> OnExecuteStepErrorHook:
    """
    Register a hook called when a YAML step raises.

    :param func: ``func(case_step: dict, exc: Exception) -> None``
    """
    _on_execute_step_error_hooks.append(func)
    return func


def run_before_execute_step(case_step: dict) -> None:
    """
    Trigger all before-execute-step hooks.
    """
    for hook in list(_before_execute_step_hooks):
        hook(case_step)


def run_after_execute_step(case_step: dict, resp: Any) -> None:
    """
    Trigger all after-execute-step hooks.
    """
    for hook in list(_after_execute_step_hooks):
        hook(case_step, resp)


def run_on_execute_step_error(case_step: dict, exc: Exception) -> None:
    """
    Trigger all on-execute-step-error hooks.
    """
    for hook in list(_on_execute_step_error_hooks):
        hook(case_step, exc)


# ── case-level hooks (pytest_runtest_makereport) ──────────────────────────

def register_after_case_finish(func: AfterCaseFinishHook) -> AfterCaseFinishHook:
    """
    Register a hook called after each test case finishes.

    The hook runs from ``pytest_runtest_makereport`` before the HTML report
    is written, so hooks can still attach failure actions / per-case
    notifications.

    :param func: ``func(result: TestRunResult) -> None``
    """
    _after_case_finish_hooks.append(func)
    return func


def run_after_case_finish(result: TestRunResult) -> None:
    """
    Trigger all after-case-finish hooks.
    """
    for hook in list(_after_case_finish_hooks):
        hook(result)


# ── helpers ───────────────────────────────────────────────────────────────

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
    _before_execute_step_hooks.clear()
    _after_execute_step_hooks.clear()
    _on_execute_step_error_hooks.clear()
    _after_case_finish_hooks.clear()
