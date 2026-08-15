from typing import Any, Dict, Optional

import requests
from pytest_req.utils import jmespath

from lounger.log import log

# Assertion types
ASSERT_TYPES: dict = {
    # assertion_type: expects (actual, expected) -> bool
    "equal": lambda actual, expected: actual == expected,  # Assert equality
    "not_equal": lambda actual, expected: actual != expected,  # Assert inequality
    "contains": lambda actual, expected: expected in actual,  # Assert that actual contains expected
    "not_contains": lambda actual, expected: expected not in actual,  # Assert that actual does not contain expected
    "type": lambda actual, expected: type(actual) is type(expected),  # Assert data type match
    "length": lambda actual, expected: len(actual) == int(expected),  # Assert length match
    "greater": lambda actual, expected: actual > expected,  # Assert greater than
    "greater_equal": lambda actual, expected: actual >= expected,  # Assert greater than or equal to
    "less": lambda actual, expected: actual < expected,  # Assert less than
    "less_equal": lambda actual, expected: actual <= expected,  # Assert less than or equal to
    "is_null": lambda actual, expected: actual is None,
    "is_not_null": lambda actual, expected: actual is not None
}


def _get_actual_value(resp: requests.Response, expr: str):
    """
    Extract the actual value from the API response based on the given expression.

    Supported expression formats:
    - "status_code": returns the HTTP status code (e.g., 200)
    - "headers.<key>": returns the value of the specified response header (e.g., "headers.Content-Type")
    - "body.<jmespath>": treats <jmespath> as a JMESPath expression applied to the JSON response body
    - Any other expression: treated as a JMESPath expression applied directly to the JSON response body
      (equivalent to prepending "body.")

    :param resp: Response object from the API request
    :param expr: Expression string to extract value, e.g.,
                "status_code",
                "headers.Content-Type",
                "body.code", or "data.name"
    """
    if isinstance(expr, str):
        if expr == "status_code":
            return resp.status_code
        elif expr == "url":
            return resp.url
        elif expr == "reason":
            return resp.reason
        elif expr == "encoding":
            return resp.encoding
        elif expr == "text":
            return resp.text
        elif expr == "content":
            return resp.content
        elif expr == "ok":
            return resp.ok
        elif expr == "elapsed":
            return resp.elapsed
        elif expr == "elapsed.total_seconds":
            return resp.elapsed.total_seconds()
        elif expr.startswith("headers."):
            header_key = expr[8:]
            return resp.headers.get(header_key)
        elif expr.startswith("cookies."):
            cookie_key = expr[8:]
            return resp.cookies.get(cookie_key)
        elif expr.startswith("request."):
            req = resp.request
            if req is None:
                return None
            request_expr = expr[8:]
            if request_expr == "method":
                return req.method
            elif request_expr == "url":
                return req.url
            elif request_expr == "body":
                return req.body
            elif request_expr.startswith("headers."):
                header_key = request_expr[8:]
                return req.headers.get(header_key)
            return expr
        elif expr.startswith("body."):
            jmes_expr = expr[5:]
            json_data = resp.json()
            return jmespath.jmespath(json_data, jmes_expr)
        elif expr.startswith("json."):
            jmes_expr = expr[5:]
            json_data = resp.json()
            return jmespath.jmespath(json_data, jmes_expr)
        else:
            # Any other expression is treated as a JMESPath expression applied
            # directly to the JSON response body (equivalent to the "body." prefix).
            json_data = resp.json()
            return jmespath.jmespath(json_data, expr)
    else:
        return expr


def api_validate(resp: requests.Response, validate_value: Optional[Dict[str, Any]]) -> None:
    """
    Validate API response against the specified assertion rules

    :param resp: Response object from API request
    :param validate_value: Dictionary containing assertion rules, e.g.:
        {
            "equal": [["status_code", 200], ["body.code", 10200]],
            "not_equal": [["body.data.name", "jack"]],
            "contains": [["body.message", "succ"]],
            "not_contains": [["body.message", "access"]]
        }
    """

    if not validate_value:
        return

    for assert_type, assertions in validate_value.items():
        if assert_type not in ASSERT_TYPES:
            log.warning(f"Unsupported assertion type: {assert_type}")
            continue

        if not isinstance(assertions, list):
            continue

        for item in assertions:
            if not isinstance(item, list) or len(item) != 2:
                continue

            expr, expected = item
            actual = _get_actual_value(resp, expr)
            assert_func = ASSERT_TYPES[assert_type]
            result = assert_func(actual, expected)

            # Map assertion types to their respective operators for clearer logging
            operator_map = {
                "equal": "==",
                "not_equal": "!=",
                "contains": "contains",
                "not_contains": "not contains",
                "greater": ">",
                "greater_equal": ">=",
                "less": "<",
                "less_equal": "<="
            }

            if result:
                if assert_type == "length":
                    log.info(
                        f"✅ assertion {assert_type} passed: [{expr}] {len(actual)} == {expected}")
                else:
                    operator = operator_map.get(assert_type, assert_type)
                    log.info(f"✅ assertion {assert_type} passed: [{expr}] {actual} {operator} {expected}")
            else:
                operator = operator_map.get(assert_type, assert_type)
                if assert_type == "length":
                    error_msg = f"❌ assertion {assert_type} failed: [{expr}] {len(actual)} != {expected}"
                else:
                    error_msg = f"❌ assertion {assert_type} failed: [{expr}] {actual} {operator} {expected}"
                log.error(error_msg)
                raise AssertionError(error_msg)
