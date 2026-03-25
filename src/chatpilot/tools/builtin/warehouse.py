"""warehouse tool — full warehouse management via backend API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

WAREHOUSE_API = os.environ.get("WAREHOUSE_API_URL", "http://localhost:8000/api/v1")
WAREHOUSE_WEB = os.environ.get("WAREHOUSE_WEB_URL", "https://warehouse.shinyipaint.com.tw")
R2_ZONE_BASE = "https://pub-fcc500f8fb48414aba2084e196f653eb.r2.dev/zone"

ZONE_IMAGES = {
    "zone_AB": f"{R2_ZONE_BASE}/floor_plan_zone_AB.png",
    "zone_CD": f"{R2_ZONE_BASE}/floor_plan_zone_CD.png",
    "zone_H": f"{R2_ZONE_BASE}/floor_plan_zone_H.png",
    "zone_E": f"{R2_ZONE_BASE}/floor_plan_zone_E.png",
    "zone_J": f"{R2_ZONE_BASE}/floor_plan_zone_J.png",
    "zone_flat": f"{R2_ZONE_BASE}/floor_plan_zone_flat.png",
    "zone_1F": f"{R2_ZONE_BASE}/floor_plan_zone_1F.png",
    "overview": f"{R2_ZONE_BASE}/floor_plan_overview.png",
}

UNIT_TO_ZONE = {
    "A1": "zone_AB", "A2": "zone_AB", "A3": "zone_AB", "A4": "zone_AB",
    "B1": "zone_AB", "B2": "zone_AB", "B3": "zone_AB", "B4": "zone_AB",
    "C1": "zone_CD", "C2": "zone_CD", "C3": "zone_CD", "C4": "zone_CD",
    "D1": "zone_CD", "D2": "zone_CD", "D3": "zone_CD", "D4": "zone_CD",
    "H1": "zone_H", "H2": "zone_H", "H3": "zone_H", "H4": "zone_H",
    "H5": "zone_H",
    "E1": "zone_E", "E2": "zone_E", "E3": "zone_E", "E4": "zone_E",
    "E5": "zone_E", "E6": "zone_E", "E7": "zone_E",
    "J1": "zone_J", "J2": "zone_J", "J3": "zone_J",
    "I": "zone_flat", "G": "zone_flat", "F1": "zone_flat",
    "F2": "zone_flat", "K1": "zone_flat", "K2": "zone_flat",
    "K3": "zone_flat", "L": "zone_flat",
    "M": "zone_1F", "N": "zone_1F",
}


# ── HTTP helpers ─────────────────────────────────────────────────


def _get(path: str, params: dict | None = None, timeout: int = 10) -> Any:
    url = f"{WAREHOUSE_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _post(path: str, body: Any = None, timeout: int = 10) -> Any:
    url = f"{WAREHOUSE_API}{path}"
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _put(path: str, body: Any = None, timeout: int = 10) -> Any:
    url = f"{WAREHOUSE_API}{path}"
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        url, data=data, method="PUT",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _delete(path: str, timeout: int = 10) -> Any:
    url = f"{WAREHOUSE_API}{path}"
    req = urllib.request.Request(
        url, method="DELETE",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _post_file(path: str, file_bytes: bytes, filename: str, timeout: int = 15) -> Any:
    """Upload file via multipart/form-data."""
    import uuid
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    url = f"{WAREHOUSE_API}{path}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ── Action handlers ──────────────────────────────────────────────


async def _action_search(args: dict) -> str:
    query = args.get("query", "")
    include_locked = args.get("include_locked", False)

    items = await asyncio.to_thread(
        _get, "/items/search", {"q": query, "include_locked": str(include_locked).lower()}
    )
    if items:
        return _format_search_results(items, query)

    # Fallback: materials search
    materials = await asyncio.to_thread(_get, "/materials", {"search": query})
    if materials:
        all_items = []
        for mat in materials[:5]:
            name = mat.get("name", "")
            if name:
                found = await asyncio.to_thread(_get, "/items/search", {"q": name})
                all_items.extend(found)
        if all_items:
            return _format_search_results(all_items, query)
        names = [m.get("name", "") for m in materials[:5]]
        return "找到相關物料但目前無庫存：\n" + "\n".join(f"  {n}" for n in names)

    return f"找不到「{query}」相關的物料或庫存"


async def _action_get_items(args: dict) -> str:
    uid = args.get("unit_id", "")
    if not uid:
        return "需要提供 unit_id（如 K1, A2）"
    layer = args.get("layer", "")

    if layer:
        items = await asyncio.to_thread(
            _get, f"/units/{uid}/layers/{layer}/items"
        )
    else:
        items = await asyncio.to_thread(_get, f"/units/{uid}/items")

    if not items:
        label = f"{uid}/{layer}" if layer else uid
        return f"位置 {label} 沒有物品"

    lines = [f"位置 {uid}{f'/{layer}' if layer else ''} 的物品："]
    for item in items:
        name = item.get("name", "") or item.get("description", "")
        lk = item.get("layer_display", item.get("layer_key", ""))
        qty = item.get("quantity", "?")
        iid = item.get("id", "?")
        lines.append(f"  {lk}: {name} — {qty}（ID:{iid}）")
    return "\n".join(lines)


async def _action_get_inventory() -> str:
    data = await asyncio.to_thread(_get, "/inventory", timeout=15)
    locked = data.get("locked_units", [])
    inventory = data.get("inventory", {})
    total_items = sum(
        len(items) for layers in inventory.values() for items in layers.values()
    )
    total_units = len(inventory)
    lines = [f"庫存快照：{total_units} 個位置，{total_items} 筆物品"]
    if locked:
        lines.append(f"鎖倉中：{', '.join(locked)}")
    return "\n".join(lines)


async def _action_search_materials(args: dict) -> str:
    query = args.get("query", "")
    materials = await asyncio.to_thread(_get, "/materials", {"search": query})
    if not materials:
        return f"找不到「{query}」相關的物料"
    lines = [f"物料目錄（{query}）："]
    for m in materials[:15]:
        lines.append(f"  ID:{m.get('id')} {m.get('name', '')}（{m.get('category', '')}）")
    return "\n".join(lines)


async def _action_add_item(args: dict) -> str:
    uid = args.get("unit_id", "")
    if not uid:
        return "需要提供 unit_id"
    layer = args.get("layer", "floor")
    item = {
        "name": args.get("name", ""),
        "description": args.get("description", ""),
        "quantity": args.get("quantity", 1),
        "unit_of_measure": args.get("unit_of_measure", "桶"),
    }
    if args.get("material_id"):
        item["material_id"] = args["material_id"]
    result = await asyncio.to_thread(_post, f"/units/{uid}/layers/{layer}/items", item)
    return f"已新增：{item['name']} → {uid}/{layer}（ID:{result.get('id', '?')}）"


async def _action_update_item(args: dict) -> str:
    item_id = args.get("item_id", "")
    if not item_id:
        return "需要提供 item_id"
    updates = {}
    for key in ("name", "description", "quantity", "unit_of_measure", "material_id", "image_paths"):
        if key in args:
            updates[key] = args[key]
    await asyncio.to_thread(_put, f"/items/{item_id}", updates)
    return f"已更新 item {item_id}"


async def _action_delete_item(args: dict) -> str:
    item_id = args.get("item_id", "")
    if not item_id:
        return "需要提供 item_id"
    await asyncio.to_thread(_delete, f"/items/{item_id}")
    return f"已刪除 item {item_id}"


async def _action_move_item(args: dict) -> str:
    item_id = args.get("item_id", "")
    if not item_id:
        return "需要提供 item_id"
    body = {
        "target_unit_id": args.get("target_unit_id", ""),
        "target_layer_key": args.get("target_layer_key", "floor"),
    }
    await asyncio.to_thread(_post, f"/items/{item_id}/move", body)
    return f"已移動 item {item_id} → {body['target_unit_id']}/{body['target_layer_key']}"


async def _action_replace_layer(args: dict) -> str:
    uid = args.get("unit_id", "")
    if not uid:
        return "需要提供 unit_id"
    layer = args.get("layer", "floor")
    items = args.get("items", [])
    result = await asyncio.to_thread(_put, f"/units/{uid}/layers/{layer}/items", items)
    count = len(result) if isinstance(result, list) else "?"
    return f"已替換 {uid}/{layer}，寫入 {count} 筆"


async def _action_batch_items(args: dict) -> str:
    items = args.get("items", [])
    result = await asyncio.to_thread(_post, "/batch/items", items)
    count = len(result) if isinstance(result, list) else "?"
    return f"批次建立完成，{count} 筆"


async def _action_lock(args: dict) -> str:
    uid = args.get("unit_id", "")
    if not uid:
        return "需要提供 unit_id（如 K1, A2）"
    await asyncio.to_thread(_put, f"/units/{uid}/lock")
    return f"已鎖倉 {uid}（搜尋將排除此區域）"


async def _action_unlock(args: dict) -> str:
    uid = args.get("unit_id", "")
    if not uid:
        return "需要提供 unit_id（如 K1, A2）"
    await asyncio.to_thread(_put, f"/units/{uid}/unlock")
    return f"已解鎖 {uid}"


async def _action_lock_all() -> str:
    result = await asyncio.to_thread(_put, "/units/lock-all")
    affected = result.get("affected", "?") if isinstance(result, dict) else "?"
    return f"已鎖倉全部 {affected} 個區域"


async def _action_unlock_all() -> str:
    result = await asyncio.to_thread(_put, "/units/unlock-all")
    affected = result.get("affected", "?") if isinstance(result, dict) else "?"
    return f"已解鎖全部 {affected} 個區域"


async def _action_list_locked() -> str:
    result = await asyncio.to_thread(_get, "/units/locked")
    locked = result if isinstance(result, list) else result.get("locked_units", [])
    if not locked:
        return "目前沒有鎖倉中的區域"
    return f"鎖倉中：{', '.join(locked)}"


async def _action_upload_image(args: dict) -> str:
    image_bytes = args.get("_image_bytes")
    filename = args.get("filename", "photo.jpg")
    if not image_bytes:
        return "需要提供圖片 bytes（先用 download_media 下載）"
    result = await asyncio.to_thread(_post_file, "/images", image_bytes, filename)
    path = result.get("path", "?")
    return f"照片已上傳：{path}"


async def _action_update_alias(args: dict) -> str:
    uid = args.get("unit_id", "")
    body = {
        "primary_name": args.get("primary_name", ""),
        "other_names": args.get("other_names", []),
    }
    await asyncio.to_thread(_put, f"/units/{uid}/alias", body)
    return f"已更新 {uid} 別名：{body['primary_name']}"


# ── Formatting ───────────────────────────────────────────────────


def _format_search_results(items: list, query: str) -> str:
    if not items:
        return f"找不到「{query}」相關的庫存"

    groups: dict[str, list] = {}
    for item in items:
        name = item.get("name", "") or item.get("description", "")
        if name not in groups:
            groups[name] = []
        groups[name].append(item)

    lines = []
    total_qty = 0

    for name, group_items in groups.items():
        lines.append(f"\n{name}：")
        for item in group_items:
            unit_id = item.get("unit_id", "?")
            layer = item.get("layer_display", item.get("layer_key", ""))
            qty = item.get("quantity", "?")
            loc = item.get("location_display", f"{unit_id} {layer}")
            lines.append(f"  📍 {loc} — {qty}")
            if isinstance(qty, (int, float)):
                total_qty += qty

    lines.append(f"\n共 {total_qty} 件")
    return "\n".join(lines)


def _make_deep_link(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"{WAREHOUSE_WEB}/#/search?q={encoded}"


# ── Tool definition ──────────────────────────────────────────────

ACTION_DISPATCH = {
    "search": _action_search,
    "get_items": _action_get_items,
    "get_inventory": _action_get_inventory,
    "search_materials": _action_search_materials,
    "add_item": _action_add_item,
    "update_item": _action_update_item,
    "delete_item": _action_delete_item,
    "move_item": _action_move_item,
    "replace_layer": _action_replace_layer,
    "batch_items": _action_batch_items,
    "lock": _action_lock,
    "unlock": _action_unlock,
    "lock_all": _action_lock_all,
    "unlock_all": _action_unlock_all,
    "list_locked": _action_list_locked,
    "upload_image": _action_upload_image,
    "update_alias": _action_update_alias,
}


def create_warehouse_tool() -> ToolDefinition:
    """Create unified warehouse management tool."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        action = args.get("action", "search")

        fn = ACTION_DISPATCH.get(action)
        if fn is None:
            return ToolResult(
                textResultForLlm=f"未知的 action: {action}",
                resultType="failure",
            )

        try:
            import inspect

            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())

            if params:
                result = await fn(args)
            else:
                result = await fn()

            return ToolResult(textResultForLlm=result, resultType="success")
        except Exception as e:
            logger.error("warehouse %s failed: %s", action, e)
            return ToolResult(
                textResultForLlm=f"倉庫操作失敗（{action}）: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="warehouse",
        description=(
            "信益倉庫管理工具。支援以下 action：\n"
            "查詢：search（搜物料）、get_items（查位置內容）、"
            "get_inventory（庫存快照）、search_materials（物料目錄）\n"
            "寫入：add_item（新增）、update_item（更新）、delete_item（刪除）、"
            "move_item（移動）、replace_layer（替換整層，盤點用）、batch_items（批次建立）\n"
            "盤點：lock（鎖單一區域）、unlock（解鎖單一）、"
            "lock_all（全部鎖倉）、unlock_all（全部解鎖）、list_locked（列鎖倉中）\n"
            "其他：upload_image（上傳照片）、update_alias（更新別名）"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTION_DISPATCH.keys()),
                    "description": "操作類型",
                },
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字（search/search_materials）",
                },
                "unit_id": {
                    "type": "string", "description": "位置編號（K1, A2）",
                },
                "layer": {
                    "type": "string", "description": "層（floor, layer1, top）",
                },
                "item_id": {
                    "type": "integer", "description": "item ID",
                },
                "name": {"type": "string", "description": "品名"},
                "description": {
                    "type": "string", "description": "描述（色號/規格）",
                },
                "quantity": {"type": "integer", "description": "數量"},
                "unit_of_measure": {
                    "type": "string", "description": "單位（桶/罐/包）",
                },
                "material_id": {
                    "type": "integer", "description": "物料目錄 ID",
                },
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "items 列表（replace_layer/batch）",
                },
                "target_unit_id": {
                    "type": "string", "description": "移動目標位置",
                },
                "target_layer_key": {
                    "type": "string", "description": "移動目標層",
                },
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "照片路徑列表",
                },
                "include_locked": {
                    "type": "boolean",
                    "description": "搜尋含鎖倉區域",
                },
                "primary_name": {
                    "type": "string", "description": "別名主名稱",
                },
                "other_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "其他別名",
                },
                "filename": {
                    "type": "string", "description": "上傳檔名",
                },
            },
            "required": ["action"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )
