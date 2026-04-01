"""Mock channel adapter — in-memory buffer for testing."""

from __future__ import annotations

from fastapi import Request

from chatpilot.core.types import Message, Response
from chatpilot.files.models import FileKind, SourceFetchResult, SourceHandleInput


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
        platform = body.get("platform", "mock")
        user_id = body.get("user_id", "mock-user")
        group_id = body.get("group_id")
        conversation_id = group_id or user_id

        source_handles = []
        for item in body.get("source_handles", []):
            source_handles.append(
                SourceHandleInput(
                    route_id=item.get("route_id", f"{platform}:{conversation_id}"),
                    platform=item.get("platform", platform),
                    kind=item["kind"],
                    native_locator=item["native_locator"],
                    filename=item.get("filename"),
                    mime_type=item.get("mime_type"),
                    platform_context=dict(item.get("platform_context", {})),
                )
            )

        text = body.get("text", "")
        if not text and source_handles:
            tags = []
            for source in source_handles:
                if source.kind == FileKind.image:
                    tags.append(f"[圖片 ref:{source.platform}:{source.native_locator}]")
                elif source.kind == FileKind.audio:
                    tags.append(f"[音檔 ref:{source.platform}:{source.native_locator}]")
                elif source.kind == FileKind.video:
                    tags.append(f"[影片 ref:{source.platform}:{source.native_locator}]")
                else:
                    filename = source.filename or "file.bin"
                    tags.append(
                        f"[檔案 ref:{source.platform}:{source.native_locator}:{filename}]"
                    )
            text = "\n".join(tags)

        return [
            Message(
                text=text,
                user_id=user_id,
                user_name=body.get("user_name", "MockUser"),
                platform=platform,
                group_id=group_id,
                conversation_id=conversation_id,
                is_mention=body.get("is_mention", True),
                source_handles=source_handles,
            )
        ]

    async def send_reply(self, message: Message, response: Response) -> None:
        self.replies.append((message.conversation_id, response.text))

    async def push_message(self, route_id: str, response: Response) -> None:
        self.pushes.append((route_id, response.text))

    def build_source_handle(
        self,
        *,
        route_id: str,
        kind: str,
        native_locator: str,
        filename: str | None = None,
        mime_type: str | None = None,
        platform_context: dict | None = None,
    ) -> SourceHandleInput:
        return SourceHandleInput(
            route_id=route_id,
            platform=self.platform,
            kind=kind,
            native_locator=native_locator,
            filename=filename,
            mime_type=mime_type,
            platform_context=dict(platform_context or {}),
        )

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

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        data = await self.download_media(source.native_locator)
        if data is None:
            return None
        return SourceFetchResult(
            data=data,
            filename=source.filename,
            mime_type=source.mime_type or "image/png",
            size_bytes=len(data),
        )
