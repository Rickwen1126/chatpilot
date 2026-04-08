from __future__ import annotations

import json

from chatpilot.core.types import ObserverBatchPayload


def build_observation_worker_system_message() -> str:
    """Return the strict system role for observation capture workers."""
    return (
        "你是 observation capture worker，不是對話助理。\n"
        "你的任務是依照給定的 profile 規格，把一批訊息整理成可安全落 DB 的結構化知識。\n"
        "你只能輸出 JSON object，格式必須符合要求；不要輸出 Markdown、說明文字或額外包裝。\n"
        "你不可創造新事實，不可替使用者補猜，不可把 reported_by 當成 subject。\n"
        "若 batch 中有圖片 ref，預設應先用 observe_image_ref(image_ref) 查看圖片；"
        "每批最多查看 1 張最有資訊量的圖片，不要對每一張圖都呼叫工具。\n"
        "只有當同一則訊息已用文字完整描述、且不看圖也不影響整理時，才可略過。\n"
        "若圖片工具回傳的是具體可見事實（例如文字標示、數量、物料名稱、施工完成狀態），"
        "即使缺少完整事件背景，也應以保守措辭保留，例如「圖片標示白漆 2 桶」或"
        "「圖片可見牆面已上第一道底漆」。\n"
        "不可憑空猜圖，也不可假裝自己已看過圖。"
    )


def build_observation_worker_prompt(payload: ObserverBatchPayload) -> str:
    """Build the user prompt for the observation worker."""
    categories = payload.categories or ["其他"]
    schema = {
        "summary": "string",
        "facts": [
            {
                "category": categories[0],
                "subject": "主要對象，例如阿明或底漆",
                "record_date": "YYYY-MM-DD",
                "content": "可直接保留的事實描述",
                "reported_by_name": "必須直接來自來源訊息中的說話者名稱",
                "search_text": "查詢友善文字，可含同義詞但不得創造新事實",
                "facets_json": {},
            }
        ],
        "semantic": [
            {
                "canonical_fact_index": 0,
                "category": categories[0],
                "subject": "與對應 fact 相同或更通用的對象",
                "record_date": "YYYY-MM-DD",
                "content": "僅供 retrieval aid 的語意重寫",
                "reported_by_name": "可選；若不知道可留空字串",
                "search_text": "更有利查詢命中的文字",
                "facets_json": {},
            }
        ],
    }
    category_lines = "\n".join(f"- {item}" for item in categories)
    return (
        f"[Capture Profile]\n"
        f"name: {payload.captured_profile_name}\n"
        f"instructions:\n{payload.instructions.strip()}\n\n"
        "[Category Contract]\n"
        "你只能從以下 categories 中選 category；真的無法歸類才用「其他」。\n"
        f"{category_lines}\n\n"
        "[Field Semantics]\n"
        "- subject: 這筆知識主要在說誰/什麼，不是發話者。\n"
        "- reported_by_name: 必須直接來自來源訊息中的說話者名稱；不要捏造新名稱。\n"
        "- search_text: 給查詢用的擴充文字，可以補同義詞或查詢友善重寫，但不得創造新事實。\n"
        "- semantic rows: 只作 retrieval aid，不得創造新事實，且必須用 "
        "canonical_fact_index 指回 facts 陣列。\n"
        "- 若 source messages 中含有 [圖片 ref:...]，預設應先用 "
        "observe_image_ref(image_ref) 取得圖片描述，再整理進 facts/semantic；"
        "每批最多查看 1 張最有資訊量的圖片，避免重複分析相似或無資訊量的圖片；"
        "只有當同一則文字已完整描述、且圖片不會改變整理結果時才可略過。\n"
        "- 若圖片描述中含有具體可見事實（例如圖片標示的物料名稱、數量、可見施工狀態），"
        "應以保守措辭保留成 fact，例如「圖片標示白漆 2 桶」；不要因為缺少完整背景就整筆捨棄。\n"
        "- 若資訊不足，不要補猜；沒有值得保存的知識時，facts/semantic 應為空陣列。\n\n"
        "[Output Contract]\n"
        "只回傳 JSON object，格式如下：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "[Source Messages]\n"
        f"{payload.formatted_messages}"
    )
