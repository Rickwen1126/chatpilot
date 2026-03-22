"""Webhook handler — thin route layer for POST /webhook/{platform}."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/{platform}")
async def webhook_handler(platform: str, request: Request) -> JSONResponse:
    """Handle incoming webhook from any platform."""
    adapters: dict = request.app.state.adapters
    hub = request.app.state.hub

    adapter = adapters.get(platform)
    if adapter is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown platform: {platform}", "code": "PLATFORM_UNKNOWN"},
        )

    try:
        await adapter.verify_request(request)
    except Exception as e:
        logger.warning("Signature verification failed for %s: %s", platform, e)
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid signature", "code": "SIGNATURE_INVALID"},
        )

    messages = await adapter.parse_messages(request)
    for msg in messages:
        await hub.receive(msg, adapter)

    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    uptime = time.time() - request.app.state.start_time
    return JSONResponse(
        content={
            "status": "ok",
            "version": "0.2.0",
            "uptime_seconds": int(uptime),
        }
    )
