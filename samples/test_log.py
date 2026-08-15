import logging

from loguru import logger


def test_sys_log():
    """sys logging log"""
    logging.debug("This is a debug message")
    logging.info("This is an info message")
    logging.warning("This is a warning message")
    logging.error("This is a error message")


def test_loguru_log():
    """loguru log"""
    logger.info("loguru 日志")
    logger.info("loguru 错误")


def test_requests_log(get):
    """
    get request log (loguru)
    """
    payload = {'key1': 'value1', 'key2': 'value2'}
    s = get(f"https://httpbin.org/get", params=payload)
    assert s.status_code == 200
