from datetime import timedelta

import pytest

from lounger.commons.assert_result import api_validate


class DummyResponse:
    def __init__(self, data, status_code=200, headers=None, text=""):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.url = "https://example.com/api"
        self.reason = "OK"
        self.encoding = "utf-8"
        self.content = text.encode("utf-8")
        self.ok = True
        self.elapsed = timedelta(milliseconds=120)
        self.history = []
        self.cookies = {"sid": "abc123"}
        self.request = type(
            "DummyRequest",
            (),
            {
                "method": "POST",
                "url": "https://example.com/api",
                "body": b'{"x":1}',
                "headers": {"X-Req": "req-v"},
            },
        )()

    def json(self):
        return self._data


def test_validate_body_and_json_prefix():
    resp = DummyResponse({"code": 200, "data": {"name": "tom"}})
    api_validate(
        resp,
        {
            "equal": [
                ["body.code", 200],
                ["body.data.name", "tom"],
                ["json.code", 200],
            ]
        },
    )


def test_validate_response_and_request_fields():
    resp = DummyResponse(
        {"code": 200},
        headers={"X-Trace-Id": "trace-1"},
        text='{"code": 200}',
    )
    api_validate(
        resp,
        {
            "equal": [
                ["status_code", 200],
                ["url", "https://example.com/api"],
                ["reason", "OK"],
                ["encoding", "utf-8"],
                ["text", '{"code": 200}'],
                ["content", b'{"code": 200}'],
                ["ok", True],
                ["headers.X-Trace-Id", "trace-1"],
                ["cookies.sid", "abc123"],
                ["request.method", "POST"],
                ["request.url", "https://example.com/api"],
                ["request.body", b'{"x":1}'],
                ["request.headers.X-Req", "req-v"],
            ]
        },
    )


def test_validate_elapsed_expression():
    resp = DummyResponse({"code": 200})
    api_validate(
        resp,
        {
            "greater": [["elapsed.total_seconds", 0.0]],
            "is_not_null": [["elapsed", None]],
        },
    )


def test_validate_non_prefixed_expression_treated_as_jmespath():
    resp = DummyResponse({"code": 200, "data": {"name": "tom"}})
    api_validate(
        resp,
        {
            "equal": [
                ["code", 200],
                ["data.name", "tom"],
            ]
        },
    )


def test_validate_non_prefixed_expression_extracts_from_body():
    from lounger.commons.assert_result import _get_actual_value

    resp = DummyResponse({"userId": 1, "items": ["a", "b"]})
    # bare expression == jmespath against the body (previously returned the literal string)
    assert _get_actual_value(resp, "userId") == 1
    assert _get_actual_value(resp, "items[0]") == "a"
    assert _get_actual_value(resp, "items") == ["a", "b"]


def test_validate_non_prefixed_expression_mismatch_raises():
    resp = DummyResponse({"code": 200})
    with pytest.raises(AssertionError):
        api_validate(resp, {"equal": [["code", "code"]]})


def test_validate_non_string_expression_passed_through():
    from lounger.commons.assert_result import _get_actual_value

    resp = DummyResponse({"code": 200})
    assert _get_actual_value(resp, 123) == 123
    assert _get_actual_value(resp, None) is None
