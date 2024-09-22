import logging
from datetime import datetime, UTC
from io import StringIO
from typing import Any

import pytest
from loguru import logger

from lounger.pytest_extend.screenshot import screenshot_base64

LOG_STREAM = StringIO()

html_title = "Lounger Test Report"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(filename)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    html = config.getoption("--html")
    if html:
        logger.remove()
        logger.add(LOG_STREAM,
                   format="{time: YYYY-MM-DD HH:mm:ss} | <level>{level: <8}</level> | {file: <10} | {message}",
                   level="DEBUG")

    global html_title
    # Here we fetch the command-line argument using config object
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


def pytest_html_report_title(report):
    """
    Configures the pytest-html report title based on command-line options.
    :param report:
    :return:
    """
    global html_title
    report.title = html_title


def pytest_html_results_table_header(cells):
    cells.insert(2, "<th>Description</th>")
    cells.insert(3, '<th class="sortable time" data-column-type="time">Time</th>')


def pytest_html_results_table_row(report, cells):
    cells.insert(2, f"<td>{report.description}</td>")
    cells.insert(3, f'<td class="col-time">{datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")}</td>')


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
                extra.append(pytest_html.extras.image(image, mime_type='image/png'))

        # add Loguru log to HTML report.
        log_content = LOG_STREAM.getvalue()
        if log_content.strip():
            extra.append(pytest_html.extras.text(log_content, "Loguru Log"))
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
        help="Specifies the title of the pytest-html test report",
    )
    group.addoption(
        "--env",
        action="store",
        default=[],
        help="only run tests matching the environment {name}.",
    )
