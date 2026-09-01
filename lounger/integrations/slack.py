"""
Slack integration hooks.
"""
from __future__ import annotations

from typing import Optional

from lounger.plugin_hooks import (
    TestRunSummary,
    register_after_run_finish,
    register_after_session_finish,
)
from lounger.utils.webhook import SlackWebhook


class SlackIntegration:
    """
    Send session summaries to Slack.
    """

    def __init__(self, webhook_url: str, title: str = "Lounger Auto Test Summary") -> None:
        self.client = SlackWebhook(webhook_url=webhook_url)
        self.title = title

    def after_session_finish(self, summary: TestRunSummary) -> None:
        self.client.send_summary_data(summary=summary, title=self.title)

    def after_run_finish(self, report_path: Optional[str], summary: TestRunSummary) -> None:
        self.client.send_summary_data(summary=summary, title=self.title, report_path=report_path)


def register_slack_integration(
        webhook_url: str,
        title: str = "Lounger Auto Test Summary",
) -> SlackIntegration:
    """
    Create and register a Slack integration.
    """
    integration = SlackIntegration(webhook_url=webhook_url, title=title)
    register_after_session_finish(integration.after_session_finish)
    register_after_run_finish(integration.after_run_finish)
    return integration
