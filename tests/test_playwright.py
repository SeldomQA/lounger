"""
playwright demo

run test：
> pytest --browser=chromium --headed -vs test_playwright.py
"""
import re
import time
from playwright.sync_api import Page, expect


def test_has_title(page: Page):
    page.goto("https://cn.bing.com")

    # Expect a title "to contain" a substring.
    expect(page).to_have_title(re.compile("Bing"))


def test_get_started_link(page: Page):
    page.goto("https://cn.bing.com")
    input = page.locator("#sb_form_q")
    input.type("playwright")
    input.press("Enter")
    time.sleep(5)

    # Expects page to have a heading with the name of "Installation | Playwright".
    search_result = page.get_by_role("link", name='Installation | Playwright').first
    expect(search_result).to_be_visible()
