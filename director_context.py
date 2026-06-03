# -*- coding: utf-8 -*-
"""Context packers used by the Director review stage.

This module keeps review-only data shaping out of agents.py so the pipeline
runner stays focused on routing and streaming.
"""

import json

import db


def split_generated_prose(text):
    """Return (thinking, prose) for writer output that uses a prose marker."""
    if not text:
        return "", ""
    for marker in ("[START_OF_PROSE]", "[正文開始]"):
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].strip(), text[idx + len(marker):].strip()
    return "", text.strip()


def _normalize_outlines(plot_data):
    chapters = plot_data.get("chapters", []) if isinstance(plot_data, dict) else []
    normalized = []
    for idx, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        item = dict(chapter)
        try:
            raw_idx = item.get("chapter_index") or item.get("chapter") or item.get("chapter_number") or item.get("index") or (idx + 1)
            item["chapter_index"] = int(raw_idx)
        except Exception:
            item["chapter_index"] = idx + 1
        normalized.append(item)
    normalized.sort(key=lambda item: item["chapter_index"])
    return normalized


def _chapter_versions(novel_id, chapter_index, limit=2):
    conn = db.get_db_connection()
    rows = conn.execute(
        "SELECT * FROM chapters WHERE novel_id = ? AND chapter_index = ? ORDER BY version DESC LIMIT ?",
        (novel_id, chapter_index, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _snippet(text, head=600, tail=900):
    text = (text or "").strip()
    if len(text) <= head + tail + 80:
        return text
    if tail <= 0:
        return text[:head] + "\n...（後文省略）"
    return text[:head] + "\n...（中段省略，保留首尾供連貫性評估）...\n" + text[-tail:]


def _tail(text, limit=1200):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _filter_active_characters(characters_text, outline):
    active_names = []
    if isinstance(outline, dict):
        active_names = outline.get("characters_active", []) or outline.get("characters", [])
    if isinstance(active_names, str):
        active_names = [active_names]
    active_names = [str(name).strip() for name in active_names if str(name).strip()]

    try:
        parsed = json.loads(characters_text) if isinstance(characters_text, str) else characters_text
    except Exception:
        return characters_text

    chars = parsed.get("characters", []) if isinstance(parsed, dict) else []
    if not chars:
        return parsed
    if not active_names:
        return {"characters": chars[:8], "selection_basis": "no_active_character_hint_limited_to_first_8"}

    selected = []
    for char in chars:
        name = str(char.get("name", "")).strip()
        if name and any(name in active or active in name for active in active_names):
            selected.append(char)

    return {"characters": selected or chars[:8], "selection_basis": active_names}


def build_writer_review_context(novel_id, chapter_index, characters_text):
    plot_data = db.get_stitched_plot(novel_id)
    outlines = _normalize_outlines(plot_data or {})
    target_idx = int(chapter_index or 1)

    current_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx), None)
    previous_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx - 1), None)
    next_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx + 1), None)

    current_chapter = db.get_latest_chapter(novel_id, target_idx)
    previous_chapter = db.get_latest_chapter(novel_id, target_idx - 1) if target_idx > 1 else None
    next_written_chapter = db.get_latest_chapter(novel_id, target_idx + 1)

    prose = current_chapter.get("content", "") if current_chapter else "（無寫作正文內容）"
    _, prose = split_generated_prose(prose)

    vols = db.get_volumes(novel_id)
    curr_vol_idx = db.get_chapter_volume_index(vols, target_idx) if vols else None
    curr_vol = next((v for v in vols if int(v.get("volume_index", 0)) == int(curr_vol_idx or 0)), None)

    packet = {
        "review_scope": "writer_chapter_continuity_and_outline_compliance",
        "chapter_index": target_idx,
        "current_volume": {
            "volume_index": curr_vol_idx,
            "title": curr_vol.get("title") if curr_vol else None,
            "summary": curr_vol.get("summary") if curr_vol else None,
        },
        "previous_chapter": {
            "outline": previous_outline,
            "tail": _tail(previous_chapter.get("content", ""), 1200) if previous_chapter else None,
        },
        "current_chapter": {
            "outline": current_outline or "（尚未生成章節大綱）",
            "allocated_tasks_and_clues": current_outline.get("allocated_tasks", {}) if isinstance(current_outline, dict) else {},
            "prose_text": prose,
        },
        "next_chapter_reference": {
            "outline": next_outline,
            "existing_prose_head": _snippet(next_written_chapter.get("content", ""), 900, 0) if next_written_chapter else None,
        },
        "active_character_cards": _filter_active_characters(characters_text, current_outline or {}),
    }
    return json.dumps(packet, ensure_ascii=False, indent=2), prose


def build_editor_review_context(novel_id, chapter_index, characters_text):
    target_idx = int(chapter_index or 1)
    versions = _chapter_versions(novel_id, target_idx, limit=2)
    latest = versions[0] if versions else {}
    previous = versions[1] if len(versions) > 1 else {}

    plot_data = db.get_stitched_plot(novel_id)
    outlines = _normalize_outlines(plot_data or {})
    current_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx), None)

    polished = latest.get("content", "（無潤色後正文）")
    original = previous.get("content") or "（沒有可比較的上一版正文，請只做保守品質檢查）"
    _, polished = split_generated_prose(polished)
    _, original = split_generated_prose(original)

    packet = {
        "review_scope": "editor_before_after_comparison",
        "chapter_index": target_idx,
        "chapter_outline": current_outline or "（尚未生成章節大綱）",
        "active_character_cards": _filter_active_characters(characters_text, current_outline or {}),
        "original_prose_before_edit": _snippet(original, 1200, 1600),
        "polished_prose_after_edit": polished,
        "comparison_required": True,
    }
    return json.dumps(packet, ensure_ascii=False, indent=2), polished
