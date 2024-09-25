"""
lounger request
"""
import json
from functools import wraps

import requests
from pytest_req.plugin import request
from pytest_req.utils.jmespath import jmespath

from lounger.log import log


class HttpRequest:
    """lounger http request class"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url

    @request
    def get(self, url, params=None, **kwargs):
        if self.base_url is not None:
            url = self.base_url + url
        return requests.get(url, params=params, **kwargs)

    @request
    def post(self, url, data=None, json=None, **kwargs):
        if self.base_url is not None:
            url = self.base_url + url
        return requests.post(url, data=data, json=json, **kwargs)

    @request
    def put(self, url, data=None, **kwargs):
        if self.base_url is not None:
            url = self.base_url + url
        return requests.put(url, data=data, **kwargs)

    @request
    def delete(self, url, **kwargs):
        if self.base_url is not None:
            url = self.base_url + url
        return requests.delete(url, **kwargs)

    @request
    def patch(self, url, data=None, **kwargs):
        if self.base_url is not None:
            url = self.base_url + url
        return requests.patch(url, data=data, **kwargs)


def api(describe: str = "", status_code: int = 200, ret: str = None, check: dict = None, debug: bool = False):
    """
    checkout api response data
    :param describe: interface describe
    :param status_code: http status code
    :param ret: return data
    :param check: check data
    :param debug: debug Ture/False
    :return:
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            if debug is True:
                log.debug(f"Execute {func_name} - args: {args}")
                log.debug(f"Execute {func_name} - kwargs: {kwargs}")

            r = func(*args, **kwargs)
            flat = True
            if r.status_code != status_code:
                log.error(f"Execute {func_name} - {describe} failed: {r.status_code}")
                flat = False

            try:
                r.json()
            except json.decoder.JSONDecodeError:
                log.error(f"Execute {func_name} - {describe} failed：Not in JSON format")
                flat = False

            if debug is True:
                log.debug(f"Execute {func_name} - response:\n {r.json()}")

            if flat is True:
                log.info(f"Execute {func_name} - {describe} success!")

            if check is not None:
                for expr, value in check.items():
                    data = jmespath(r.json(), expr)
                    if data != value:
                        log.error(f"Execute {func_name} - check data failed：{expr} = {value}")
                        log.error(f"Execute {func_name} - response：{r.json()}")
                        raise ValueError(f"{data} != {value}")

            if ret is not None:
                data = jmespath(r.json(), ret)
                if data is None:
                    log.error(f"Execute {func_name} - return {ret} is None")
                return data

            return r.json()

        return wrapper

    return decorator
