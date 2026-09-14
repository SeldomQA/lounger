"""
Tests for ``lounger.commons.assert_result`` (YAML ``validate`` expressions).

CI-covered home for the assertion-expression contract:

- ``body.<jmespath>`` / ``json.<jmespath>`` prefixes;
- **bare (non-prefixed) expressions are JMESPath against the JSON body**
  (regression guard: they used to be returned as literal strings);
- response / request field shortcuts (``status_code`` / ``headers.*`` /
  ``cookies.*`` / ``request.*`` / ``elapsed*``);
- non-string expressions pass through unchanged;
- the assertion-type map (``equal`` / ``contains`` / ``greater`` / ``length`` ...).
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from lounger.commons.assert_result import _get_actual_value, api_validate


def _fake_response(payload, status_code=200, headers=None, text='{"code": 200}'):
    """Minimal stand-in for ``requests.Response`` (only what assert_result reads)."""
    return SimpleNamespace(
        status_code=status_code,
        headers=headers if headers is not None else {},
        text=text,
        content=text.encode("utf-8"),
        url="https://example.com/api",
        reason="OK",
        encoding="utf-8",
        ok=True,
        elapsed=timedelta(milliseconds=120),
        cookies={"sid": "abc123"},
        request=SimpleNamespace(
            method="POST",
            url="https://example.com/api",
            body=b'{"x":1}',
            headers={"X-Req": "req-v"},
        ),
        json=lambda: payload,
    )


# ── bare (non-prefixed) expressions are JMESPath against the body ─────────

def test_bare_expression_is_jmespath_against_body():
    resp = _fake_response({"code": 200, "data": {"name": "tom"}})

    api_validate(resp, {"equal": [["code", 200], ["data.name", "tom"]]})


def test_bare_expression_extracts_from_body():
    resp = _fake_response({"userId": 1, "items": ["a", "b"]})

    assert _get_actual_value(resp, "userId") == 1
    assert _get_actual_value(resp, "items[0]") == "a"
    assert _get_actual_value(resp, "items") == ["a", "b"]


def test_bare_expression_mismatch_raises():
    resp = _fake_response({"code": 200})

    # bare "code" means body.code (200), not the literal string "code"
    with pytest.raises(AssertionError):
        api_validate(resp, {"equal": [["code", "code"]]})


def test_non_string_expression_passed_through():
    resp = _fake_response({"code": 200})

    assert _get_actual_value(resp, 123) == 123
    assert _get_actual_value(resp, None) is None


# ── prefixed expressions & response/request shortcuts ─────────────────────

def test_body_and_json_prefixes():
    resp = _fake_response({"code": 200, "data": {"name": "tom"}})

    api_validate(
        resp,
        {"equal": [["body.code", 200], ["body.data.name", "tom"], ["json.code", 200]]},
    )


def test_response_and_request_field_shortcuts():
    resp = _fake_response({"code": 200}, headers={"X-Trace-Id": "trace-1"})

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


def test_elapsed_expressions():
    resp = _fake_response({"code": 200})

    api_validate(
        resp,
        {
            "greater": [["elapsed.total_seconds", 0.0]],
            "is_not_null": [["elapsed", None]],
        },
    )


# ── assertion types ──────────────────────────────────────────────────────

def test_assertion_types():
    resp = _fake_response({"code": 200, "message": "success", "items": [1, 2, 3]})

    api_validate(
        resp,
        {
            "equal": [["body.code", 200]],
            "not_equal": [["body.code", 500]],
            "contains": [["body.message", "succ"]],
            "not_contains": [["body.message", "denied"]],
            "type": [["body.items", []]],
            "length": [["body.items", 3]],
            "greater": [["body.code", 199]],
            "greater_equal": [["body.code", 200]],
            "less": [["body.code", 201]],
            "less_equal": [["body.code", 200]],
            "is_null": [["body.missing", None]],
            "is_not_null": [["body.code", None]],
        },
    )


def test_unsupported_assertion_type_is_skipped():
    """Unknown assertion types are ignored (warning) instead of failing the case."""
    resp = _fake_response({"code": 200})

    api_validate(resp, {"not_an_assertion": [["body.code", "ignored"]]})


def test_malformed_assertion_item_is_skipped():
    """Items that are not [expr, expected] pairs are ignored."""
    resp = _fake_response({"code": 200})

    api_validate(resp, {"equal": [["only-one-element"]]})
