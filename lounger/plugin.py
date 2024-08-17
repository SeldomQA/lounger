from typing import Any

import pytest

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
