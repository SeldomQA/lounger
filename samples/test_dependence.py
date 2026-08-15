from lounger.testdata import get_md5
from lounger.utils import cache
from lounger.utils import dependent_func


def user_login(username, password):
    """
    模拟用户登录，获取登录token
    """
    return get_md5(username + password)


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
