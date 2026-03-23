"""Tests for quote_search tool."""

import json

import pytest

from chatpilot.tools.builtin.quote_search import _load_quotes, _search


@pytest.fixture()
def quotes():
    return _load_quotes()


def test_load_quotes(quotes):
    assert len(quotes) == 8
    assert quotes[0]["id"] == "Q-2025-001"


def test_search_by_building_type(quotes):
    results = _search(quotes, building_type="住宅")
    assert len(results) == 4
    assert all(q["building_type"] == "住宅" for q in results)


def test_search_by_area_range(quotes):
    results = _search(quotes, min_area=400, max_area=1000)
    assert all(400 <= q["area_ping"] <= 1000 for q in results)
    assert len(results) == 3  # 500, 800, 600


def test_search_by_brand(quotes):
    results = _search(quotes, brand="虹牌")
    assert len(results) == 4
    assert all("虹牌" in q["paint_brand"] for q in results)


def test_search_by_keyword(quotes):
    results = _search(quotes, keyword="防水")
    assert len(results) == 2  # Q-2025-001 notes, Q-2025-004 paint_type+notes


def test_search_combined_filters(quotes):
    results = _search(quotes, building_type="住宅", brand="虹牌")
    assert len(results) == 2  # Q-2025-001, Q-2026-001


def test_search_no_results(quotes):
    results = _search(quotes, keyword="不存在的關鍵字")
    assert len(results) == 0


def test_search_no_filters_returns_all(quotes):
    results = _search(quotes)
    assert len(results) == 8


async def test_handler_returns_json():
    from chatpilot.tools.builtin.quote_search import create_quote_search_tool

    tool = create_quote_search_tool()
    result = await tool.handler({"arguments": {"building_type": "商辦"}})
    assert result["resultType"] == "success"
    data = json.loads(result["textResultForLlm"])
    assert len(data) == 2
    assert all(q["building_type"] == "商辦" for q in data)
