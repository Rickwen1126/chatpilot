"""Tests for multi-line adapter behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import Request

from chatpilot.adapters.line import adapter as line_adapter_module
from chatpilot.adapters.line.adapter import LineAdapter
from chatpilot.adapters.line.parser import parse_line_events


def _request(body: bytes = b"{}", headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (k.lower().encode("utf-8"), v.encode("utf-8"))
        for k, v in (headers or {}).items()
    ]

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhook/line",
        "headers": raw_headers,
    }
    return Request(scope, receive)


@pytest.mark.asyncio
async def test_line_adapter_named_channel_passes_platform_to_parser(monkeypatch):
    captured: dict[str, object] = {}

    class FakeParser:
        def parse(self, body: str, signature: str):
            captured["body"] = body
            captured["signature"] = signature
            return ["event-1"]

    def fake_parse_line_events(events, platform):
        captured["events"] = events
        captured["platform"] = platform
        return []

    monkeypatch.setattr(line_adapter_module, "parse_line_events", fake_parse_line_events)

    adapter = LineAdapter(name="webric", secret="secret", token="")
    adapter._parser = FakeParser()

    await adapter.parse_messages(
        _request(body=b'{"events":[]}', headers={"X-Line-Signature": "sig-1"})
    )

    assert adapter.platform == "line:webric"
    assert captured["platform"] == "line:webric"
    assert captured["events"] == ["event-1"]


@pytest.mark.asyncio
async def test_legacy_line_adapter_logs_error_on_parse(monkeypatch, caplog):
    class FakeParser:
        def parse(self, body: str, signature: str):
            return []

    monkeypatch.setattr(line_adapter_module, "parse_line_events", lambda events, platform: [])

    adapter = LineAdapter(secret="secret", token="")
    adapter._parser = FakeParser()

    with caplog.at_level("ERROR"):
        await adapter.parse_messages(
            _request(body=b'{"events":[]}', headers={"X-Line-Signature": "sig-1"})
        )

    assert "Legacy unnamed LINE adapter path used" in caplog.text


def test_parse_line_events_uses_named_platform_for_text_and_media_refs(monkeypatch):
    class FakeMessageEvent:
        def __init__(self, source, message, reply_token="reply-1", timestamp=1000):
            self.source = source
            self.message = message
            self.reply_token = reply_token
            self.timestamp = timestamp

    class FakeTextMessageContent:
        def __init__(self, text: str, id: str):
            self.text = text
            self.id = id
            self.mention = None

    class FakeImageMessageContent:
        def __init__(self, id: str):
            self.id = id

    monkeypatch.setattr("chatpilot.adapters.line.parser.MessageEvent", FakeMessageEvent)
    monkeypatch.setattr(
        "chatpilot.adapters.line.parser.TextMessageContent", FakeTextMessageContent
    )
    monkeypatch.setattr(
        "chatpilot.adapters.line.parser.ImageMessageContent", FakeImageMessageContent
    )

    source = SimpleNamespace(user_id="U123", group_id="C456")
    events = [
        FakeMessageEvent(source=source, message=FakeTextMessageContent("hi", "m1")),
        FakeMessageEvent(source=source, message=FakeImageMessageContent("img1")),
    ]

    messages = parse_line_events(events, platform="line:webric")

    assert [m.platform for m in messages] == ["line:webric", "line:webric"]
    assert messages[1].text == "[圖片 ref:line:webric:img1]"
