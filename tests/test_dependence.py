import hashlib

from lounger.utils import cache
from lounger.utils import dependent_func


def generate_md5(input_string):
    """生成md5"""
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()


def user_login(username, password):
    """
    模拟用户登录，获取登录token
    """
    return generate_md5(username + password)


def setup_module():
    # 所有用例开始前：手动清空 cache
    cache.clear()


@dependent_func(user_login, username="tom", password="t123")
def test_case():
    """
    sample test case
    """
    token = cache.get("user_login")
    print("token", token)
