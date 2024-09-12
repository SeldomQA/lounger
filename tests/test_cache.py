from lounger.utils import cache


def setup_function():
    """
    测试前执行
    """
    cache.set({"key1": "value1", "key2": "value2"})


def test_get_cache():
    d = cache.get("key1")
    assert d == "value1"


def test_set_cache():
    """
    设置缓存
    """
    cache.set({"token": "123"})
    t = cache.get("token")
    assert t == "123"


def test_set_cache_more():
    """
    设置更复杂的缓存数据
    """
    cache.set({"user": [{"name": "tom", "age": 11}]})
    m = cache.get("user")
    assert m == [{"name": "tom", "age": 11}]


def test_clear_cache():
    """
    清除指定数据
    """
    cache.clear("key1")
    d = cache.get("key1")
    assert d is None


def test_clear_all_cache():
    """
    清除所有缓存
    """
    cache.clear()
    d = cache.get()
    assert d == {}
