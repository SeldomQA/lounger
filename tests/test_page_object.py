"""
playwright page object demo

run:
> pytest -vs --browser=chromium --headed test_page_object.py
"""
import re

from playwright.sync_api import expect, Page

from lounger.po import BasePage, Locator


# page
class BingPage(BasePage):
    search_input = Locator('id=sb_form_q', describe="bing搜索框")
    search_icon = Locator('id=search_icon', describe="bing搜索按钮")


def test_bing_search(page: Page):
    # 进入指定URL
    page.goto("https://cn.bing.com")

    bp = BingPage(page)
    # 获得元素
    bp.search_input.highlight()
    bp.search_input.fill("playwright")
    bp.search_icon.highlight()
    bp.search_icon.screenshot(path="./docs/abc.png")
    bp.search_icon.click()

    # 断言URL
    expect(page).to_have_title(re.compile("playwright"))
