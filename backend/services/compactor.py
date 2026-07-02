# -*- coding: utf-8 -*-
"""
內容縮減演算法 - 將大型 context 分層級壓縮以適應 LLM token 限制
"""

import json
from typing import Any, Dict, List, Optional


TARGET_TOKENS_DEFAULT = 16000


def compact_json(data: Any, max_keys: int = 8, max_list_items: int = 5) -> Any:
    """遞迴縮減 JSON/dict 結構"""
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
        return {k: compact_json(data[k], max_keys // 2, max_list_items) for k in selected}
    if isinstance(data, list):
        return [
            compact_json(item, max_keys // 2, max_list_items // 2)
            for item in data[:max_list_items]
        ]
    if isinstance(data, str) and len(data) > 600:
        return data[:300] + f"\n...省略 {len(data) - 600} 字...\n" + data[-300:]
    return data


def compact_skeleton(chapters_outline: List[Dict], max_chapters: int = 8) -> List[Dict]:
    """縮減章節骨架 (保留摘要)"""
    compacted = []
    for ch in (chapters_outline or [])[:max_chapters]:
        compacted.append({
            "chapter_index": ch.get("chapter_index"),
            "chapter_title": ch.get("chapter_title", "")[:40],
            "chapter_summary": (ch.get("chapter_summary", "") or "")[:150],
        })
    return compacted


def compact_character_bible(characters_data: Any, max_chars: int = 12) -> Any:
    """提取角色聖經核心欄位"""
    parsed = json.loads(characters_data) if isinstance(characters_data, str) else characters_data
    if isinstance(parsed, dict) and "characters" in parsed:
        chars = parsed["characters"][:max_chars]
        compacted_chars = []
        for ch in chars:
            compacted_chars.append({
                "name": ch.get("name"),
                "role": ch.get("role"),
                "want": (ch.get("want", "") or "")[:80],
                "need": (ch.get("need", "") or "")[:80],
                "fatal_flaw": (ch.get("fatal_flaw", "") or "")[:60],
                "arc": (ch.get("arc", "") or "")[:60],
            })
        return {"characters": compacted_chars}
    return parsed


def estimate_token_count(text: str) -> int:
    """估算 token 數量 (簡易法: 字元數 * 0.75 中文 / 0.3 英文)"""
    if not text:
        return 0
    return max(1, int(len(text) * 0.75))
