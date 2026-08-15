from types import SimpleNamespace

from lounger.integrations.dingtalk import register_dingtalk_integration
from lounger.plugin import pytest_sessionfinish
from lounger.plugin_hooks import (
    TestRunSummary,
    build_test_run_summary,
    register_after_run_finish,
    register_after_session_finish,
    reset_hooks,
)


class DummyPluginManager:
    def __init__(self, terminalreporter):
        self._terminalreporter = terminalreporter

    def get_plugin(self, name):
        if name == "terminalreporter":
            return self._terminalreporter
        return None


def test_build_test_run_summary():
    terminalreporter = SimpleNamespace(
        _numcollected=10,
        stats={
            "passed": [1, 2, 3],
            "failed": [1],
            "error": [1, 2],
            "skipped": [1],
        },
    )

    summary = build_test_run_summary(terminalreporter, 1)

    assert summary == TestRunSummary(
        total=10,
        passed=3,
        failed=1,
        errors=2,
        skipped=1,
        exitstatus=1,
    )
    assert summary.success_rate == 40.0


def test_pytest_sessionfinish_triggers_registered_hooks():
    reset_hooks()
    calls = {"session": None, "run": None}

    @register_after_session_finish
    def on_session(summary):
        calls["session"] = summary

    @register_after_run_finish
    def on_run(report_path, summary):
        calls["run"] = (report_path, summary)

    terminalreporter = SimpleNamespace(
        _numcollected=5,
        stats={"passed": [1, 2], "failed": [1], "error": [], "skipped": [1]},
    )
    session = SimpleNamespace(
        config=SimpleNamespace(
            pluginmanager=DummyPluginManager(terminalreporter),
            option=SimpleNamespace(htmlpath="reports/result.html"),
        )
    )

    pytest_sessionfinish(session, 1)

    assert calls["session"] is not None
    assert calls["session"].total == 5
    assert calls["run"][0] == "reports/result.html"
    assert calls["run"][1].failed == 1

    reset_hooks()


def test_register_dingtalk_integration_uses_normalized_summary(monkeypatch):
    reset_hooks()
    calls = {"payloads": []}

    def fake_send_summary_data(self, summary, title="Lounger Auto Test Summary", report_path=None):
        calls["payloads"].append((summary, title, report_path))

    monkeypatch.setattr(
        "lounger.utils.webhook.DingDingWebhook.send_summary_data",
        fake_send_summary_data,
    )

    register_dingtalk_integration(
        webhook_url="https://example.invalid/hook",
        secret="secret",
        title="Build Summary",
    )

    terminalreporter = SimpleNamespace(
        _numcollected=3,
        stats={"passed": [1], "failed": [1], "error": [1], "skipped": []},
    )
    session = SimpleNamespace(
        config=SimpleNamespace(
            pluginmanager=DummyPluginManager(terminalreporter),
            option=SimpleNamespace(htmlpath="reports/result.html"),
        )
    )

    pytest_sessionfinish(session, 1)

    assert len(calls["payloads"]) == 2
    assert calls["payloads"][0][1] == "Build Summary"
    assert calls["payloads"][1][2] == "reports/result.html"

    reset_hooks()
