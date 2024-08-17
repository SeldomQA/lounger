from datetime import datetime
from typing import Any

import pytest

from lounger.pytest_extend.screenshot import screenshot_base64

html_title = "Lounger Test Report"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    global html_title
    # Here we fetch the command-line argument using config object
    title = config.getoption("--html-title")
    if title:
        html_title = title


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
    cells.insert(3, f'<td class="col-time">{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}</td>')


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
        report.extra = extra


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
