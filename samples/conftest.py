from lounger.utils.webhook import DingDingWebhook


def pytest_xhtml_report_title(report):
    report.title = "Lounger Test Report"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    webhook = DingDingWebhook(
        webhook_url="dingtalk_webhook", # 修改为真实地址
        secret="dingtalk_secret"        # 修改为真实密钥
    )
    webhook.send_summary(title="Lounger Auto Test Summary", result=terminalreporter)
