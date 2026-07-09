"""
DingTalk integration hooks.
"""
from __future__ import annotations

from typing import Optional

from lounger.plugin_hooks import (
    TestRunSummary,
    register_after_run_finish,
    register_after_session_finish,
)
from lounger.utils.webhook import DingDingWebhook


class DingTalkIntegration:
    """
    Send session summaries to DingTalk.
    """

    def __init__(self, webhook_url: str, secret: str, title: str = "Lounger Auto Test Summary") -> None:
        self.client = DingDingWebhook(webhook_url=webhook_url, secret=secret)
        self.title = title

    def after_session_finish(self, summary: TestRunSummary) -> None:
        self.client.send_summary_data(summary=summary, title=self.title)

    def after_run_finish(self, report_path: Optional[str], summary: TestRunSummary) -> None:
        self.client.send_summary_data(summary=summary, title=self.title, report_path=report_path)


def register_dingtalk_integration(
        webhook_url: str,
        secret: str,
        title: str = "Lounger Auto Test Summary",
) -> DingTalkIntegration:
    """
    Create and register a DingTalk integration.
    """
    integration = DingTalkIntegration(webhook_url=webhook_url, secret=secret, title=title)
    register_after_session_finish(integration.after_session_finish)
    register_after_run_finish(integration.after_run_finish)
    return integration
