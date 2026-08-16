"""
Consistency tests for the request-layer merge (docs/development_plan.md §3.5).

Covers:

- ``HttpRequest`` now delegates to :class:`RequestClient` (single main path):
  same method / url / params for both call styles;
- ``@api`` assertion/extraction reuses ``assert_result`` expressions
  (``status_code`` / ``body.<jmespath>`` / bare JMESPath);
- legacy API surface (``HttpRequest``, ``@api``, ``expect``) keeps working.
"""
from types import SimpleNamespace

import pytest

from lounger.commons.assert_result import _get_actual_value
from lounger.request import HttpRequest, api, expect


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """The pytest_req @request decorator resolves the host — stub DNS."""
    monkeypatch.setattr("pytest_req.plugin.socket.gethostbyname", lambda domain: "127.0.0.1")


def _fake_response(payload: dict, status_code: int = 200):
    """Build a requests.Response-like object sufficient for the request paths."""
    return SimpleNamespace(
        status_code=status_code,
        json=lambda: payload,
        text="{}",
        content=b"{}",
        headers={},
        elapsed=SimpleNamespace(total_seconds=lambda: 0.01),
        request=SimpleNamespace(method="GET", url="http://x", headers={}),
        url="http://x",
        reason="OK",
        ok=True,
        encoding="utf-8",
    )


class _RecordingClient:
    """RequestClient stand-in that records the outgoing request kwargs."""

    def __init__(self):
        self.calls = []

    def send_request(self, **kwargs):
        self.calls.append(kwargs)
        return _fake_response({"ok": True})


def _patch_http_client(monkeypatch, client):
    """Point HttpRequest._client at the recording client."""
    monkeypatch.setattr("lounger.request.request_utils.request_client", client)


# ── HttpRequest delegates to RequestClient ────────────────────────────────

def test_http_request_get_delegates_to_request_client(monkeypatch):
    recording = _RecordingClient()
    _patch_http_client(monkeypatch, recording)

    HttpRequest(base_url="https://api.example.com").get("/users", params={"page": 1})

    assert len(recording.calls) == 1
    call = recording.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://api.example.com/users"
    assert call["params"] == {"page": 1}


def test_http_request_all_methods_delegate(monkeypatch):
    recording = _RecordingClient()
    _patch_http_client(monkeypatch, recording)

    client = HttpRequest(base_url="https://api.example.com")
    client.post("/users", json={"name": "tom"}, headers={"X-Token": "t"})
    client.put("/users/1", data={"name": "tom"})
    client.delete("/users/1")
    client.patch("/users/1", data={"name": "tom"})

    methods = [c["method"] for c in recording.calls]
    assert methods == ["POST", "PUT", "DELETE", "PATCH"]
    assert all(c["url"].startswith("https://api.example.com") for c in recording.calls)


def test_http_request_without_base_url_keeps_url(monkeypatch):
    recording = _RecordingClient()
    _patch_http_client(monkeypatch, recording)

    HttpRequest().get("https://absolute.example.com/users")

    assert recording.calls[0]["url"] == "https://absolute.example.com/users"


# ── same request, two styles: identical outgoing request ──────────────────

def test_same_request_two_styles_produce_identical_call(monkeypatch):
    recording = _RecordingClient()
    _patch_http_client(monkeypatch, recording)

    payload = {"name": "tom"}
    headers = {"X-Token": "t"}

    # Style A: RequestClient.send_request directly (YAML-engine path)
    recording.send_request(
        method="POST", url="https://api.example.com/users", json=payload, headers=headers,
    )
    # Style B: HttpRequest wrapper (code-style API object) — same request
    HttpRequest(base_url="https://api.example.com").post(
        "/users", json=payload, headers=headers,
    )

    assert len(recording.calls) == 2
    a, b = recording.calls
    assert a["method"] == b["method"] == "POST"
    assert a["url"] == b["url"] == "https://api.example.com/users"
    assert a["json"] == b["json"] == payload
    assert a["headers"] == b["headers"] == headers


# ── @api reuses assert_result expressions ─────────────────────────────────

def test_api_decorator_check_uses_assert_result_expressions(monkeypatch):
    """check accepts body.<jmespath> / bare JMESPath / status_code expressions."""
    called = {"value": None}

    class Demo(HttpRequest):
        @api(describe="demo", check={"body.code": 0, "status_code": 200})
        def demo(self):
            called["value"] = self.get("/demo")
            return called["value"]

    _patch_http_client(
        monkeypatch,
        SimpleNamespace(send_request=lambda **kw: _fake_response({"code": 0, "data": {"name": "tom"}})),
    )

    demo = Demo(base_url="https://api.example.com")
    result = demo.demo()
    assert result == {"code": 0, "data": {"name": "tom"}}
    assert called["value"].status_code == 200


def test_api_decorator_check_failure_raises_value_error(monkeypatch):
    class Demo(HttpRequest):
        @api(describe="demo", check={"body.code": 1})
        def demo(self):
            return self.get("/demo")

    _patch_http_client(
        monkeypatch,
        SimpleNamespace(send_request=lambda **kw: _fake_response({"code": 0})),
    )

    demo = Demo(base_url="https://api.example.com")
    with pytest.raises(ValueError, match="0 != 1"):
        demo.demo()


def test_api_decorator_status_code_failure_raises_assertion_error(monkeypatch):
    class Demo(HttpRequest):
        @api(describe="demo", status_code=201)
        def demo(self):
            return self.get("/demo")

    _patch_http_client(
        monkeypatch,
        SimpleNamespace(send_request=lambda **kw: _fake_response({}, status_code=200)),
    )

    demo = Demo(base_url="https://api.example.com")
    with pytest.raises(AssertionError, match="200 != 201"):
        demo.demo()


def test_api_decorator_ret_extracts_with_assert_result_expression(monkeypatch):
    """ret supports body.<jmespath> / bare JMESPath via assert_result."""
    class Demo(HttpRequest):
        @api(describe="demo", ret="body.data.name")
        def demo(self):
            return self.get("/demo")

    _patch_http_client(
        monkeypatch,
        SimpleNamespace(send_request=lambda **kw: _fake_response({"data": {"name": "tom"}})),
    )

    demo = Demo(base_url="https://api.example.com")
    assert demo.demo() == "tom"


def test_api_decorator_ret_bare_jmespath_still_works(monkeypatch):
    """Backward compat: bare JMESPath (no body. prefix) keeps working."""
    class Demo(HttpRequest):
        @api(describe="demo", ret="data.name")
        def demo(self):
            return self.get("/demo")

    _patch_http_client(
        monkeypatch,
        SimpleNamespace(send_request=lambda **kw: _fake_response({"data": {"name": "tom"}})),
    )

    demo = Demo(base_url="https://api.example.com")
    assert demo.demo() == "tom"


# ── assert_result expression helper is shared ─────────────────────────────

def test_get_actual_value_supports_shared_expressions():
    resp = _fake_response({"data": {"name": "tom"}}, status_code=200)

    assert _get_actual_value(resp, "status_code") == 200
    assert _get_actual_value(resp, "body.data.name") == "tom"
    assert _get_actual_value(resp, "data.name") == "tom"  # bare JMESPath


# ── expect entrypoint unchanged ───────────────────────────────────────────

def test_expect_entrypoint_still_works():
    expect({"code": 0}).to_have_path_value("code", 0)
    expect({"data": [1, 2]}).to_have_path_length("data", 2)
