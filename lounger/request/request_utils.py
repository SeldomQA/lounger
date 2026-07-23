"""
lounger request
"""
import json
import os
import time
from collections.abc import Mapping
from functools import wraps

import requests
from pytest_req.plugin import request
from pytest_req.utils.jmespath import jmespath

from lounger.log import log


class HttpRequest:
    """lounger http request class"""

    def __init__(self, base_url: str = None, *args, **kwargs):
        self.base_url = base_url
        self.args = args
        self.kwargs = kwargs

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


def api(describe: str = "", status_code: int = None, ret: str = None, check: dict = None, debug: bool = False):
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
            log.info(f"Execute HTTP API: {func_name} - {describe}")
            if debug is True:
                log.debug(f"Params: args={args}, kwargs={kwargs}")

            r = func(*args, **kwargs)

            if status_code is not None:
                if r.status_code != status_code:
                    log.error(f"Execute {func_name} - {describe} failed: {r.status_code}")
                    raise AssertionError(f"{r.status_code} != {status_code}")

            try:
                response_data = r.json()
            except json.decoder.JSONDecodeError:
                log.error(f"Execute {func_name} - {describe} failed：Not in JSON format")
                response_data = {}

            if debug is True:
                log.debug(f"Execute {func_name} - response:\n {response_data}")

            if check:
                for expr, value in check.items():
                    data = jmespath(response_data, expr)
                    if data != value:
                        log.error(f"Execute {func_name} - check data failed：{expr} = {value}")
                        log.error(f"Execute {func_name} - response：{r.json()}")
                        raise ValueError(f"{data} != {value}")

            if ret:
                data = jmespath(response_data, ret)
                if debug is True:
                    log.debug(f"Execute {func_name} - extract: {ret} - {data}")
                return data

            return response_data

        return wrapper

    return decorator


def save_response(response: requests.Response | Mapping | list, filename: str = None):
    """
    Save response content to a local file.
    :param response:
    :param filename:
    :return:
    """
    data = response
    ext = ".json"

    if isinstance(response, requests.Response):
        content_type = response.headers.get("Content-Type", "").lower()
        data = response.text
        ext = ".txt"

        if "application/json" in content_type or response.text.strip().startswith(("{", "[")):
            try:
                data = response.json()
                ext = ".json"
            except (requests.exceptions.JSONDecodeError, ValueError):
                pass
    elif not isinstance(response, (Mapping, list)):
        raise TypeError("save_response() only supports requests.Response or JSON-compatible dict/list data")

    if filename is None:
        timestamp = int(time.time() * 1000)
        filename = f"response_{timestamp}{ext}"
    else:
        root, _ = os.path.splitext(filename)
        filename = f"{root}{ext}"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4) if ext == ".json" else f.write(data)

    log.info(f"Saved response to {filename}")
    return filename
