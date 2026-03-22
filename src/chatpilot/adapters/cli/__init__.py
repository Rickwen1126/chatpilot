"""CLI channel adapter — stdin/stdout interaction."""

from __future__ import annotations

from fastapi import Request

from chatpilot.core.types import Message, Response


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
