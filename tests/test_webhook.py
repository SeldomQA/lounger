"""
Tests for DingTalk webhook payload builders.
"""
from lounger.utils.webhook import _markdown_payload, _text_payload


def test_text_payload_structure():
    payload = _text_payload("hello")

    assert payload == {"msgtype": "text", "text": {"content": "hello"}}


def test_markdown_payload_structure():
    payload = _markdown_payload("title", "body")

    assert payload == {
        "msgtype": "markdown",
        "markdown": {"title": "title", "text": "body"},
    }


def test_payloads_are_json_serializable():
    import json

    json.dumps(_text_payload("x"))
    json.dumps(_markdown_payload("t", "b"))
