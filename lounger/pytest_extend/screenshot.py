import base64

from playwright.sync_api import Page


def screenshot_base64(page: Page):
    """
    Obtain a base64 encoded screenshot
    :param page:
    :return:
    """
    img = page.screenshot(type='png', path=None)
    img_base64 = base64.b64encode(img).decode('utf-8')
    return img_base64
