# -*- coding: utf-8 -*-
"""
內容縮減演算法 - 將大型 context 分層級壓縮以適應 LLM token 限制
"""

import json
from typing import Any, Dict, List, Optional


TARGET_TOKENS_DEFAULT = 16000


def _collapsed_marker(kind: str, *, total_count: int = None, char_count: int = None, path: str = "") -> Dict[str, Any]:
    marker = {
        "director_payload_view": "collapsed_json",
        "collapsed_kind": kind,
        "path": path or "$",
        "message": "此處以 JSON metadata 收合；不得把本視圖當完整內容審查，需由總監指定位置展開。",
    }
    if total_count is not None:
        marker["total_count"] = total_count
    if char_count is not None:
        marker["char_count"] = char_count
    return marker


def compact_json(data: Any, max_keys: int = 8, max_list_items: int = 5, path: str = "") -> Any:
    """遞迴收合 JSON/dict 結構，保留可展開 metadata，不輸出片段摘要。"""
    if isinstance(data, dict):
        priority_keys = [
            "theme", "main_conflict", "worldview", "macro_outline",
            "title", "summary", "chapter_index", "chapter_title",
            "volume_index", "name", "role", "motivation", "arc",
        ]
        keys = list(data.keys())
        priority_set = [k for k in priority_keys if k in keys]
        remaining = [k for k in keys if k not in priority_set]
        selected = priority_set[:max_keys]
        selected += remaining[:max_keys - len(selected)]
        result = {k: compact_json(data[k], max(1, max_keys // 2), max(1, max_list_items), f"{path}.{k}" if path else k) for k in selected}
        omitted = [k for k in keys if k not in selected]
        if omitted:
            result["_collapsed_keys"] = _collapsed_marker("object_keys", total_count=len(keys), path=path)
            result["_collapsed_keys"]["omitted_keys"] = omitted
        return result
    if isinstance(data, list):
        shown = [
            compact_json(item, max(1, max_keys // 2), max(1, max_list_items // 2), f"{path}[{idx}]")
            for idx, item in enumerate(data[:max_list_items])
        ]
        if len(data) > max_list_items:
            shown.append(_collapsed_marker("list_items", total_count=len(data), path=path))
        return shown
    if isinstance(data, str) and len(data) > 600:
        return _collapsed_marker("text", char_count=len(data), path=path)
    return data


def compact_skeleton(chapters_outline: List[Dict], max_chapters: int = 8) -> List[Dict]:
    """收合章節骨架，保留索引並以 metadata 標示可展開。"""
    compacted = []
    chapters = chapters_outline or []
    for ch in chapters[:max_chapters]:
        compacted.append({
            "chapter_index": ch.get("chapter_index"),
            "chapter_title": ch.get("chapter_title", ""),
            "chapter_summary": ch.get("chapter_summary", "") or "",
        })
    if len(chapters) > max_chapters:
        compacted.append(_collapsed_marker("chapters_outline", total_count=len(chapters), path="chapters_outline"))
    return compacted


def compact_character_bible(characters_data: Any, max_chars: int = 12) -> Any:
    """提取角色聖經核心欄位"""
    parsed = json.loads(characters_data) if isinstance(characters_data, str) else characters_data
    if isinstance(parsed, dict) and "characters" in parsed:
        chars = parsed["characters"]
        compacted_chars = []
        for ch in chars[:max_chars]:
            compacted_chars.append({
                "name": ch.get("name"),
                "role": ch.get("role"),
                "want": ch.get("want", "") or "",
                "need": ch.get("need", "") or "",
                "fatal_flaw": ch.get("fatal_flaw", "") or "",
                "arc": ch.get("arc", "") or "",
            })
        if len(chars) > max_chars:
            compacted_chars.append(_collapsed_marker("characters", total_count=len(chars), path="characters"))
        return {"characters": compacted_chars}
    return parsed


def estimate_token_count(text: str) -> int:
    """估算 token 數量 (簡易法: 字元數 * 0.75 中文 / 0.3 英文)"""
    if not text:
        return 0
    return max(1, int(len(text) * 0.75))
