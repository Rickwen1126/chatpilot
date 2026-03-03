"""Mock channel adapter — for testing and architecture validation."""

from __future__ import annotations

import json
import logging

from chatpilot.core.types import Message, Response

logger = logging.getLogger(__name__)


class MockAdapter:
    """Mock adapter for testing — proves Ports & Adapters architecture."""

    @property
    def platform(self) -> str:
        return "mock"

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        return True

    def parse_messages(self, raw_body: bytes) -> list[Message]:
        try:
            data = json.loads(raw_body)
            return [
                Message(
                    text=data.get("text", ""),
                    user_id=data.get("userId", "mock-user"),
                    platform="mock",
                    conversation_id=data.get("conversationId"),
                )
            ]
        except Exception as e:
            logger.error("Mock parse error: %s", e)
            return []

    async def send_response(self, message: Message, response: Response) -> None:
        print(f"[MOCK SEND] {response.text}", flush=True)

    async def send_processing_ack(self, message: Message) -> None:
        print("[MOCK ACK]", flush=True)


mock_adapter = MockAdapter()
