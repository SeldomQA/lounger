"""
Tests for notification channel integrations (Feishu, WeCom, Slack).
"""
from types import SimpleNamespace

from lounger.plugin import pytest_sessionfinish
from lounger.plugin_hooks import (
    TestRunSummary,
    format_notification,
    reset_hooks,
)

# ── format_notification tests ──────────────────────────────────────────────

class TestFormatNotification:
    def test_pass_summary(self):
        summary = TestRunSummary(total=10, passed=9, failed=0, errors=0, skipped=1, exitstatus=0)
        payload = format_notification(summary, title="Test")

        assert payload.status_emoji == "✅"
        assert "PASSED" in payload.text
        assert "PASSED" in payload.markdown
        assert "Total: 10" in payload.text
        assert "Success Rate: 100.0%" in payload.text  # (9+1)/10 = 100%
        assert payload.report_path is None

    def test_fail_summary(self):
        summary = TestRunSummary(total=10, passed=5, failed=3, errors=2, skipped=0, exitstatus=1)
        payload = format_notification(summary)

        assert payload.status_emoji == "❌"
        assert "FAILED" in payload.text
        assert "FAILED" in payload.markdown

    def test_with_report_path(self):
        summary = TestRunSummary(total=5, passed=5, failed=0, errors=0, skipped=0, exitstatus=0)
        payload = format_notification(summary, report_path="reports/result.html")

        assert payload.report_path == "reports/result.html"
        assert "reports/result.html" in payload.text
        assert "View Report" in payload.markdown

    def test_markdown_table_format(self):
        summary = TestRunSummary(total=8, passed=6, failed=1, errors=1, skipped=0, exitstatus=1)
        payload = format_notification(summary)

        assert "| Metric | Value |" in payload.markdown
        assert "**8**" in payload.markdown
        assert "**6**" in payload.markdown


# ── Feishu webhook tests ──────────────────────────────────────────────────


class TestFeishuWebhook:
    def test_send_summary_data_calls_api(self, monkeypatch):
        from lounger.utils.webhook import FeishuWebhook

        calls = {"url": None, "payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["url"] = url
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = FeishuWebhook(webhook_url="https://open.feishu.cn/hook/test")
        summary = TestRunSummary(total=5, passed=4, failed=1, errors=0, skipped=0, exitstatus=1)
        client.send_summary_data(summary, title="Test Summary")

        assert calls["url"] == "https://open.feishu.cn/hook/test"
        assert calls["payload"]["msg_type"] == "interactive"
        assert "header" in calls["payload"]["card"]
        assert calls["payload"]["card"]["header"]["template"] == "red"

    def test_send_summary_with_report(self, monkeypatch):
        from lounger.utils.webhook import FeishuWebhook

        calls = {"payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = FeishuWebhook(webhook_url="https://open.feishu.cn/hook/test")
        summary = TestRunSummary(total=5, passed=5, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary, report_path="https://example.com/report.html")

        elements = calls["payload"]["card"]["elements"]
        # Should have an action button for report
        action_elements = [e for e in elements if e.get("tag") == "action"]
        assert len(action_elements) == 1
        assert action_elements[0]["actions"][0]["url"] == "https://example.com/report.html"

    def test_not_configured_skips(self, monkeypatch):
        from lounger.utils.webhook import FeishuWebhook

        called = {"posted": False}

        def fake_post(*args, **kwargs):
            called["posted"] = True
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = FeishuWebhook(webhook_url="")
        summary = TestRunSummary(total=1, passed=1, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary)

        assert not called["posted"]

    def test_signed_url(self):
        from lounger.utils.webhook import FeishuWebhook

        client = FeishuWebhook(webhook_url="https://open.feishu.cn/hook/test", secret="mysecret")
        signed = client._get_signed_webhook_url()
        assert "timestamp=" in signed
        assert "sign=" in signed


# ── WeCom webhook tests ──────────────────────────────────────────────────


class TestWeComWebhook:
    def test_send_summary_data_calls_api(self, monkeypatch):
        from lounger.utils.webhook import WeComWebhook

        calls = {"url": None, "payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["url"] = url
            calls["payload"] = json
            return SimpleNamespace(text='{"errcode": 0}', raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = WeComWebhook(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx")
        summary = TestRunSummary(total=10, passed=8, failed=2, errors=0, skipped=0, exitstatus=1)
        client.send_summary_data(summary, title="Build Report")

        assert calls["url"] == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
        assert calls["payload"]["msgtype"] == "markdown"
        assert "Build Report" in calls["payload"]["markdown"]["content"]
        assert "Total: **10**" in calls["payload"]["markdown"]["content"]

    def test_pass_color(self, monkeypatch):
        from lounger.utils.webhook import WeComWebhook

        calls = {"payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["payload"] = json
            return SimpleNamespace(text='{"errcode": 0}', raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = WeComWebhook(webhook_url="https://qyapi.weixin.qq.com/hook")
        summary = TestRunSummary(total=5, passed=5, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary)

        content = calls["payload"]["markdown"]["content"]
        assert "info" in content  # green color for pass

    def test_not_configured_skips(self, monkeypatch):
        from lounger.utils.webhook import WeComWebhook

        called = {"posted": False}

        def fake_post(*args, **kwargs):
            called["posted"] = True
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = WeComWebhook(webhook_url="")
        summary = TestRunSummary(total=1, passed=1, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary)

        assert not called["posted"]


# ── Slack webhook tests ──────────────────────────────────────────────────


class TestSlackWebhook:
    def test_send_summary_data_calls_api(self, monkeypatch):
        from lounger.utils.webhook import SlackWebhook

        calls = {"url": None, "payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["url"] = url
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = SlackWebhook(webhook_url="https://hooks.slack.com/services/T00/B00/xxx")
        summary = TestRunSummary(total=20, passed=18, failed=1, errors=1, skipped=0, exitstatus=1)
        client.send_summary_data(summary, title="CI Results")

        assert calls["url"] == "https://hooks.slack.com/services/T00/B00/xxx"
        assert "blocks" in calls["payload"]
        assert calls["payload"]["blocks"][0]["type"] == "header"
        assert "CI Results" in calls["payload"]["blocks"][0]["text"]["text"]

    def test_pass_color_attachment(self, monkeypatch):
        from lounger.utils.webhook import SlackWebhook

        calls = {"payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = SlackWebhook(webhook_url="https://hooks.slack.com/hook")
        summary = TestRunSummary(total=5, passed=5, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary)

        assert calls["payload"]["attachments"][0]["color"] == "#a6e3a1"

    def test_fail_color_attachment(self, monkeypatch):
        from lounger.utils.webhook import SlackWebhook

        calls = {"payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = SlackWebhook(webhook_url="https://hooks.slack.com/hook")
        summary = TestRunSummary(total=5, passed=3, failed=2, errors=0, skipped=0, exitstatus=1)
        client.send_summary_data(summary)

        assert calls["payload"]["attachments"][0]["color"] == "#f38ba8"

    def test_report_button(self, monkeypatch):
        from lounger.utils.webhook import SlackWebhook

        calls = {"payload": None}

        def fake_post(url, json=None, timeout=None):
            calls["payload"] = json
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = SlackWebhook(webhook_url="https://hooks.slack.com/hook")
        summary = TestRunSummary(total=5, passed=5, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary, report_path="https://ci.example.com/report.html")

        blocks = calls["payload"]["blocks"]
        action_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(action_blocks) == 1
        assert action_blocks[0]["elements"][0]["url"] == "https://ci.example.com/report.html"

    def test_not_configured_skips(self, monkeypatch):
        from lounger.utils.webhook import SlackWebhook

        called = {"posted": False}

        def fake_post(*args, **kwargs):
            called["posted"] = True
            return SimpleNamespace(text="ok", raise_for_status=lambda: None)

        monkeypatch.setattr("requests.post", fake_post)

        client = SlackWebhook(webhook_url="")
        summary = TestRunSummary(total=1, passed=1, failed=0, errors=0, skipped=0, exitstatus=0)
        client.send_summary_data(summary)

        assert not called["posted"]


# ── Integration registration tests ────────────────────────────────────────


class DummyPluginManager:
    def __init__(self, terminalreporter):
        self._terminalreporter = terminalreporter

    def get_plugin(self, name):
        if name == "terminalreporter":
            return self._terminalreporter
        return None


class TestFeishuIntegration:
    def test_register_and_trigger(self, monkeypatch):
        from lounger.integrations.feishu import register_feishu_integration

        reset_hooks()
        calls = {"payloads": []}

        def fake_send(self, summary, title="Lounger Auto Test Summary", report_path=None):
            calls["payloads"].append((summary, title, report_path))

        monkeypatch.setattr(
            "lounger.utils.webhook.FeishuWebhook.send_summary_data",
            fake_send,
        )

        register_feishu_integration(
            webhook_url="https://open.feishu.cn/hook/test",
            secret="secret",
            title="Feishu Summary",
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
        assert calls["payloads"][0][1] == "Feishu Summary"
        assert calls["payloads"][1][2] == "reports/result.html"

        reset_hooks()


class TestWeComIntegration:
    def test_register_and_trigger(self, monkeypatch):
        from lounger.integrations.wecom import register_wecom_integration

        reset_hooks()
        calls = {"payloads": []}

        def fake_send(self, summary, title="Lounger Auto Test Summary", report_path=None):
            calls["payloads"].append((summary, title, report_path))

        monkeypatch.setattr(
            "lounger.utils.webhook.WeComWebhook.send_summary_data",
            fake_send,
        )

        register_wecom_integration(
            webhook_url="https://qyapi.weixin.qq.com/hook",
            title="WeCom Report",
        )

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

        pytest_sessionfinish(session, 0)

        assert len(calls["payloads"]) == 2
        assert calls["payloads"][0][1] == "WeCom Report"
        assert calls["payloads"][1][2] == "reports/result.html"

        reset_hooks()


class TestSlackIntegration:
    def test_register_and_trigger(self, monkeypatch):
        from lounger.integrations.slack import register_slack_integration

        reset_hooks()
        calls = {"payloads": []}

        def fake_send(self, summary, title="Lounger Auto Test Summary", report_path=None):
            calls["payloads"].append((summary, title, report_path))

        monkeypatch.setattr(
            "lounger.utils.webhook.SlackWebhook.send_summary_data",
            fake_send,
        )

        register_slack_integration(
            webhook_url="https://hooks.slack.com/hook",
            title="Slack CI",
        )

        terminalreporter = SimpleNamespace(
            _numcollected=10,
            stats={"passed": [1, 2, 3], "failed": [], "error": [], "skipped": []},
        )
        session = SimpleNamespace(
            config=SimpleNamespace(
                pluginmanager=DummyPluginManager(terminalreporter),
                option=SimpleNamespace(htmlpath="reports/result.html"),
            )
        )

        pytest_sessionfinish(session, 0)

        assert len(calls["payloads"]) == 2
        assert calls["payloads"][0][1] == "Slack CI"
        assert calls["payloads"][1][2] == "reports/result.html"

        reset_hooks()
