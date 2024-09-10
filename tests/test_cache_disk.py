import hashlib
import time

import pytest

from lounger.log import log
from lounger.utils import disk_cache


def generate_md5(input_string):
    """生成md5"""
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()


@disk_cache()
def login_token(username: str, password: str):
    """
    模拟：生成登录token
    """
    time.sleep(5)
    token = generate_md5(username + password)
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
