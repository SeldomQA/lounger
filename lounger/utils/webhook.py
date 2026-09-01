import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any

import requests

from lounger.log import log
from lounger.plugin_hooks import TestRunSummary, format_notification


def _text_payload(content: str) -> dict[str, Any]:
    """Build a DingTalk text message payload (dict[str, Any] keeps mypy happy)."""
    return {
        "msgtype": "text",
        "text": {
            "content": content,
        },
    }


def _markdown_payload(title: str, text: str) -> dict[str, Any]:
    """Build a DingTalk markdown message payload."""
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text,
        },
    }


class DingDingWebhook:
    """DingTalk robot webhook client with signature support."""

    def __init__(self, webhook_url: str, secret: str) -> None:
        """
        Initialize the DingTalk webhook client.

        :param webhook_url: The base webhook URL (without timestamp and sign).
        :param secret: The secret key used for signature calculation.
        """
        self.webhook_url = webhook_url
        self.secret = secret

    def is_configured(self) -> bool:
        """Check whether a valid webhook URL has been configured."""
        return bool(self.webhook_url)

    def _get_signed_webhook_url(self) -> str:
        """
        Generate a signed webhook URL with current timestamp and signature.

        :return: Full webhook URL including timestamp and sign query parameters.
        """
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

    def send_summary(self, result, title: str = "Lounger Auto Test Summary") -> None:
        """Send a text summary of test results via DingTalk.

        :param result: pytest terminalreporter object (expects ``_numcollected`` and ``stats``).
        :param title: Custom title for the summary.
        """
        if not self.is_configured():
            log.warning("DingTalk webhook not configured, skip notification.")
            return

        total = getattr(result, "_numcollected", 0)
        stats = getattr(result, "stats", {})
        passed = len(stats.get("passed", []))
        failed = len(stats.get("failed", []))
        errors = len(stats.get("error", []))
        skipped = len(stats.get("skipped", []))
        success_rate = round(((passed + skipped) / total) * 100, 2) if total else 0

        content = (
            f"{title}\n"
            f"--------------------------\n"
            f"📊 Total: {total}\n"
            f"✅ Passed: {passed}\n"
            f"❌ Failed: {failed}\n"
            f"⚠️ Errors: {errors}\n"
            f"⏭️ Skipped: {skipped}\n"
            f"📈 Success Rate: {success_rate}%\n"
            f"--------------------------\n"
            f"Note: Success Rate = (Passed + Skipped) / Total"
        )

        payload = _text_payload(content)

        try:
            response = requests.post(self._get_signed_webhook_url(), json=payload, timeout=10)
            response.raise_for_status()
            log.info(f"DingTalk notification sent: {response.text}")
        except Exception as e:
            log.error(f"Failed to send DingTalk notification: {e}")

    def send_summary_data(
            self,
            summary: TestRunSummary,
            title: str = "Lounger Auto Test Summary",
            report_path: str | None = None,
    ) -> None:
        """
        Send a text summary from a normalized summary object.
        """
        if not self.is_configured():
            log.warning("DingTalk webhook not configured, skip notification.")
            return

        content = (
            f"{title}\n"
            f"--------------------------\n"
            f"📊 Total: {summary.total}\n"
            f"✅ Passed: {summary.passed}\n"
            f"❌ Failed: {summary.failed}\n"
            f"⚠️ Errors: {summary.errors}\n"
            f"⏭️ Skipped: {summary.skipped}\n"
            f"📈 Success Rate: {summary.success_rate}%\n"
            f"--------------------------\n"
            f"Note: Success Rate = (Passed + Skipped) / Total"
        )
        if report_path:
            content += f"\n📄 Report: {report_path}"

        payload = _text_payload(content)

        try:
            response = requests.post(self._get_signed_webhook_url(), json=payload, timeout=10)
            response.raise_for_status()
            log.info(f"DingTalk notification sent: {response.text}")
        except Exception as e:
            log.error(f"Failed to send DingTalk notification: {e}")

    def send_msg(self, title: str, text: str) -> None:
        """
        Send a custom markdown message to DingTalk.

        :param title: Message title.
        :param text: Markdown-formatted message content.
        """
        data = _markdown_payload(title, text)

        try:
            signed_url = self._get_signed_webhook_url()
            requests.post(signed_url, json=data, timeout=10)
        except Exception as e:
            log.error(e)


class FeishuWebhook:
    """Feishu (Lark) robot webhook client."""

    def __init__(self, webhook_url: str, secret: str = "") -> None:
        """
        Initialize the Feishu webhook client.

        :param webhook_url: The full webhook URL.
        :param secret: Optional secret for signature verification.
        """
        self.webhook_url = webhook_url
        self.secret = secret

    def is_configured(self) -> bool:
        """Check whether a valid webhook URL has been configured."""
        return bool(self.webhook_url)

    def _get_signed_webhook_url(self) -> str:
        """Generate a signed webhook URL if secret is configured."""
        if not self.secret:
            return self.webhook_url
        timestamp = str(round(time.time()))
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            string_to_sign_enc, digestmod=hashlib.sha256
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return f"{self.webhook_url}?timestamp={timestamp}&sign={sign}"

    def send_summary_data(
        self,
        summary: TestRunSummary,
        title: str = "Lounger Auto Test Summary",
        report_path: str | None = None,
    ) -> None:
        """
        Send a rich card summary from a normalized summary object.
        """
        if not self.is_configured():
            log.warning("Feishu webhook not configured, skip notification.")
            return

        payload = format_notification(summary, title=title, report_path=report_path)
        status_text = "PASSED" if summary.exitstatus == 0 else "FAILED"
        color = "green" if summary.exitstatus == 0 else "red"

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{payload.status_emoji} {title}"},
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "fields": [
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**📊 Total:** {summary.total}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**✅ Passed:** {summary.passed}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**❌ Failed:** {summary.failed}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**⚠️ Errors:** {summary.errors}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**⏭️ Skipped:** {summary.skipped}"}},
                            {"is_short": True, "text": {"tag": "lark_md", "content": f"**📈 Success Rate:** {summary.success_rate}%"}},
                        ],
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"**Status:** {status_text}"},
                    },
                ],
            },
        }

        if report_path:
            card["card"]["elements"].append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "📄 View Report"},
                    "url": report_path,
                    "type": "primary",
                }],
            })

        try:
            response = requests.post(self._get_signed_webhook_url(), json=card, timeout=10)
            response.raise_for_status()
            log.info(f"Feishu notification sent: {response.text}")
        except Exception as e:
            log.error(f"Failed to send Feishu notification: {e}")


class WeComWebhook:
    """WeCom (企业微信) robot webhook client."""

    def __init__(self, webhook_url: str) -> None:
        """
        Initialize the WeCom webhook client.

        :param webhook_url: The full webhook URL (no signature needed).
        """
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        """Check whether a valid webhook URL has been configured."""
        return bool(self.webhook_url)

    def send_summary_data(
        self,
        summary: TestRunSummary,
        title: str = "Lounger Auto Test Summary",
        report_path: str | None = None,
    ) -> None:
        """
        Send a markdown summary from a normalized summary object.
        """
        if not self.is_configured():
            log.warning("WeCom webhook not configured, skip notification.")
            return

        payload = format_notification(summary, title=title, report_path=report_path)
        status_text = "PASSED" if summary.exitstatus == 0 else "FAILED"

        md_content = (
            f"## {payload.status_emoji} {title}\n"
            f"> Total: **{summary.total}** | "
            f"Passed: **{summary.passed}** | "
            f"Failed: **{summary.failed}**\n"
            f"> Errors: **{summary.errors}** | "
            f"Skipped: **{summary.skipped}** | "
            f"Rate: **{summary.success_rate}%**\n\n"
            f"**Status:** <font color=\"{'info' if summary.exitstatus == 0 else 'warning'}\">{status_text}</font>"
        )
        if report_path:
            md_content += f"\n[View Report]({report_path})"

        data = {
            "msgtype": "markdown",
            "markdown": {"content": md_content},
        }

        try:
            response = requests.post(self.webhook_url, json=data, timeout=10)
            response.raise_for_status()
            log.info(f"WeCom notification sent: {response.text}")
        except Exception as e:
            log.error(f"Failed to send WeCom notification: {e}")


class SlackWebhook:
    """Slack incoming webhook client."""

    def __init__(self, webhook_url: str) -> None:
        """
        Initialize the Slack webhook client.

        :param webhook_url: The full Slack webhook URL.
        """
        self.webhook_url = webhook_url

    def is_configured(self) -> bool:
        """Check whether a valid webhook URL has been configured."""
        return bool(self.webhook_url)

    def send_summary_data(
        self,
        summary: TestRunSummary,
        title: str = "Lounger Auto Test Summary",
        report_path: str | None = None,
    ) -> None:
        """
        Send a Block Kit summary from a normalized summary object.
        """
        if not self.is_configured():
            log.warning("Slack webhook not configured, skip notification.")
            return

        payload = format_notification(summary, title=title, report_path=report_path)
        status_text = "PASSED" if summary.exitstatus == 0 else "FAILED"
        color = "#a6e3a1" if summary.exitstatus == 0 else "#f38ba8"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{payload.status_emoji} {title}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*📊 Total:*\n{summary.total}"},
                    {"type": "mrkdwn", "text": f"*✅ Passed:*\n{summary.passed}"},
                    {"type": "mrkdwn", "text": f"*❌ Failed:*\n{summary.failed}"},
                    {"type": "mrkdwn", "text": f"*⚠️ Errors:*\n{summary.errors}"},
                    {"type": "mrkdwn", "text": f"*⏭️ Skipped:*\n{summary.skipped}"},
                    {"type": "mrkdwn", "text": f"*📈 Rate:*\n{summary.success_rate}%"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Status:* {status_text}"},
            },
        ]

        if report_path:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📄 View Report"},
                    "url": report_path,
                }],
            })

        data = {
            "text": payload.text,
            "blocks": blocks,
            "attachments": [{"color": color, "blocks": []}],
        }

        try:
            response = requests.post(self.webhook_url, json=data, timeout=10)
            response.raise_for_status()
            log.info(f"Slack notification sent: {response.text}")
        except Exception as e:
            log.error(f"Failed to send Slack notification: {e}")
