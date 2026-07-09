import json
import os
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import pytest
from pytest_req.log import log_cfg

from lounger import __version__
from lounger.log import log
from lounger.plugin_hooks import build_test_run_summary, run_after_run_finish, run_after_session_finish
from lounger.pytest_extend.screenshot import screenshot_base64

LOG_STREAM = StringIO()

html_title = "Lounger Test Report"

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
    # setting log format
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</> |<level> {level} | {message}</level>"
    log_cfg.set_level(format=log_format)


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
    report.description = str(item.function.__doc__)
    extra = getattr(report, 'extra', [])
    if report.when == 'call':
        xfail = hasattr(report, 'wasxfail')
        if (report.skipped and xfail) or (report.failed and not xfail):
            page = item.funcargs.get('page')
            if page is not None:
                # add screenshot to HTML report.
                image = screenshot_base64(page)
                if pytest_html:
                    extra.append(pytest_html.extras.image(image, mime_type='image/png'))

        # Empty memory stream
        LOG_STREAM.truncate(0)
        LOG_STREAM.seek(0)

    report.extras = extra


def pytest_addoption(parser: Any) -> None:
    """
    Add pytest option
    """
    group = parser.getgroup("lounger", "Lounger")
    group.addoption(
        "--html-title",
        action="store",
        default=[],
        help="Specifies the title of the pytest-xhtml test report",
    ),
    group.addoption(
        "--env",
        action="store",
        default=[],
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
            # Unwrap bound method to get the underlying function
            if hasattr(func, "__func__"):
                raw_func = func.__func__
            else:
                raw_func = func
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

            # Replace the test item's function object
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

    run_after_session_finish(summary)
    run_after_run_finish(report_path, summary)
