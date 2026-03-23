"""warehouse_query tool — query warehouse inventory via backend API."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from copilot.types import ToolInvocation, ToolResult

from chatpilot.core.types import AccessLevel, ToolDefinition

logger = logging.getLogger(__name__)

WAREHOUSE_API = "http://localhost:8000/api/v1"
WAREHOUSE_WEB = "https://warehouse.shinyipaint.com.tw"
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


def create_warehouse_query_tool() -> ToolDefinition:
    """Create warehouse query tool for inventory lookup."""

    async def handler(invocation: ToolInvocation) -> ToolResult:
        args = invocation.get("arguments") or {}
        query = args.get("query", "").strip()
        query_type = args.get("query_type", "search")

        if not query:
            return ToolResult(
                textResultForLlm="請提供搜尋關鍵字",
                resultType="failure",
            )

        try:
            if query_type == "search":
                result = await _search_items(query)
            elif query_type == "location":
                result = await _query_location(query)
            elif query_type == "brand":
                result = await _search_by_brand(query)
            elif query_type == "low_stock":
                result = await _low_stock()
            else:
                result = await _search_items(query)

            return ToolResult(
                textResultForLlm=result,
                resultType="success",
            )
        except Exception as e:
            logger.error("Warehouse query failed: %s", e)
            return ToolResult(
                textResultForLlm=f"倉庫查詢失敗: {e}",
                resultType="failure",
            )

    return ToolDefinition(
        name="warehouse_query",
        description=(
            "查詢信益倉庫庫存位置和數量。"
            "可搜尋物料名稱、品牌、色號、位置。"
            "query_type: search（搜物料）、location（查位置內容）、"
            "brand（品牌查詢）、low_stock（低庫存）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字（物料名、品牌、色號、位置編號）",
                },
                "query_type": {
                    "type": "string",
                    "enum": ["search", "location", "brand", "low_stock"],
                    "description": "查詢類型",
                },
            },
            "required": ["query"],
        },
        handler=handler,
        access_level=AccessLevel.GLOBAL,
    )


async def _search_items(query: str) -> str:
    """Search items by keyword. Falls back to materials search if no direct match."""
    import asyncio

    def _fetch_items(q: str) -> list:
        params = urllib.parse.urlencode({"q": q})
        url = f"{WAREHOUSE_API}/items/search?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def _fetch_materials(q: str) -> list:
        params = urllib.parse.urlencode({"search": q})
        url = f"{WAREHOUSE_API}/materials?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    # Try direct item search first
    items = await asyncio.to_thread(_fetch_items, query)
    if items:
        return _format_search_results(items, query)

    # Fallback: search materials catalog, then search by material name
    materials = await asyncio.to_thread(_fetch_materials, query)
    if materials:
        all_items = []
        for mat in materials[:5]:
            mat_name = mat.get("name", "")
            if mat_name:
                found = await asyncio.to_thread(_fetch_items, mat_name)
                all_items.extend(found)
        if all_items:
            return _format_search_results(all_items, query)

        # Materials found but no items in stock
        names = [m.get("name", "") for m in materials[:5]]
        deep_link = _make_deep_link(query)
        return (
            "找到相關物料但目前無庫存：\n"
            + "\n".join(f"  {n}" for n in names)
            + f"\n\n👉 {deep_link}"
        )

    return f"找不到「{query}」相關的物料或庫存\n\n👉 {_make_deep_link(query)}"


async def _query_location(unit_id: str) -> str:
    """Query items at a specific location."""
    import asyncio

    def _fetch():
        url = f"{WAREHOUSE_API}/units/{unit_id}/layers/all/items"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            # Try search fallback
            params = urllib.parse.urlencode({"q": unit_id})
            url2 = f"{WAREHOUSE_API}/items/search?{params}"
            req2 = urllib.request.Request(url2, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req2, timeout=10) as resp:
                return json.loads(resp.read().decode())

    items = await asyncio.to_thread(_fetch)
    return _format_location_results(items, unit_id)


async def _search_by_brand(brand: str) -> str:
    """Search materials by brand, then find their items."""
    import asyncio

    def _fetch():
        params = urllib.parse.urlencode({"search": brand})
        url = f"{WAREHOUSE_API}/materials?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    materials = await asyncio.to_thread(_fetch)
    if not materials:
        return f"找不到品牌「{brand}」的物料"

    lines = [f"品牌「{brand}」的物料："]
    for m in materials[:10]:
        name = m.get("name", "")
        cat = m.get("category", "")
        lines.append(f"  {name}（{cat}）")

    deep_link = _make_deep_link(brand)
    lines.append(f"\n{deep_link}")
    return "\n".join(lines)


async def _low_stock() -> str:
    """Find low stock items."""
    import asyncio

    def _fetch():
        url = f"{WAREHOUSE_API}/inventory"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    data = await asyncio.to_thread(_fetch)
    inventory = data.get("inventory", {})

    low_items = []
    for unit_id, layers in inventory.items():
        for layer_key, items in layers.items():
            for item in items:
                qty = item.get("quantity", 0)
                if qty is not None and qty <= 2:
                    low_items.append({
                        "name": item.get("name", ""),
                        "location": f"{unit_id} {layer_key}",
                        "quantity": qty,
                    })

    if not low_items:
        return "目前沒有低庫存物品（數量 ≤ 2）"

    lines = ["低庫存物品（數量 ≤ 2）："]
    for item in low_items[:20]:
        lines.append(
            f"  {item['name']} — {item['location']} — 剩 {item['quantity']}"
        )
    if len(low_items) > 20:
        lines.append(f"  ...還有 {len(low_items) - 20} 項")
    return "\n".join(lines)


def _format_search_results(items: list, query: str) -> str:
    """Format search results with location and deep link."""
    if not items:
        return f"找不到「{query}」相關的庫存"

    # Group by material name
    groups: dict[str, list] = {}
    for item in items:
        name = item.get("name", "") or item.get("description", "")
        if name not in groups:
            groups[name] = []
        groups[name].append(item)

    lines = []
    total_qty = 0
    zones_seen: set[str] = set()

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
            zone = UNIT_TO_ZONE.get(unit_id)
            if zone:
                zones_seen.add(zone)

    lines.append(f"\n共 {total_qty} 件")

    # Deep link
    deep_link = _make_deep_link(query)
    lines.append(f"\n👉 {deep_link}")

    # Zone image URL
    if len(zones_seen) == 1:
        zone = zones_seen.pop()
        img_url = ZONE_IMAGES.get(zone)
        if img_url:
            lines.append(f"\n[image:{img_url}]")
    elif len(zones_seen) > 1:
        img_url = ZONE_IMAGES.get("overview")
        if img_url:
            lines.append(f"\n[image:{img_url}]")

    return "\n".join(lines)


def _format_location_results(items: list, unit_id: str) -> str:
    """Format location query results."""
    if not items:
        return f"位置 {unit_id} 沒有找到物品"

    lines = [f"位置 {unit_id} 的物品："]
    for item in items[:20]:
        name = item.get("name", "") or item.get("description", "")
        layer = item.get("layer_display", item.get("layer_key", ""))
        qty = item.get("quantity", "?")
        lines.append(f"  {layer}: {name} — {qty}")

    zone = UNIT_TO_ZONE.get(unit_id)
    if zone:
        lines.append(f"\n[zone:{zone}]")

    return "\n".join(lines)


def _make_deep_link(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"{WAREHOUSE_WEB}/#/search?q={encoded}"
