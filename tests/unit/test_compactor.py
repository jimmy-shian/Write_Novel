# -*- coding: utf-8 -*-
"""
backend.services.compactor 單元測試：
- compact_json：遞迴收合、優先鍵保留、收合標記
- compact_skeleton / compact_character_bible
- estimate_token_count
"""
from backend.services.compactor import (
    compact_json,
    compact_skeleton,
    compact_character_bible,
    estimate_token_count,
)


def test_compact_json_collapses_long_lists_with_marker():
    data = {"items": [f"item_{i}" for i in range(20)]}
    out = compact_json(data, max_list_items=5)
    assert len(out["items"]) == 6  # 5 筆 + 1 收合標記
    marker = out["items"][-1]
    assert marker["director_payload_view"] == "collapsed_json"
    assert marker["collapsed_kind"] == "list_items"
    assert marker["total_count"] == 20


def test_compact_json_collapses_long_text():
    data = {"worldview": "長" * 1000}
    out = compact_json(data)
    marker = out["worldview"]
    assert marker["collapsed_kind"] == "text"
    assert marker["char_count"] == 1000


def test_compact_json_priority_keys_kept_and_omitted_recorded():
    data = {f"key_{i}": i for i in range(20)}
    data["theme"] = "主題"
    out = compact_json(data, max_keys=5)
    assert out["theme"] == "主題"
    assert "_collapsed_keys" in out
    assert "theme" not in out["_collapsed_keys"]["omitted_keys"]


def test_compact_skeleton():
    chapters = [
        {"chapter_index": i, "chapter_title": f"第{i}章", "chapter_summary": f"摘要{i}", "extra": "x"}
        for i in range(1, 13)
    ]
    out = compact_skeleton(chapters, max_chapters=8)
    assert len(out) == 9  # 8 章 + 1 收合標記
    assert out[0]["chapter_index"] == 1
    assert "extra" not in out[0]
    marker = out[-1]
    assert marker["collapsed_kind"] == "chapters_outline"
    assert marker["total_count"] == 12


def test_compact_character_bible():
    chars = {
        "characters": [
            {"name": f"角色{i}", "role": "配角", "want": "目標", "secret_extra": "x"}
            for i in range(15)
        ]
    }
    out = compact_character_bible(chars, max_chars=12)
    assert len(out["characters"]) == 13  # 12 位 + 1 收合標記
    assert "secret_extra" not in out["characters"][0]
    marker = out["characters"][-1]
    assert marker["collapsed_kind"] == "characters"
    # 非標準結構原樣通過
    assert compact_character_bible({"other": 1}) == {"other": 1}


def test_estimate_token_count():
    assert estimate_token_count("") == 0
    assert estimate_token_count(None) == 0
    assert estimate_token_count("abcd") == 3  # 4 * 0.75 = 3