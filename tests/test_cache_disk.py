import time

import pytest

from lounger.log import log
from lounger.testdata import get_md5
from lounger.utils import disk_cache


@disk_cache()
def login_token(username: str, password: str):
    """
    模拟：生成登录token
    """
    time.sleep(5)
    token = get_md5(username + password)
    return token


def setup_module():
    # 所有用例开始前：手动清空 cache
    disk_cache().clear()


@pytest.fixture()
def get_token():
    """
    获取登录token
    """
    return login_token("tom", "tom123")


def test_login_one(get_token):
    log.info(f"token: {get_token}")


def test_login_tow(get_token):
    log.info(f"token: {get_token}")


def test_login_three(get_token):
    log.info(f"token: {get_token}")
