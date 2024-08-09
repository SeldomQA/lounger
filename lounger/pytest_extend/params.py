import pytest


def data(data, ids: list = None, scope=None):
    """
    lounger parametrize decorator
    :param data:
    :param ids:
    :param scope:
    :return:
    """
    if ids is None:
        ids = []

    if scope is None:
        scope = "function"

    return pytest.mark.parametrize(
        "params",
        data,
        ids=ids,
        scope=scope)
