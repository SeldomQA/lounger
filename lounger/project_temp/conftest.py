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

# Optional template function registration example:
#
# from lounger.runtime import register_template_func
#
# def random_email():
#     return "user@example.com"
#
# register_template_func("random_email", random_email)

# Optional execution-chain hooks example (request before/after + failure notify):
#
# from lounger.plugin_hooks import (
#     register_after_case_finish,
#     register_after_execute_step,
#     register_before_execute_step,
#     register_on_execute_step_error,
# )
#
# @register_before_execute_step
# def log_request_start(case_step):
#     log.info(f"▶ {case_step.get('name')} — before request")
#
# @register_after_execute_step
# def log_request_end(case_step, resp):
#     log.info(f"✓ {case_step.get('name')} — {getattr(resp, 'status_code', '?')}")
#
# @register_on_execute_step_error
# def notify_step_error(case_step, exc):
#     log.error(f"✗ {case_step.get('name')} — {exc}")   # e.g. send to DingTalk here
#
# @register_after_case_finish
# def notify_case_finish(result):
#     # result: TestRunResult(nodeid, status, duration, description)
#     log.info(f"📦 {result.nodeid} → {result.status} ({result.duration}s)")
#
# Note: prefer these hooks over monkey-patching lounger.case.execute_step.
