"""Webhook handler — POST /webhook/{platform} thin route."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from chatpilot.channels.adapter import AdapterRegistry

router = APIRouter()


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> Response:
    """Handle incoming webhook from any platform."""
    app = request.app
    adapter_registry: AdapterRegistry = app.state.adapter_registry

    adapter = adapter_registry.get(platform)
    if adapter is None:
        return Response(status_code=400, content=f"Unknown platform: {platform}")

    raw_body = await request.body()
    signature = request.headers.get("x-line-signature", "")
    if not adapter.verify_signature(raw_body, signature):
        return Response(status_code=401, content="Invalid signature")

    if hasattr(adapter, "parse_messages_with_signature"):
        messages = adapter.parse_messages_with_signature(raw_body, signature)
    else:
        messages = adapter.parse_messages(raw_body)

    for msg in messages:
        await app.state.processor.process(msg, adapter)

    return Response(status_code=200, content="OK")
