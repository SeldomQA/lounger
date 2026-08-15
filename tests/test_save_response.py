import json

import pytest
import requests

from lounger.request import save_response


def test_save_response_supports_json_dict(tmp_path):
    payload = {
        "code": 0,
        "data": {
            "carriers": ["q4848", "ups"],
        },
    }

    saved_path = save_response(payload, str(tmp_path / "result.txt"))

    assert saved_path.endswith("result.json")
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8")) == payload


def test_save_response_supports_json_list_without_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = [{"id": 1}, {"id": 2}]

    saved_path = save_response(payload)

    assert saved_path.endswith(".json")
    assert json.loads((tmp_path / saved_path).read_text(encoding="utf-8")) == payload


def test_save_response_keeps_response_compatibility(tmp_path):
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Type"] = "application/json"
    response._content = b'{"code": 0, "message": "ok"}'
    response.encoding = "utf-8"

    saved_path = save_response(response, str(tmp_path / "response.txt"))

    assert saved_path.endswith("response.json")
    assert json.loads((tmp_path / "response.json").read_text(encoding="utf-8")) == {"code": 0, "message": "ok"}


def test_save_response_rejects_unsupported_data_type(tmp_path):
    with pytest.raises(TypeError, match="requests.Response or JSON-compatible dict/list data"):
        save_response("plain text", str(tmp_path / "response.txt"))
