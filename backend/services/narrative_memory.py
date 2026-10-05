# -*- coding: utf-8 -*-
"""Narrative memory service for long-form continuity."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from backend import persistence as db
from backend.common.utils import normalize_outlines
from backend.prompts.common.context import build_relevant_character_context


RECENT_MEMORY_WINDOW = 5
ARC_SIZE = 5
LONG_RANGE_MEMORY_WINDOW = 50
CHARACTER_RECALL_WINDOW = 30
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
    state_changes = {}
    if isinstance(outline, dict):
        names = outline.get("characters_active") or outline.get("characters") or []
        raw_changes = outline.get("character_state_changes") or outline.get("relationship_changes") or []
        if isinstance(raw_changes, dict):
            state_changes = raw_changes
        elif isinstance(raw_changes, list):
            state_changes = {
                str(item.get("name") or item.get("character") or "").strip(): item
                for item in raw_changes if isinstance(item, dict)
            }
    if isinstance(names, str):
        names = [names]
    result = []
    for name in names or []:
        item = name if isinstance(name, dict) else {}
        clean = str(item.get("name") or item.get("character") or name).strip()
        if clean:
            change = state_changes.get(clean, {})
            if isinstance(change, str):
                change = {"state_change": change}
            if not isinstance(change, dict):
                change = {}
            state_change = (
                item.get("state_change") or item.get("emotional_change") or
                change.get("state_change") or change.get("emotional_change") or
                change.get("change") or ""
            )
            relationship_change = item.get("relationship_change") or change.get("relationship_change") or ""
            result.append({
                "name": clean,
                "behavior": str(item.get("behavior") or change.get("behavior") or ""),
                "state_change": str(state_change),
                "relationship_change": str(relationship_change),
            })
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
    chapter_summary = build_chapter_synopsis_from_prose(
        prose,
        fallback=(f"{title}：{outline_brief}" if title and outline_brief else title or outline_brief or prose_excerpt),
        limit=320,
    )
    return {
        "chapter_index": int(chapter_index),
        "title": title or f"第 {chapter_index} 章",
        "chapter_summary": chapter_summary,
        "active_characters": _active_characters(outline),
        "foreshadowing_progress": _foreshadowing_progress(outline, chapter_index),
        "timeline_event": (outline or {}).get("time_setting", "") if isinstance(outline, dict) else "",
        "emotional_state": (
            (outline or {}).get("emotional_requirement") or
            (outline or {}).get("emotional_state") or
            (outline or {}).get("emotional_tone") or ""
        ) if isinstance(outline, dict) else "",
        "relationship_changes": (outline or {}).get("relationship_changes", []) if isinstance(outline, dict) else [],
        "outline_reference": outline or {},
        "prose_excerpt": prose_excerpt,
    }


def build_chapter_synopsis_from_prose(content: str, fallback: str = "", limit: int = 320) -> str:
    """Create a deterministic synopsis from the saved prose, never from a stale outline.

    This extractive summary uses the opening and closing complete sentences so that
    a rewrite changing the chapter's direction cannot retain an obsolete outline synopsis.
    """
    _, prose = split_generated_prose(content or "")
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?])\s*|\n+", prose)
        if part and part.strip()
    ]
    if not sentences:
        return str(fallback or "").strip()
    selected = sentences[:2]
    if len(sentences) > 3:
        selected.append(sentences[-1])
    synopsis = "".join(selected)
    if len(synopsis) > limit:
        synopsis = synopsis[:limit].rsplit("。", 1)[0]
        if not synopsis:
            synopsis = "".join(selected)[:limit].rstrip()
    return synopsis or str(fallback or "").strip()


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
                "latest_relationship_change": item.get("relationship_change", ""),
            }
    return list(seen.values())


def get_overdue_character_recalls(
    novel_id: str,
    before_chapter: int,
    window: int = CHARACTER_RECALL_WINDOW,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return named characters absent for more than ``window`` chapters.

    Only characters recorded in prior chapter memories are eligible. This keeps
    characters that have never appeared out of the recall list.
    """
    target = int(before_chapter)
    threshold = max(1, int(window))
    if not novel_id or target <= threshold:
        return []

    memories = _memory_payload(db.get_chapter_memories(novel_id, 1, target - 1))
    progress = _merge_character_progress(memories)
    overdue = []
    for item in progress:
        last_seen = item.get("last_seen_chapter")
        if last_seen is None:
            continue
        try:
            chapters_since = target - int(last_seen)
        except (TypeError, ValueError):
            continue
        if chapters_since > threshold:
            overdue.append({
                **item,
                "chapters_since_last_seen": chapters_since,
            })
    overdue.sort(key=lambda item: (-int(item["chapters_since_last_seen"]), str(item.get("name", ""))))
    return overdue[:max(1, int(limit))]


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


def get_unresolved_foreshadowing(novel_id: str, before_chapter: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Return planted narrative seeds without a later allocated payoff, in story order."""
    if not novel_id or int(before_chapter) <= 1:
        return []
    memories = _memory_payload(db.get_chapter_memories(novel_id, 1, int(before_chapter) - 1))
    pending = unresolved_foreshadowing_from_memories(memories)
    return pending[-max(1, int(limit)):]


def build_writer_memory_context(novel_id: str, chapter_index: int, window: int = RECENT_MEMORY_WINDOW) -> Dict[str, Any]:
    target = int(chapter_index)
    recent = _memory_payload(db.get_chapter_memories(novel_id, max(1, target - window), target - 1))
    previous = db.get_latest_chapter(novel_id, target - 1) if target > 1 else None
    previous_tail = tail_text(previous.get("content", ""), PREVIOUS_TAIL_LIMIT) if previous else ""
    arc = db.get_arc_summary(novel_id, chapter_index=target - 1) if target > 1 else None
    retrospective_start = max(1, target - LONG_RANGE_MEMORY_WINDOW)
    retrospective_end = max(0, target - window - 1)
    long_range_memories = _memory_payload(
        db.get_chapter_memories(novel_id, retrospective_start, retrospective_end)
    ) if target > window + 1 else []
    try:
        chapter_rows = {
            int(row["chapter_index"]): row
            for row in db.get_chapters_latest_range(novel_id, retrospective_start, retrospective_end)
        } if retrospective_start <= retrospective_end else {}
    except Exception:
        chapter_rows = {}
    long_range_retrospective = []
    chapter_cache = dict(chapter_rows)
    for offset in range(0, len(long_range_memories), ARC_SIZE):
        group = long_range_memories[offset:offset + ARC_SIZE]
        beats = []
        for memory in group:
            chapter_idx = int(memory.get("chapter_index") or 0)
            chapter = chapter_cache.get(chapter_idx)
            if chapter is None and chapter_idx:
                chapter = db.get_latest_chapter(novel_id, chapter_idx)
                chapter_cache[chapter_idx] = chapter
            saved_prose = (chapter or {}).get("content") or ""
            summary = (
                build_chapter_synopsis_from_prose(saved_prose, fallback=memory.get("chapter_summary", ""), limit=180)
                if saved_prose else str(memory.get("chapter_summary") or "")
            )
            summary = re.sub(r"\s+", " ", summary).strip()
            if summary:
                beats.append(f"第{memory.get('chapter_index', '?')}章：{summary[:180]}")
        if beats:
            long_range_retrospective.append("；".join(beats))
    character_history = _build_character_history(novel_id, target, chapter_rows=chapter_cache)
    return {
        "memory_policy": "寫作必須以章節記憶、前章正文尾段、當前 arc summary 為連續性依據；伏筆僅處理本章大綱明確指派之任務。",
        "recent_chapter_memories": recent,
        "current_arc_summary": arc.get("summary_json") if arc else None,
        "long_range_arc_retrospective": long_range_retrospective,
        "character_emotional_and_relationship_history": character_history,
        "previous_chapter_tail": previous_tail,
    }


def _build_character_history(
    novel_id: str,
    target_chapter: int,
    max_chars: int = 7000,
    chapter_rows: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Recall first and latest recorded emotional/relationship moments for current cast."""
    outline = get_chapter_outline(novel_id, target_chapter) or {}
    active = _active_characters(outline)
    if not active:
        return []
    memories = _memory_payload(db.get_chapter_memories(novel_id, 1, target_chapter - 1))
    result = []
    used_chars = 0
    prose_cache = {}
    chapter_rows = chapter_rows or {}
    for character in active:
        name = character["name"]
        appearances = [
            memory for memory in memories
            if any(item.get("name") == name for item in (memory.get("active_characters") or []) if isinstance(item, dict))
        ]
        if not appearances:
            continue
        picked = [appearances[0]]
        if appearances[-1] is not appearances[0]:
            picked.append(appearances[-1])
        if len(appearances) > 2:
            picked.append(appearances[-2])
        moments = []
        for memory in picked:
            active_record = next(
                (item for item in (memory.get("active_characters") or []) if isinstance(item, dict) and item.get("name") == name),
                {},
            )
            summary = str(memory.get("chapter_summary") or "").strip()
            cache_key = (memory.get("chapter_index"), name)
            evidence = prose_cache.get(cache_key)
            if evidence is None:
                historical_idx = int(memory.get("chapter_index") or 0)
                historical_chapter = chapter_rows.get(historical_idx)
                if historical_chapter is None and historical_idx:
                    historical_chapter = db.get_latest_chapter(novel_id, historical_idx)
                historical_prose = (historical_chapter or {}).get("content") or ""
                evidence = _character_prose_evidence(historical_prose, name)
                prose_cache[cache_key] = evidence
            if not summary:
                summary = str(memory.get("prose_excerpt") or "").replace("\n...(中略)...\n", " … ").strip()[:180]
            event = {
                "chapter_index": memory.get("chapter_index"),
                "chapter_summary": summary[:180],
                "state_change": active_record.get("state_change", ""),
                "relationship_change": active_record.get("relationship_change", ""),
                "textual_evidence": evidence,
            }
            cost = len(json.dumps(event, ensure_ascii=False))
            if used_chars + cost > max_chars:
                break
            used_chars += cost
            moments.append(event)
        if moments:
            result.append({"character": name, "recorded_moments": moments})
        if used_chars >= max_chars:
            break
    return result


def _character_prose_evidence(prose: str, character_name: str, limit: int = 300) -> str:
    """Extract scene-local sentences about a character from the saved chapter prose."""
    if not prose or not character_name:
        return ""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?])\s*|\n+", prose)
        if sentence and sentence.strip()
    ]
    matched_indexes = [i for i, sentence in enumerate(sentences) if character_name in sentence]
    if not matched_indexes:
        return ""
    selected = []
    for idx in matched_indexes[:2]:
        for neighbor in (idx - 1, idx, idx + 1):
            if 0 <= neighbor < len(sentences) and neighbor not in selected:
                selected.append(neighbor)
    selected.sort()
    evidence = " ".join(sentences[i] for i in selected)
    return evidence[:limit].rstrip()


def build_editor_context_packet(novel_id: str, chapter_index: int, original_prose: str, fix_mode: bool = False) -> Dict[str, Any]:
    """
    Build lightweight, clean context for Editor according to CONTEXT_ARCHITECTURE_REVIEW.md Section 1.7:
    - Minimum required: scene goals / chapter function, previous chapter tail (800-1200 words), relevant terms, editor policy.
    - Strictly prohibited: truncated excerpts with ...(中略)..., 16KB historical memory dumps, full character bible dump.
    """
    outline = get_chapter_outline(novel_id, chapter_index)
    scene_goals = {}
    if isinstance(outline, dict):
        scene_goals = {
            "chapter_index": chapter_index,
            "chapter_title": outline.get("title") or outline.get("chapter_title") or f"第 {chapter_index} 章",
            "chapter_goal": outline.get("scene_goal") or outline.get("purpose") or outline.get("chapter_summary") or "",
            "scene_beats": outline.get("scene_beats") or outline.get("events") or [],
            "characters_active": outline.get("characters_active") or [],
        }

    # Fetch previous chapter tail (800-1200 characters) for continuity checking
    target = int(chapter_index)
    previous_tail = ""
    if target > 1:
        prev = db.get_latest_chapter(novel_id, target - 1)
        if prev and prev.get("content"):
            _, prev_prose = split_generated_prose(prev["content"])
            previous_tail = tail_text(prev_prose, limit=PREVIOUS_TAIL_LIMIT)

    # Scoped story terms relevant to this chapter
    terms_list = []
    try:
        all_terms = db.get_terms(novel_id)
        if all_terms:
            content_str = str(scene_goals) + " " + (original_prose[:1000] if original_prose else "")
            matched = [t for t in all_terms if t.get("term") and t["term"] in content_str]
            terms_list = matched[:15] if matched else all_terms[:5]
    except Exception:
        terms_list = []

    # Graphiti Temporal Graph Facts (動態世界線事實，避免潤色穿幫)
    temporal_facts = ""
    try:
        from backend.services.graphiti.temporal_graph import TemporalGraphService
        active_names = scene_goals.get("characters_active") or []
        temporal_facts = TemporalGraphService.build_narrative_context(
            novel_id=novel_id,
            at_chapter=chapter_index,
            active_characters=active_names,
            max_facts=12,
        )
    except Exception:
        temporal_facts = ""

    # Conflict Novelty Guard (長程衝突因果防重複指引)
    conflict_guard = ""
    try:
        from backend.services.narrative.conflict_ledger import ConflictLedger
        conflict_guard = ConflictLedger.build_anti_repetition_prompt_snippet(novel_id, chapter_index)
    except Exception:
        conflict_guard = ""

    # Setting Boundaries & Mechanism (設定運作機制與代價邊界約束)
    setting_block = ""
    try:
        from backend.services.narrative.setting_registry import SettingRegistry
        setting_names = outline.get("setting_usage", []) if isinstance(outline, dict) else []
        setting_block = SettingRegistry.get_scoped_context_for_writer(novel_id, setting_names)
    except Exception:
        setting_block = ""

    return {
        "chapter_index": chapter_index,
        "scene_goals": scene_goals,
        "previous_chapter_tail": previous_tail,
        "character_emotional_and_relationship_history": _build_character_history(novel_id, target),
        "story_terms": [
            {"term": t.get("term"), "definition": t.get("definition"), "notes": t.get("notes", "")}
            for t in terms_list
        ],
        "editor_policy": (
            "修正方針：允許重寫被標記段落之因果、策略、微動作與代價，徹底打破套路；未標記段落與大綱主旨事件保留。"
            if fix_mode else
            "潤色方針：以修辭優化、節奏微調、對白生動與文學美感提升為主；嚴格保留本章既有情節走向、人物生死與客觀事實，不隨意刪除核心事件。"
        ),
        "temporal_graph_facts": temporal_facts,
        "conflict_novelty_guard": conflict_guard,
        "setting_boundaries": setting_block,
    }


def memory_context_text(packet: Dict[str, Any]) -> str:
    return json.dumps(packet, ensure_ascii=False, indent=2)
