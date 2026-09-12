# -*- coding: utf-8 -*-
"""
Graphiti Cascade Module（模組化關聯）.

Single entry point for keeping chapter prose, the temporal graph and the
story-terms glossary in sync:

- clear_chapter_cascade(): 單章正文清除時連動清除該章衍生的圖譜物件與自動術語。
  所有清除路徑（手動存空正文 / reset-content / 刪章 / API）都應走這裡，
  而不是各自散寫 DELETE。
- clear_novel_derived(): 整批正文清除時清空全書圖譜與自動術語（手動術語保留）。

手動術語（source_chapter IS NULL）永遠不受章節清除影響，僅隨整本刪除
（FK CASCADE）或術語 API 手動刪除。
"""
from typing import Dict, Any
from backend import persistence as db


def clear_chapter_cascade(novel_id: str, chapter_index: int) -> Dict[str, Any]:
    """連動清除單章衍生物件，回傳各項筆數摘要。"""
    chapter_index = int(chapter_index)
    graph = db.delete_chapter_slice(novel_id, chapter_index)
    try:
        terms_deleted = db.delete_terms_by_chapter(novel_id, chapter_index)
    except Exception:
        terms_deleted = 0
    summary = {**graph, "auto_terms_deleted": terms_deleted}
    print(f"[Graphiti Cascade] novel={novel_id} chapter={chapter_index} cleared: {summary}")
    return summary


def clear_novel_derived(novel_id: str) -> Dict[str, Any]:
    """清空全書圖譜與自動術語（整批正文清除時使用，手動術語保留）。"""
    graph = db.clear_novel_graph(novel_id)
    try:
        terms_deleted = db.delete_auto_terms(novel_id)
    except Exception:
        terms_deleted = 0
    summary = {**graph, "auto_terms_deleted": terms_deleted}
    print(f"[Graphiti Cascade] novel={novel_id} derived data cleared: {summary}")
    return summary
