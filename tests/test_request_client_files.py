"""
Tests for file upload handling in RequestClient:

- ``_files_load`` opens one handle per file and returns them so callers can close them.
- ``send_request`` always closes the opened handles (success, request failure,
  unsupported method, and partial-load failure).
"""
import pytest

from lounger.request.request_client import RequestClient


class DummySession:
    """Records every call; never performs real I/O."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def handler(url, **kwargs):
            self.calls.append((name, url, kwargs))
            return "response"

        return handler


def _make_client() -> RequestClient:
    """Build a RequestClient without touching the real pytest_req Session."""
    return RequestClient.__new__(RequestClient)


def _patch_session(monkeypatch, session) -> None:
    """
    Make ``send_request`` use the given fake session.

    ``send_request`` now resolves its session lazily via ``_get_session()``
    (so config changes are picked up); tests bypass that by patching the
    session getter directly.
    """
    monkeypatch.setattr(RequestClient, "_get_session", lambda self: session)


def test_files_load_returns_open_handles(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    f2 = tmp_path / "b.txt"
    f2.write_text("world")

    files, handles = RequestClient._files_load({"file1": str(f1), "file2": str(f2)})

    assert set(files) == {"file1", "file2"}
    assert len(handles) == 2
    # handles are open and readable
    assert all(not h.closed for h in handles)
    assert files["file1"].read() == b"hello"

    for h in handles:
        h.close()


def test_files_load_closes_partial_handles_on_failure(tmp_path, monkeypatch):
    existing = tmp_path / "a.txt"
    existing.write_text("hello")

    real_open = open
    opened = []

    def tracking_open(path, mode="r", *args, **kwargs):
        handle = real_open(path, mode, *args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr("builtins.open", tracking_open)

    with pytest.raises(FileNotFoundError):
        RequestClient._files_load(
            {"file1": str(existing), "file2": str(tmp_path / "missing.txt")}
        )

    # the handle opened before the failure must already be closed
    assert len(opened) == 1
    assert opened[0].closed


def test_send_request_closes_files_after_request(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("hello")

    session = DummySession()
    _patch_session(monkeypatch, session)

    client = _make_client()
    resp = client.send_request(
        method="POST", url="/upload", files={"file": str(f)}
    )

    assert resp == "response"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "/upload"
    # the handle handed to the session must be closed after the request
    assert kwargs["files"]["file"].closed


def test_send_request_closes_files_when_request_fails(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    handle = open(str(f), "rb")

    def fake_files_load(files_dict):
        return {"file": handle}, [handle]

    monkeypatch.setattr(RequestClient, "_files_load", staticmethod(fake_files_load))

    class BoomSession(DummySession):
        def post(self, url, **kwargs):
            raise ConnectionError("boom")

    _patch_session(monkeypatch, BoomSession())
    client = _make_client()

    with pytest.raises(ConnectionError):
        client.send_request(method="POST", url="/upload", files={"file": str(f)})

    assert handle.closed


def test_send_request_closes_files_on_unsupported_method(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    handle = open(str(f), "rb")

    def fake_files_load(files_dict):
        return {"file": handle}, [handle]

    monkeypatch.setattr(RequestClient, "_files_load", staticmethod(fake_files_load))

    _patch_session(monkeypatch, DummySession())
    client = _make_client()

    with pytest.raises(NotImplementedError):
        client.send_request(method="TRACE", url="/x", files={"file": str(f)})

    assert handle.closed


def test_send_request_without_files_still_works(monkeypatch):
    session = DummySession()
    _patch_session(monkeypatch, session)

    client = _make_client()
    resp = client.send_request(method="GET", url="/ping")

    assert resp == "response"
    method, url, kwargs = session.calls[0]
    assert method == "get"
    assert url == "/ping"
    assert "files" not in kwargs
