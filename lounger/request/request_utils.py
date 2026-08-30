"""
lounger request
"""
import json
import os
import time
from collections.abc import Mapping
from functools import wraps
from typing import Any

import requests
from pytest_req.utils.jmespath import jmespath

from lounger.commons.assert_result import _get_actual_value
from lounger.log import log
from lounger.request.request_client import request_client


class HttpRequest:
    """lounger http request class"""

    def __init__(self, base_url: str | None = None, *args, **kwargs):
        self.base_url = base_url
        self.args = args
        self.kwargs = kwargs
        # 统一走 RequestClient（3.5：请求层双轨合并，base_url/headers/日志统一）
        self._client = request_client

    def _dispatch(self, method: str, url: str, **kwargs):
        """
        Send the request through the shared :class:`RequestClient`.

        The instance ``base_url`` is joined here (same semantics as before);
        the client's session uses the configured base_url for any remaining
        relative URL, and headers/logging are unified on this path.
        """
        if self.base_url is not None and not str(url).startswith(("http://", "https://")):
            url = self.base_url + url
        return self._client.send_request(method=method, url=url, **kwargs)

    def get(self, url, params=None, **kwargs):
        return self._dispatch("GET", url, params=params, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        return self._dispatch("POST", url, data=data, json=json, **kwargs)

    def put(self, url, data=None, **kwargs):
        return self._dispatch("PUT", url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        return self._dispatch("DELETE", url, **kwargs)

    def patch(self, url, data=None, **kwargs):
        return self._dispatch("PATCH", url, data=data, **kwargs)


def api(
    describe: str = "",
    status_code: int | None = None,
    ret: str | None = None,
    check: dict | None = None,
    debug: bool = False,
):
    """
    Check API response data.

    Assertions/extraction are delegated to ``lounger.commons.assert_result``,
    so the expressions support the same syntax as YAML cases: ``status_code``,
    ``headers.<key>``, ``body.<jmespath>`` or a bare JMESPath expression.

    :param describe: interface describe
    :param status_code: http status code
    :param ret: return data (JMESPath expression)
    :param check: check data, e.g. ``{"body.code": 0}``
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
                    try:
                        actual = _get_actual_value(r, expr)
                    except (ValueError, json.JSONDecodeError):
                        # Non-JSON response: fall back to the parsed body (may be {})
                        actual = jmespath(response_data, expr)
                    if actual != value:
                        log.error(f"Execute {func_name} - check data failed：{expr} = {value}")
                        log.error(f"Execute {func_name} - response：{response_data}")
                        raise ValueError(f"{actual} != {value}")

            if ret:
                try:
                    data = _get_actual_value(r, ret)
                except (ValueError, json.JSONDecodeError):
                    data = jmespath(response_data, ret)
                if debug is True:
                    log.debug(f"Execute {func_name} - extract: {ret} - {data}")
                return data

            return response_data

        return wrapper

    return decorator


def save_response(response: requests.Response | Mapping | list, filename: str | None = None):
    """
    Save response content to a local file.
    :param response:
    :param filename:
    :return:
    """
    data: Any = response
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
