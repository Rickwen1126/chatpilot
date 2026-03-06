"""Warehouse agent — AI-powered paint warehouse inventory assistant."""

from __future__ import annotations

import logging

from chatpilot.agents.warehouse.db import load_full_inventory
from chatpilot.core.errors import AgentError
from chatpilot.core.types import Message, Response
from chatpilot.sdk.session_manager import session_manager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是「信益油漆倉庫管理助手」。根據下方的完整倉庫資料回答使用者問題。

## 倉庫結構
- 儲位編號格式：字母+數字，如 A1, B2, C3, D4, K1, M
- 特殊儲位：G, I（平面區）
- 每個儲位有多層：layer1-layer4, floor（地板）
- 資料格式：儲位/層: 品名 ×數量單位

## 回答規則
1. 只根據下方【倉庫資料】回答，絕對不要編造資料
2. 使用繁體中文，簡潔友善
3. 查詢品項時，列出品名、數量、位置
4. 查詢儲位時，列出該位置所有品項
5. 如果使用者問的東西在資料中找不到，明確說找不到
6. 可以做統計、彙整、比較等分析
7. 回覆用純文字，不用 markdown
"""


class WarehouseAgent:
    """AI agent backed by full inventory context + LLM."""

    @property
    def name(self) -> str:
        return "warehouse-agent"

    async def handle(
        self, message: Message, session_id: str, model: str | None = None
    ) -> Response:
        user_query = message.text.strip()
        logger.info("[WH] handle start query=%r session=%s", user_query[:50], session_id)

        try:
            inventory = load_full_inventory()
            logger.info("[WH] DB loaded, %d chars", len(inventory))
        except Exception as e:
            logger.error("[WH] DB error: %s", e)
            return Response(text="無法連接倉庫資料庫，請稍後再試。")

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"【倉庫資料】\n{inventory}\n\n"
            f"【使用者問題】\n{user_query}"
        )
        logger.info("[WH] prompt built, %d chars", len(prompt))

        try:
            wh_session_id = f"wh-{session_id}"
            logger.info("[WH] getting session %s", wh_session_id)
            session = await session_manager.get_or_create_session(
                wh_session_id, model=model
            )
            logger.info("[WH] session ready, calling send_and_wait")
            result = await session_manager.send_and_wait(session, prompt)
            logger.info("[WH] got result, %d chars: %r", len(result), result[:80])
            return Response(text=result)
        except Exception as e:
            logger.error(
                "[WH] LLM error (%s): %s", type(e).__name__, e, exc_info=True
            )
            raise AgentError(
                "倉庫助手暫時無法回應，請稍後再試。",
                cause=e,
            ) from e


warehouse_agent = WarehouseAgent()
