from lounger.commons.load_config import base_url
from lounger.commons.load_config import global_test_config


def test_base_url():
    """
    base_url
    """
    assert base_url == "https://jsonplaceholder.typicode.com"


def test_global_test_config():
    """
    global_test_config
    """
    one = global_test_config("var_one")
    two = global_test_config("var_two")
    assert one == "foo"
    assert two == "bar"
