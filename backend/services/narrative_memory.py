# -*- coding: utf-8 -*-
"""Narrative memory service for long-form continuity."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from backend import persistence as db
from backend.common.utils import normalize_outlines
from backend.prompts.common.context import build_relevant_character_context


RECENT_MEMORY_WINDOW = 5
ARC_SIZE = 5
PREVIOUS_TAIL_LIMIT = 1200


def tail_text(text: Any, limit: int = PREVIOUS_TAIL_LIMIT) -> str:
    text = (text or "").strip()
    if limit is None or limit <= 0:
        return ""
    return text[-limit:] if len(text) > limit else text


def snippet_text(text: Any, head: int = 600, tail: int = 900) -> str:
    text = (text or "").strip()
    head = max(0, int(head or 0))
    tail = max(0, int(tail or 0))
    limit = head + tail
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if tail == 0:
        return text[:head]
    if head == 0:
        return text[-tail:]
    return text[:head] + "\n...(中略)...\n" + text[-tail:]


def split_generated_prose(text: Any):
    text = (text or "").strip()
    for marker in ("[START_OF_PROSE]", "[正文開始]"):
        idx = text.find(marker)
        if idx >= 0:
            return text[:idx].strip(), text[idx + len(marker):].strip()
    return "", text


def get_chapter_outline(novel_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
    plot_data = db.get_stitched_plot(novel_id)
    outlines = normalize_outlines(plot_data or {})
    target = int(chapter_index)
    return next((ch for ch in outlines if ch.get("chapter_index") == target), None)


def _stringify_event(event: Any) -> str:
    if isinstance(event, dict):
        parts = []
        for key in ("scene", "action", "consequence", "summary", "description", "event"):
            if event.get(key):
                parts.append(str(event.get(key)))
        return " / ".join(parts) if parts else json.dumps(event, ensure_ascii=False)
    return str(event)


def _outline_summary(outline: Optional[Dict[str, Any]]) -> str:
    if not isinstance(outline, dict):
        return ""
    for key in ("chapter_summary", "summary", "purpose", "goal"):
        if outline.get(key):
            return str(outline.get(key)).strip()
    events = outline.get("events") or outline.get("scenes") or []
    if isinstance(events, list):
        return "；".join(_stringify_event(event) for event in events[:4] if event)
    if events:
        return str(events)
    return ""


def _active_characters(outline: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    names = []
    if isinstance(outline, dict):
        names = outline.get("characters_active") or outline.get("characters") or []
    if isinstance(names, str):
        names = [names]
    result = []
    for name in names or []:
        clean = str(name).strip()
        if clean:
            result.append({"name": clean, "behavior": "", "state_change": ""})
    return result


def _item_id(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("seed_id", "id", "code", "name", "title", "seed"):
            if item.get(key):
                return str(item.get(key))
        return snippet_text(json.dumps(item, ensure_ascii=False), 80, 0)
    return snippet_text(str(item), 80, 0)


def _foreshadowing_progress(outline: Optional[Dict[str, Any]], chapter_index: int) -> List[Dict[str, Any]]:
    if not isinstance(outline, dict):
        return []
    tasks = outline.get("allocated_tasks") or {}
    if not isinstance(tasks, dict):
        return []
    progress = []
    for key, action, status in (
        ("foreshadowing_plants", "plant", "planted_in_written_chapter"),
        ("foreshadowing_payoffs", "payoff", "paid_off_in_written_chapter"),
        ("turning_points", "turning_point", "executed_in_written_chapter"),
    ):
        items = tasks.get(key) or []
        if not isinstance(items, list):
            items = [items]
        for item in items:
            progress.append({
                "seed_id": _item_id(item),
                "action": action,
                "status": status,
                "chapter_index": int(chapter_index),
                "source": item,
            })
    return progress


def build_chapter_memory_summary(
    novel_id: str,
    chapter_index: int,
    content: str,
    outline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    outline = outline if outline is not None else get_chapter_outline(novel_id, chapter_index)
    _, prose = split_generated_prose(content)
    title = ""
    if isinstance(outline, dict):
        title = outline.get("title") or outline.get("chapter_title") or ""
    outline_brief = _outline_summary(outline)
    prose_excerpt = snippet_text(prose, 520, 520)
    if outline_brief:
        chapter_summary = f"{title}：{outline_brief}" if title else outline_brief
    else:
        chapter_summary = prose_excerpt
    return {
        "chapter_index": int(chapter_index),
        "title": title or f"第 {chapter_index} 章",
        "chapter_summary": chapter_summary,
        "active_characters": _active_characters(outline),
        "foreshadowing_progress": _foreshadowing_progress(outline, chapter_index),
        "timeline_event": (outline or {}).get("time_setting", "") if isinstance(outline, dict) else "",
        "emotional_state": (outline or {}).get("emotional_state", "") if isinstance(outline, dict) else "",
        "outline_reference": outline or {},
        "prose_excerpt": prose_excerpt,
    }


def store_chapter_memory(
    novel_id: str,
    chapter_index: int,
    content: str,
    source_version: Optional[int] = None,
    outline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = build_chapter_memory_summary(novel_id, chapter_index, content, outline=outline)
    db.save_chapter_memory(novel_id, chapter_index, summary, source_version=source_version)
    rebuild_arc_summary_for_chapter(novel_id, chapter_index)
    return summary


def _memory_payload(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for row in rows or []:
        payload = row.get("summary_json") if isinstance(row, dict) else {}
        if isinstance(payload, dict):
            result.append(payload)
    return result


def rebuild_arc_summary_for_chapter(novel_id: str, chapter_index: int, arc_size: int = ARC_SIZE) -> Optional[Dict[str, Any]]:
    chapter_index = int(chapter_index)
    arc_start = ((chapter_index - 1) // arc_size) * arc_size + 1
    arc_end = arc_start + arc_size - 1
    memories = _memory_payload(db.get_chapter_memories(novel_id, arc_start, arc_end))
    if not memories:
        return None
    summary = {
        "arc_start": arc_start,
        "arc_end": arc_end,
        "chapter_count": len(memories),
        "arc_summary": " / ".join(
            str(memory.get("chapter_summary", "")).strip()
            for memory in memories
            if str(memory.get("chapter_summary", "")).strip()
        ),
        "character_arc_progress": _merge_character_progress(memories),
        "unresolved_foreshadowing": unresolved_foreshadowing_from_memories(memories),
        "timeline_anchor": [
            memory.get("timeline_event")
            for memory in memories
            if memory.get("timeline_event")
        ],
    }
    db.save_arc_summary(novel_id, arc_start, arc_end, summary)
    return summary


def _merge_character_progress(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {}
    for memory in memories:
        for item in memory.get("active_characters") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            seen[name] = {
                "name": name,
                "last_seen_chapter": memory.get("chapter_index"),
                "latest_state_change": item.get("state_change", ""),
            }
    return list(seen.values())


def unresolved_foreshadowing_from_memories(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    states = {}
    for memory in memories:
        for item in memory.get("foreshadowing_progress") or []:
            if not isinstance(item, dict):
                continue
            seed_id = str(item.get("seed_id", "")).strip()
            if not seed_id:
                continue
            action = item.get("action")
            if action == "payoff":
                states.pop(seed_id, None)
            elif action == "plant":
                states[seed_id] = item
    return list(states.values())


def build_writer_memory_context(novel_id: str, chapter_index: int, window: int = RECENT_MEMORY_WINDOW) -> Dict[str, Any]:
    target = int(chapter_index)
    recent = _memory_payload(db.get_chapter_memories(novel_id, max(1, target - window), target - 1))
    previous = db.get_latest_chapter(novel_id, target - 1) if target > 1 else None
    previous_tail = tail_text(previous.get("content", ""), PREVIOUS_TAIL_LIMIT) if previous else ""
    arc = db.get_arc_summary(novel_id, chapter_index=target - 1) if target > 1 else None
    historical = _memory_payload(db.get_chapter_memories(novel_id, 1, target - 1))
    return {
        "memory_policy": "寫作必須以章節記憶、前章正文尾段、當前 arc summary 與未回收伏筆為連續性依據；若與本章大綱衝突，優先回報上下文衝突。",
        "recent_chapter_memories": recent,
        "current_arc_summary": arc.get("summary_json") if arc else None,
        "previous_chapter_tail": previous_tail,
        "unresolved_foreshadowing": unresolved_foreshadowing_from_memories(historical),
    }


def build_editor_context_packet(novel_id: str, chapter_index: int, original_prose: str) -> Dict[str, Any]:
    outline = get_chapter_outline(novel_id, chapter_index)
    current_memory = db.get_chapter_memory(novel_id, chapter_index)
    recent_memory = build_writer_memory_context(novel_id, chapter_index, window=RECENT_MEMORY_WINDOW)
    char_data = db.get_latest_characters(novel_id)
    characters_source = char_data.get("parsed_data") if char_data and char_data.get("parsed_data") else {}
    query = json.dumps({
        "outline": outline or {},
        "memory": current_memory.get("summary_json") if current_memory else {},
        "edit_target_excerpt": snippet_text(original_prose, 500, 500),
    }, ensure_ascii=False)
    active_names = (outline or {}).get("characters_active") if isinstance(outline, dict) else None
    return {
        "chapter_outline": outline or {},
        "allocated_tasks": (outline or {}).get("allocated_tasks", {}) if isinstance(outline, dict) else {},
        "current_chapter_memory": current_memory.get("summary_json") if current_memory else None,
        "continuity_memory": recent_memory,
        "active_character_cards": build_relevant_character_context(
            characters_source,
            query_text=query,
            force_full_names=active_names,
        ),
        "editor_policy": "只允許改善文句、節奏、意象與局部銜接；不得改寫大綱事件、角色動機、伏筆鋪墊/回收狀態或既有連續性。",
    }


def memory_context_text(packet: Dict[str, Any]) -> str:
    return json.dumps(packet, ensure_ascii=False, indent=2)
