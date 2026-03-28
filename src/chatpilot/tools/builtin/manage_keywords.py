"""manage_trigger_keywords tool — add/remove/list trigger keywords per route."""

from __future__ import annotations

import logging

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition
from chatpilot.hub.mention_filter import (
    MAX_ROUTE_KEYWORDS,
    MIN_KEYWORD_LENGTH,
    add_route_keyword,
    get_config_keywords,
    get_route_keywords,
    remove_route_keyword,
)

logger = logging.getLogger(__name__)


def create_manage_keywords_tool(memory_store) -> ToolDefinition:
    """Create a tool for managing per-route trigger keywords."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments", {})
        action = args.get("action", "list").strip().lower()
        keyword = args.get("keyword", "").strip()
        session_id = invocation.get("session_id", "")

        # Extract route_id and chatbot_name from session
        route_id = session_id.split("__")[0].replace("-", ":", 1)
        chatbot_name = session_id.split("__")[1] if "__" in session_id else ""

        if action == "list":
            db_keywords = get_route_keywords(route_id)
            config_keywords = get_config_keywords(chatbot_name)
            parts = []
            if config_keywords:
                parts.append(
                    "系統設定的關鍵字（無法移除）：\n"
                    + "、".join(config_keywords)
                )
            if db_keywords:
                parts.append(
                    "自訂關鍵字：\n" + "、".join(db_keywords)
                )
            if not parts:
                return ToolResult(
                    textResultForLlm="目前沒有設定任何觸發關鍵字",
                    resultType="success",
                )
            return ToolResult(
                textResultForLlm="\n\n".join(parts),
                resultType="success",
            )

        if not keyword:
            return ToolResult(
                textResultForLlm="需要提供 keyword 參數",
                resultType="failure",
            )

        if action == "add":
            # Validation
            if len(keyword) < MIN_KEYWORD_LENGTH:
                return ToolResult(
                    textResultForLlm=f"關鍵字至少要 {MIN_KEYWORD_LENGTH} 個字",
                    resultType="failure",
                )
            existing = get_route_keywords(route_id)
            if keyword in existing:
                return ToolResult(
                    textResultForLlm=f"「{keyword}」已經是觸發關鍵字了",
                    resultType="failure",
                )
            if len(existing) >= MAX_ROUTE_KEYWORDS:
                return ToolResult(
                    textResultForLlm=(
                        f"每個群組最多 {MAX_ROUTE_KEYWORDS} 個自訂關鍵字，"
                        f"目前已有 {len(existing)} 個"
                    ),
                    resultType="failure",
                )

            # Write DB first → success → update cache
            await memory_store.add_trigger_keyword(route_id, keyword)
            add_route_keyword(route_id, keyword)
            logger.info(
                "Trigger keyword added: route=%s keyword='%s'",
                route_id[:16], keyword,
            )
            return ToolResult(
                textResultForLlm=f"已新增觸發關鍵字「{keyword}」",
                resultType="success",
            )

        if action == "remove":
            # Can't remove config seed keywords
            config_kws = get_config_keywords(chatbot_name)
            if keyword in config_kws:
                return ToolResult(
                    textResultForLlm=(
                        f"「{keyword}」是系統設定的關鍵字，無法移除。"
                        "請聯繫管理員修改設定。"
                    ),
                    resultType="failure",
                )
            existing = get_route_keywords(route_id)
            if keyword not in existing:
                return ToolResult(
                    textResultForLlm=f"找不到自訂關鍵字「{keyword}」",
                    resultType="failure",
                )

            # Write DB first → success → update cache
            deleted = await memory_store.remove_trigger_keyword(
                route_id, keyword
            )
            if deleted:
                remove_route_keyword(route_id, keyword)
            logger.info(
                "Trigger keyword removed: route=%s keyword='%s'",
                route_id[:16], keyword,
            )
            return ToolResult(
                textResultForLlm=f"已移除觸發關鍵字「{keyword}」",
                resultType="success",
            )

        return ToolResult(
            textResultForLlm="action 必須是 add、remove 或 list",
            resultType="failure",
        )

    return ToolDefinition(
        name="manage_trigger_keywords",
        description=(
            "管理觸發關鍵字。群組裡有人說出關鍵字時，你會被喚醒回應。\n"
            "action=list：列出目前所有關鍵字\n"
            "action=add：新增一個關鍵字（例如使用者要你改名）\n"
            "action=remove：移除一個自訂關鍵字（系統設定的無法移除）"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "list"],
                    "description": "操作類型",
                },
                "keyword": {
                    "type": "string",
                    "description": "要新增或移除的關鍵字（list 時不需要）",
                },
            },
            "required": ["action"],
        },
        handler=handler,
        access_level=AccessLevel.CHATBOT_ONLY,
    )
