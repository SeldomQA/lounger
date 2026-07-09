import base64
import hashlib
import hmac
import time
import urllib.parse

import requests

from lounger.log import log
from lounger.plugin_hooks import TestRunSummary


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

        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

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

        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

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
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text,
            },
        }

        try:
            signed_url = self._get_signed_webhook_url()
            requests.post(signed_url, json=data, timeout=10)
        except Exception as e:
            log.error(e)
