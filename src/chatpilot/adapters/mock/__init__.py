"""Mock channel adapter — in-memory buffer for testing."""

from __future__ import annotations

from fastapi import Request

from chatpilot.core.types import Message, Response


class MockAdapter:
    """Mock adapter for testing. Stores replies/pushes in memory."""

    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []  # (conversation_id, text)
        self.pushes: list[tuple[str, str]] = []   # (route_id, text)

    @property
    def platform(self) -> str:
        return "mock"

    @property
    def format_hint(self) -> str | None:
        return None  # Mock supports any format

    async def verify_request(self, request: Request) -> bool:
        return True

    async def parse_messages(self, request: Request) -> list[Message]:
        body = await request.json()
        return [
            Message(
                text=body["text"],
                user_id=body.get("user_id", "mock-user"),
                user_name=body.get("user_name", "MockUser"),
                platform="mock",
                group_id=body.get("group_id"),
                conversation_id=body.get("group_id", body.get("user_id", "mock-user")),
                is_mention=body.get("is_mention", True),
            )
        ]

    async def send_reply(self, message: Message, response: Response) -> None:
        self.replies.append((message.conversation_id, response.text))

    async def push_message(self, route_id: str, response: Response) -> None:
        self.pushes.append((route_id, response.text))

    async def download_media(self, media_id: str) -> bytes | None:
        """Return a tiny test PNG for mock media IDs."""
        import struct
        import zlib

        w, h = 2, 2
        raw = b""
        for _ in range(h):
            raw += b"\x00" + bytes([255, 0, 0]) * w  # red pixels
        compressed = zlib.compress(raw)

        def chunk(ct: bytes, d: bytes) -> bytes:
            c = ct + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )
