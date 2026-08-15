"""
Playwright smoke test — verifies the browser toolchain works.

Runs in the CI ``web`` job where browsers are installed:

    pytest tests/test_playwright_smoke.py -q

Marked ``integration`` so the default unit run (``pytest tests/``) skips it;
when no browser is available locally the test skips instead of failing.

Note: uses a ``data:`` URL, so it needs no external network.
"""
import pytest

pytestmark = pytest.mark.integration


def test_playwright_smoke():
    """
    Launch chromium, open a page, assert the title.
    """
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"chromium not available: {e}")

        page = browser.new_page()
        page.goto("data:text/html,<title>lounger-smoke</title>")
        assert page.title() == "lounger-smoke"
        browser.close()
