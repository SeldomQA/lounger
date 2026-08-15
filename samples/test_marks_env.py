"""
功能：在运行测试的时候通过 --env {name} 筛选运行的用例
使用：
> pytest -vs --env dev test_marks_env.py   # 运行 test_three()
> pytest -vs --env test test_marks_env.py  # 运行 test_one()/test_two()
"""
import pytest


@pytest.mark.env("test")
def test_one():
    assert True


@pytest.mark.env("test")
def test_two():
    assert True


@pytest.mark.env("dev")
def test_three():
    assert True
