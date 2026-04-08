"""Unit tests for SttTranscriber."""

import asyncio
import json
from unittest.mock import MagicMock, patch

from chatpilot.stt.transcriber import SttTranscriber


def test_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    t = SttTranscriber(api_key="")
    assert not t.enabled
    result = asyncio.run(t.transcribe(b"fake"))
    assert result is None


def test_enabled_with_api_key():
    t = SttTranscriber(api_key="sk-test")
    assert t.enabled


def test_transcribe_success():
    t = SttTranscriber(api_key="sk-test")
    fake_response = json.dumps({"text": "你好世界"}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = asyncio.run(
            t.transcribe(b"fake-audio-bytes", language="zh")
        )
        assert result == "你好世界"
        # Verify API was called
        call_args = mock_open.call_args
        req = call_args[0][0]
        assert "audio/transcriptions" in req.full_url
        assert "Bearer sk-test" in req.get_header("Authorization")


def test_transcribe_empty_result():
    t = SttTranscriber(api_key="sk-test")
    fake_response = json.dumps({"text": ""}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = asyncio.run(
            t.transcribe(b"silence")
        )
        assert result is None


def test_transcribe_api_error():
    t = SttTranscriber(api_key="sk-test")

    with patch("urllib.request.urlopen", side_effect=Exception("API down")):
        result = asyncio.run(
            t.transcribe(b"audio")
        )
        assert result is None  # Graceful failure


def test_model_passed_to_api():
    t = SttTranscriber(api_key="sk-test", model="whisper-1")
    fake_response = json.dumps({"text": "test"}).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = fake_response
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        asyncio.run(t.transcribe(b"audio"))
        req = mock_open.call_args[0][0]
        assert b"whisper-1" in req.data
