"""
Tests for the execution-chain hooks (docs/development_plan.md §3.12).

Acceptance points covered:

- ``before_execute_step`` / ``after_execute_step`` / ``on_execute_step_error``
  fire at the right time with the right arguments (``case_step``, ``resp``/``exc``);
- ``after_case_finish`` fires once per item from ``pytest_runtest_makereport``
  (before the report is written) with nodeid / status / duration / description;
- old ``execute_step`` callers keep working (no signature change).
"""
import time
from types import SimpleNamespace

import pytest

from lounger.case import execute_step
from lounger.plugin import _trigger_after_case_finish
from lounger.plugin_hooks import (
    TestRunResult,
    register_after_case_finish,
    register_after_execute_step,
    register_before_execute_step,
    register_on_execute_step_error,
    reset_hooks,
    run_after_execute_step,
    run_before_execute_step,
    run_on_execute_step_error,
)

# ── registry-level: hooks fire with correct arguments ─────────────────────

def test_registry_runs_hooks_with_arguments():
    reset_hooks()
    calls = {"before": [], "after": [], "error": []}

    @register_before_execute_step
    def on_before(step):
        calls["before"].append(step)

    @register_after_execute_step
    def on_after(step, resp):
        calls["after"].append((step, resp))

    @register_on_execute_step_error
    def on_error(step, exc):
        calls["error"].append((step, exc))

    step = {"name": "s1", "request": {"url": "/x"}}
    resp = object()

    run_before_execute_step(step)
    run_after_execute_step(step, resp)
    run_on_execute_step_error(step, ValueError("boom"))

    assert calls["before"] == [step]
    assert calls["after"] == [(step, resp)]
    assert calls["error"][0][0] is step
    assert isinstance(calls["error"][0][1], ValueError)

    reset_hooks()


def test_registry_invokes_in_registration_order():
    reset_hooks()
    order = []

    @register_before_execute_step
    def first(step):
        order.append("first")

    @register_before_execute_step
    def second(step):
        order.append("second")

    run_before_execute_step({})
    assert order == ["first", "second"]

    reset_hooks()


# ── execute_step integration: timing of before/after/error ────────────────

def test_execute_step_calls_before_then_after_on_success(monkeypatch):
    reset_hooks()
    events = []

    @register_before_execute_step
    def on_before(step):
        events.append("before")

    @register_after_execute_step
    def on_after(step, resp):
        events.append(f"after:{resp}")

    class FakeClient:
        def send_request(self, **kwargs):
            events.append("request")
            return "OK"

    monkeypatch.setattr("lounger.request.request_client", FakeClient())

    execute_step({"name": "s1", "request": {"url": "/x"}})

    assert events == ["before", "request", "after:OK"]

    reset_hooks()


def test_execute_step_calls_error_hook_and_reraises(monkeypatch):
    reset_hooks()
    events = []

    @register_on_execute_step_error
    def on_error(step, exc):
        events.append(("error", type(exc).__name__))

    @register_after_execute_step
    def on_after(step, resp):
        events.append("after")  # must NOT fire on failure

    class FakeClient:
        def send_request(self, **kwargs):
            raise ConnectionError("down")

    monkeypatch.setattr("lounger.request.request_client", FakeClient())

    with pytest.raises(ConnectionError):
        execute_step({"name": "s1", "request": {"url": "/x"}})

    assert events == [("error", "ConnectionError")]

    reset_hooks()


def test_execute_step_error_hook_receives_original_step(monkeypatch):
    reset_hooks()
    captured = {}

    @register_on_execute_step_error
    def on_error(step, exc):
        captured["step"] = step
        captured["exc"] = exc

    class FakeClient:
        def send_request(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("lounger.request.request_client", FakeClient())

    step = {"name": "s1", "request": {"url": "/x"}}
    with pytest.raises(RuntimeError):
        execute_step(step)

    assert captured["step"] is step
    assert isinstance(captured["exc"], RuntimeError)

    reset_hooks()


def test_execute_step_without_hooks_still_works(monkeypatch):
    """Old callers are unaffected: no hooks registered = original behaviour."""
    reset_hooks()

    class FakeClient:
        def send_request(self, **kwargs):
            return "OK"

    monkeypatch.setattr("lounger.request.request_client", FakeClient())

    # Should not raise
    execute_step({"name": "s1", "request": {"url": "/x"}})

    reset_hooks()


# ── after_case_finish ─────────────────────────────────────────────────────

def test_after_case_finish_fires_once_with_result(monkeypatch):
    reset_hooks()
    results = []

    @register_after_case_finish
    def on_finish(result):
        results.append(result)

    item = SimpleNamespace(
        nodeid="test_demo.py::test_ok",
        function=SimpleNamespace(__doc__="my case"),
    )
    report = SimpleNamespace(passed=True, failed=False, skipped=False)

    monkeypatch.setattr("lounger.plugin._item_start_times", {"test_demo.py::test_ok": time.monotonic()})
    monkeypatch.setattr("lounger.plugin._item_finished", set())

    _trigger_after_case_finish(item, report)
    # Second call for the same item must be ignored (fires once)
    _trigger_after_case_finish(item, report)

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, TestRunResult)
    assert result.nodeid == "test_demo.py::test_ok"
    assert result.status == "passed"
    assert result.description == "my case"
    assert result.duration >= 0

    reset_hooks()


def test_after_case_finish_status_failed(monkeypatch):
    reset_hooks()
    results = []

    @register_after_case_finish
    def on_finish(result):
        results.append(result)

    item = SimpleNamespace(
        nodeid="test_demo.py::test_bad",
        function=SimpleNamespace(__doc__=""),
    )
    report = SimpleNamespace(passed=False, failed=True, skipped=False)

    monkeypatch.setattr("lounger.plugin._item_start_times", {"test_demo.py::test_bad": time.monotonic()})
    monkeypatch.setattr("lounger.plugin._item_finished", set())

    _trigger_after_case_finish(item, report)

    assert results[0].status == "failed"

    reset_hooks()


def test_after_case_finish_result_matches_run_api():
    """TestRunResult is a plain dataclass usable by business hooks."""
    r = TestRunResult(nodeid="a::b", status="passed", duration=1.2, description="d")
    assert r.nodeid == "a::b"
    assert r.status == "passed"
    assert r.duration == 1.2
    assert r.description == "d"
