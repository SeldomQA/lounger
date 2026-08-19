import inspect
import json
import os
import sys
import time
import types
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pytest
from pytest_req.log import log_cfg

from lounger import __version__
from lounger.log import log
from lounger.plugin_hooks import (
    TestRunResult,
    build_test_run_summary,
    run_after_case_finish,
    run_after_run_finish,
    run_after_session_finish,
)
from lounger.pytest_extend.screenshot import screenshot_base64

LOG_STREAM = StringIO()

html_title = "Lounger Test Report"

# Per-item timing for after_case_finish (nodeid -> monotonic start time)
_item_start_times: dict[str, float] = {}
_item_finished: set[str] = set()

logo = rf"""
    __                                 
   / /___  __  ______  ____ ____  _____
  / / __ \/ / / / __ \/ __ `/ _ \/ ___/
 / / /_/ / /_/ / / / / /_/ /  __/ /    
/_/\____/\__,_/_/ /_/\__, /\___/_/     
                    /____/             v{__version__}
"""


@pytest.fixture(scope="session", autouse=True)
def setup_log():
    """
    setup log
    """
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</> |<level> {level} | {message}</level>"
    _configure_logging(log_format)


def _configure_logging(log_format: str) -> None:
    """
    Configure the loguru console handler, bound to the real interpreter stderr.

    pytest_req's ``log_cfg.set_level`` binds the console handler to the
    *current* ``sys.stderr`` object. pytest replaces ``sys.stderr`` with its
    capture streams — and nested pytester sessions replace it again — and those
    streams are closed when capture ends, leaving loguru writing to a closed
    file ("I/O operation on closed file"). Binding to ``sys.__stderr__`` (the
    real interpreter stderr, never replaced or closed) keeps logging working
    in every environment.

    :param log_format: loguru format string for the console handler.
    """
    real_stderr = sys.__stderr__
    saved_stderr = sys.stderr
    sys.stderr = real_stderr
    try:
        log_cfg.set_level(format=log_format)
    finally:
        sys.stderr = saved_stderr


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # print logo
    log.info(logo)

    # Here we fetch the command-line argument using config object
    global html_title
    title = config.getoption("--html-title")
    if title:
        html_title = title
    # add env markers
    config.addinivalue_line(
        "markers", "env(name): mark test to run only on named environment"
    )


def pytest_runtest_setup(item: Any) -> None:
    """
    Called to perform the setup phase for a test item.
    """
    _item_start_times[item.nodeid] = time.monotonic()

    env_names = [mark.args[0] for mark in item.iter_markers(name="env")]
    if env_names:
        if item.config.getoption("--env") not in env_names:
            pytest.skip(f"test requires env in {env_names}")


def pytest_xhtml_report_title(report):
    """
    Configures the pytest-xhtml report title based on command-line options.
    :param report:
    :return:
    """
    global html_title
    if report.title.endswith(".html"):
        report.title = html_title


def pytest_xhtml_results_table_header(cells):
    cells.insert(2, "<th>Description</th>")
    cells.insert(3, '<th class="sortable time" data-column-type="time">Time</th>')


def pytest_xhtml_results_table_row(report, cells):
    if hasattr(report, "description"):
        cells.insert(2, f"<td>{report.description}</td>")
    else:
        cells.insert(2, "<td>No description</td>")
    cells.insert(3, f'<td class="col-time">{datetime.now(timezone.utc)}</td>')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item):
    outcome = yield
    pytest_html = item.config.pluginmanager.getplugin('html')
    report = outcome.get_result()
    # `item.function` may be missing on exotic item types; guard so a single
    # attribute access can never fail the whole test run.
    report.description = str(getattr(item.function, "__doc__", "") or "")
    extra = getattr(report, 'extra', [])
    if report.when == 'call':
        # add screenshot to HTML report (failure / xfail only)
        _attach_failure_screenshot(item, report, pytest_html, extra)

        # Empty memory stream
        LOG_STREAM.truncate(0)
        LOG_STREAM.seek(0)

        # Case-level hook: fired before the report is written (3.12)
        _trigger_after_case_finish(item, report)
    elif report.when == 'setup' and not report.passed:
        # Setup-time failures/skips never reach 'call'; notify once here.
        _trigger_after_case_finish(item, report)

    report.extras = extra


def _attach_failure_screenshot(item, report, pytest_html, extra: list) -> bool:
    """
    Attach a page screenshot to the HTML report for failed (or xfailed) cases.

    Extracted from ``pytest_runtest_makereport`` so it can be unit-tested
    without a real browser (stub :func:`screenshot_base64` / fake ``page``).

    :param item: The pytest test item (must expose ``funcargs``).
    :param report: The ``TestReport`` whose ``when == "call"``.
    :param pytest_html: The pytest-html plugin instance (or ``None``).
    :param extra: The report's ``extra`` list, mutated in place.
    :return: True if a screenshot was attached.
    """
    xfail = hasattr(report, 'wasxfail')
    if not ((report.skipped and xfail) or (report.failed and not xfail)):
        return False

    page = item.funcargs.get('page')
    if page is None:
        return False

    image = screenshot_base64(page)
    if pytest_html is not None:
        extra.append(pytest_html.extras.image(image, mime_type='image/png'))
        return True
    return False


def _trigger_after_case_finish(item, report) -> None:
    """
    Fire the ``after_case_finish`` hooks exactly once per test item.

    Runs from ``pytest_runtest_makereport`` (``when == "call"``) — i.e. before
    the HTML report is written — so hooks can attach failure actions or send
    per-case notifications.

    :param item: The pytest test item.
    :param report: The ``TestReport`` whose ``when == "call"``.
    """
    nodeid = item.nodeid
    if nodeid in _item_finished:
        return
    _item_finished.add(nodeid)

    start = _item_start_times.pop(nodeid, None)
    duration = round(time.monotonic() - start, 3) if start is not None else 0.0

    if report.passed:
        status = "passed"
    elif report.failed:
        status = "failed"
    else:
        status = "skipped"

    result = TestRunResult(
        nodeid=nodeid,
        status=status,
        duration=duration,
        description=str(getattr(item.function, "__doc__", "") or ""),
    )
    run_after_case_finish(result)

def pytest_addoption(parser: Any) -> None:
    """
    Add pytest option
    """
    group = parser.getgroup("lounger", "Lounger")
    group.addoption(
        "--html-title",
        action="store",
        default=None,
        help="Specifies the title of the pytest-xhtml test report",
    ),
    group.addoption(
        "--env",
        action="store",
        default=None,
        help="only run tests matching the environment {name}.",
    )
    group.addoption(
        "--run-json",
        action="store",
        help="Pass the JSON of the use case to be executed."
    )


def pytest_collection_modifyitems(config, items):
    """
    Dynamically set Description for parameterized test cases.
    """
    for item in items:
        # Precise check: only process parameterized tests with parameter name 'params'
        if hasattr(item, "callspec") and "params" in item.callspec.params:
            case_data = item.callspec.params["params"]

            # Extract case name (priority: business fields > first value > type name)
            if isinstance(case_data, dict):
                # Prefer explicit description fields
                for key in ("test_case", "test_scene"):
                    if key in case_data:
                        case_name = str(case_data[key])
                        break
                else:
                    case_name = str(next(iter(case_data.values()), "")) if case_data else ""
            elif isinstance(case_data, (list, tuple)):
                case_name = str(case_data[0]) if case_data else ""
            else:
                case_name = str(case_data) if case_data is not None else "none"

            # Create a new function object with updated docstring
            func = item._obj
            # Only rewrite plain functions and bound methods; skip other
            # callables (e.g. functools.partial) to avoid collection crashes
            is_bound_method = inspect.ismethod(func)
            if not (inspect.isfunction(func) or is_bound_method):
                continue

            # Unwrap bound method to get the underlying function
            raw_func = func.__func__ if is_bound_method else func
            new_func = type(raw_func)(
                raw_func.__code__,
                raw_func.__globals__,
                raw_func.__name__,
                raw_func.__defaults__,
                raw_func.__closure__,
            )
            # Copy original function attributes
            new_func.__dict__.update(raw_func.__dict__)
            # Safely append case name to docstring (handle None cases)
            new_func.__doc__ = (raw_func.__doc__ or "") + " | " + case_name

            # Replace the test item's function object.
            # If the original was a bound method (class-based test), re-bind
            # the new function to the same instance so `self` keeps working.
            if is_bound_method:
                item._obj = types.MethodType(new_func, func.__self__)
            else:
                item._obj = new_func

    json_path = config.getoption("--run-json")
    if not json_path:
        return

    if not os.path.exists(json_path):
        pytest.exit(f"JSON file not found: {json_path}")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            target_list = json.load(f)

        target_nodeids = [item["nodeid"] for item in target_list]
    except Exception as e:
        pytest.exit(f"JSON parsing failed: {e}")

    # Create a mapping table
    mapping = {item.nodeid: item for item in items}

    # Build a new execution queue in the order of `target_nodeids`
    selected_items = []
    for nodeid in target_nodeids:
        if nodeid in mapping:
            selected_items.append(mapping[nodeid])
        else:
            log.warning(f"No example was found, skipping execution: {nodeid}")

    # Core: Update the pending execution queue of pytest in place
    items[:] = selected_items


def pytest_sessionfinish(session, exitstatus):
    """
    Trigger lounger post-run hooks after pytest session finishes.
    """
    terminalreporter = session.config.pluginmanager.get_plugin("terminalreporter")
    summary = build_test_run_summary(terminalreporter, exitstatus)

    report_path = None
    option = getattr(session.config, "option", None)
    if option is not None:
        report_path = getattr(option, "htmlpath", None)

    # Release per-item timing state (long-running / web_runner processes).
    _item_start_times.clear()
    _item_finished.clear()

    run_after_session_finish(summary)
    run_after_run_finish(report_path, summary)
