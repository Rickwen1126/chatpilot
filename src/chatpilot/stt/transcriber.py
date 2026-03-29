"""SttTranscriber — async speech-to-text via OpenAI gpt-4o-mini-transcribe."""

from __future__ import annotations

import asyncio
import io
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini-transcribe"


class SttTranscriber:
    """Transcribe audio bytes to text using OpenAI transcription API.

    If OPENAI_API_KEY is not set, all calls return None (graceful skip).
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        if not self._api_key:
            logger.warning("SttTranscriber: no OPENAI_API_KEY, transcription disabled")

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "zh",
        filename: str = "audio.m4a",
    ) -> str | None:
        """Transcribe audio bytes to text.

        Returns transcribed text, or None on failure / disabled.
        """
        if not self._api_key:
            return None

        try:
            return await asyncio.to_thread(
                self._call_api, audio_bytes, language, filename
            )
        except Exception as e:
            logger.error("STT transcription failed: %s", e)
            return None

    def _call_api(
        self, audio_bytes: bytes, language: str, filename: str
    ) -> str:
        """Synchronous API call (run in thread)."""
        import json
        import urllib.request

        boundary = "----SttBoundary"
        body = io.BytesIO()

        def add_field(name: str, value: str) -> None:
            body.write(f"--{boundary}\r\n".encode())
            body.write(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            body.write(f"{value}\r\n".encode())

        def add_file(name: str, fname: str, data: bytes) -> None:
            body.write(f"--{boundary}\r\n".encode())
            body.write(
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{fname}"\r\n'.encode()
            )
            body.write(b"Content-Type: application/octet-stream\r\n\r\n")
            body.write(data)
            body.write(b"\r\n")

        add_field("model", self._model)
        add_field("language", language)
        add_file("file", filename, audio_bytes)
        body.write(f"--{boundary}--\r\n".encode())

        payload = body.getvalue()
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        text = result.get("text", "").strip()
        logger.info("STT transcribed %d bytes → %d chars", len(audio_bytes), len(text))
        return text if text else None
