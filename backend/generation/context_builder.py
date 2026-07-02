"""Backend context selection for generation tasks."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend import db
from backend.services.diagnostics import detect_current_stage
from backend.prompts.prompt_builder import (
    compact_json_data,
    extract_character_basic,
    extract_character_names_list,
    extract_worldview_summary,
)

from .task_schema import GenerationTaskRequest


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _summarize_volumes(volumes: List[Dict[str, Any]]) -> Dict[str, Any]:
    chapter_total = 0
    compacted = []
    for vol in volumes or []:
        if not isinstance(vol, dict):
            continue
        item = {
            "volume_index": vol.get("volume_index"),
            "title": vol.get("title", ""),
            "chapter_count": vol.get("chapter_count", 0),
            "has_outline": bool(vol.get("chapters_outline")),
        }
        try:
            chapter_total += int(vol.get("chapter_count", 0) or 0)
        except Exception:
            pass
        compacted.append(item)
    return {
        "volume_count": len(compacted),
        "chapter_count": chapter_total,
        "volumes": compacted,
    }


def _compact_character_card(char: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(char, dict):
        return {}
    selected = {}
    for key in ("name", "role", "entry_phase", "personality", "want", "need", "arc", "relationships", "relationship_matrix"):
        if key in char and char[key] not in (None, "", [], {}):
            selected[key] = char[key]
    return selected


def _get_current_outline_window(plot_data: Dict[str, Any], chapter_index: Optional[int]) -> Dict[str, Any]:
    chapters = plot_data.get("chapters", []) if isinstance(plot_data, dict) else []
    if not isinstance(chapters, list) or not chapter_index:
        return {}
    current = None
    previous = None
    nxt = None
    for idx, chapter in enumerate(chapters):
        try:
            ch_idx = int(chapter.get("chapter_index"))
        except Exception:
            continue
        if ch_idx == chapter_index:
            current = chapter
            if idx > 0:
                previous = chapters[idx - 1]
            if idx + 1 < len(chapters):
                nxt = chapters[idx + 1]
            break
    return {
        "previous_outline": previous,
        "current_outline": current,
        "next_outline": nxt,
    }


def _build_worldview_bundle(task: GenerationTaskRequest, worldview_text: str) -> Dict[str, Any]:
    mode = task.context_mode
    if not worldview_text:
        return {"mode": mode, "data": "尚無世界觀設定"}

    parsed_worldview = db.parse_worldview_to_json(worldview_text) if isinstance(worldview_text, str) else worldview_text

    if mode == "full":
        return {
            "mode": mode,
            "data": parsed_worldview,
        }
    if mode == "minimal":
        return {
            "mode": mode,
            "data": extract_worldview_summary(worldview_text),
        }
    compact_worldview = {}
    if isinstance(parsed_worldview, dict):
        for key in ("theme", "main_conflict", "worldview", "macro_outline"):
            if key in parsed_worldview and parsed_worldview[key] not in (None, "", [], {}):
                compact_worldview[key] = parsed_worldview[key]
    else:
        compact_worldview = parsed_worldview
    return {
        "mode": mode,
        "data": compact_json_data(compact_worldview, max_list_items=5),
    }


def _build_character_bundle(task: GenerationTaskRequest, characters_data: Any) -> Dict[str, Any]:
    mode = task.context_mode
    if not characters_data:
        return {"mode": mode, "data": "尚無角色設定"}

    if mode == "full":
        if isinstance(characters_data, dict) and "parsed_data" in characters_data:
            return {"mode": mode, "data": characters_data["parsed_data"]}
        return {"mode": mode, "data": characters_data}

    if mode == "minimal":
        names_source = characters_data.get("parsed_data") if isinstance(characters_data, dict) else characters_data
        names = extract_character_names_list(names_source)
        return {
            "mode": mode,
            "data": {
                "character_count": len(names),
                "character_names": names,
            },
        }

    compact_source = characters_data.get("parsed_data") if isinstance(characters_data, dict) else characters_data
    compact_cards = extract_character_basic(compact_source)
    if isinstance(compact_cards, dict) and isinstance(compact_cards.get("characters"), list):
        compact_cards["characters"] = [_compact_character_card(char) for char in compact_cards["characters"]]
    return {"mode": mode, "data": compact_cards}


def _build_plot_bundle(task: GenerationTaskRequest, volumes: List[Dict[str, Any]], plot_data: Dict[str, Any]) -> Dict[str, Any]:
    mode = task.context_mode
    chapter_index = task.target.chapter_index
    volume_index = task.target.volume_index
    if mode == "full":
        return {
            "mode": mode,
            "data": {
                "plot": plot_data,
                "volumes": volumes,
            },
        }

    if mode == "minimal":
        summary = _summarize_volumes(volumes)
        summary["backend_stage"] = detect_current_stage(task.novel_id)
        summary["target"] = {
            "volume_index": volume_index,
            "chapter_index": chapter_index,
            "section_index": task.target.section_index,
        }
        summary["window"] = _get_current_outline_window(plot_data, chapter_index)
        return {"mode": mode, "data": summary}

    bundle = {
        "volumes": _summarize_volumes(volumes),
        "window": _get_current_outline_window(plot_data, chapter_index),
    }
    return {"mode": mode, "data": bundle}


def build_generation_context(task: GenerationTaskRequest) -> Dict[str, Any]:
    """Build backend-side context for the unified generation-task API."""
    wb = db.get_latest_worldbuilding(task.novel_id)
    char_data = db.get_latest_characters(task.novel_id)
    plot_data = db.get_stitched_plot(task.novel_id) or {"chapters": []}
    volumes = db.get_volumes(task.novel_id) or []

    worldview_text = wb["content"] if wb else ""
    characters_source = char_data if char_data else None
    backend_stage = detect_current_stage(task.novel_id)
    frontend_state = task.frontend_state.model_dump() if hasattr(task.frontend_state, "model_dump") else task.frontend_state.dict()
    target_reference = task.target.model_dump() if hasattr(task.target, "model_dump") else task.target.dict()

    return {
        "novel_id": task.novel_id,
        "task_id": task.task_id,
        "task_type": task.task_type,
        "stage": task.stage,
        "scope": task.scope,
        "context_mode": task.context_mode,
        "backend_stage": backend_stage,
        "instruction": task.instruction or task.user_prompt or "",
        "frontend_state_reference": frontend_state,
        "target_reference": target_reference,
        "worldview": _build_worldview_bundle(task, worldview_text),
        "characters": _build_character_bundle(task, characters_source),
        "plot": _build_plot_bundle(task, volumes, plot_data),
    }
