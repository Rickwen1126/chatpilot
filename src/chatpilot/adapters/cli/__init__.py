"""CLI channel adapter — stdin/stdout interaction."""

from __future__ import annotations

from fastapi import Request

from chatpilot.core.types import Message, Response
from chatpilot.files.models import SourceFetchResult, SourceHandleInput


class CliAdapter:
    """CLI adapter for local development."""

    @property
    def platform(self) -> str:
        return "cli"

    @property
    def format_hint(self) -> str | None:
        return None  # CLI supports Markdown

    async def verify_request(self, request: Request) -> bool:
        return True

    async def parse_messages(self, request: Request) -> list[Message]:
        body = await request.json()
        return [
            Message(
                text=body["text"],
                user_id=body.get("user_id", "cli-user"),
                platform="cli",
                conversation_id=body.get("session_id", "cli-user"),
                is_mention=True,
            )
        ]

    async def send_reply(self, message: Message, response: Response) -> None:
        print(response.text)

    async def push_message(self, route_id: str, response: Response) -> None:
        print(f"[PUSH] {response.text}")

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
        return None

    async def fetch_source_file(
        self,
        source: SourceHandleInput,
    ) -> SourceFetchResult | None:
        _ = source
        return None
