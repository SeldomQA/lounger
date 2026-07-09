def pytest_xhtml_report_title(report):
    report.title = "Lounger Test Report"


# Optional post-run notification example:
#
# from lounger.utils.variables import ExtractVar
# from support.notify import register_notifications
#
# _extractor = ExtractVar()
# register_notifications(
#     webhook_url=_extractor.config("dingtalk_webhook"),
#     secret=_extractor.config("dingtalk_secret"),
# )
