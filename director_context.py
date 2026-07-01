# -*- coding: utf-8 -*-
"""Context packers used by the Director review stage.

This module keeps review-only data shaping out of agents.py so the pipeline
runner stays focused on routing and streaming.
"""

import json

import db
from utils import normalize_outlines


def build_director_conversation_context(novel_id, limit=1):
    """Return the latest chat memory slice used by Director decisions."""
    memory = db.get_chat_memory(novel_id, limit=max(limit * 8, 8))
    if not memory:
        return ""

    role_labels = {
        "user": "作者",
        "assistant": "協作總監",
        "director": "流程總監",
    }
    lines = []
    for item in memory:
        if item.get("role") == "director" or item.get("message_type") in ("director", "pipeline"):
            continue
        role = role_labels.get(item.get("role"), item.get("role", "未知"))
        content = (item.get("content") or "").strip()
        thinking = (item.get("thinking") or "").strip()
        if content:
            lines.append(f"[{role}] {content}")
        if thinking:
            lines.append(f"[{role}思考摘錄] {thinking[:400]}")
        if len(lines) >= limit:
            break
    return "\n\n".join(lines)


def build_director_context_block(conversation_context=None, summary_context=None, extra_context=None):
    """Compose optional Director input sections in one backend-owned place."""
    sections = []
    if conversation_context and str(conversation_context).strip():
        sections.append(f"【最近對話內容（僅前 1 則）】\n{str(conversation_context).strip()}")
    if summary_context and str(summary_context).strip():
        sections.append(f"【本輪精簡結果】\n{str(summary_context).strip()}")
    if extra_context and str(extra_context).strip():
        sections.append(f"【補充上下文 / 指定素材】\n{str(extra_context).strip()}")
    return "\n\n".join(sections)


def _allocated_foreshadowing_status(allocated_tasks):
    if not isinstance(allocated_tasks, dict):
        allocated_tasks = {}

    plants = allocated_tasks.get("foreshadowing_plants") or []
    payoffs = allocated_tasks.get("foreshadowing_payoffs") or []
    turns = allocated_tasks.get("turning_points") or []
    return {
        "source_of_truth": "current_chapter.outline.allocated_tasks",
        "worldview_seed_act_metadata_is_reference_only": True,
        "director_rule": "Only require foreshadowing in this chapter when allocated_tasks explicitly assigns plants, payoffs, or turning_points. Do not infer a chapter obligation from worldview seed act/stage metadata.",
        "has_required_foreshadowing_task": bool(plants or payoffs or turns),
        "plants_count": len(plants) if isinstance(plants, list) else 1,
        "payoffs_count": len(payoffs) if isinstance(payoffs, list) else 1,
        "turning_points_count": len(turns) if isinstance(turns, list) else 1,
    }


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _seed_label(seed, idx):
    if isinstance(seed, dict):
        for key in ("name", "title", "summary", "description", "content", "seed"):
            value = seed.get(key)
            if value:
                return str(value)
        return json.dumps(seed, ensure_ascii=False)
    return str(seed)


def _chapter_volume_index(volumes, chapter_index):
    try:
        return db.get_chapter_volume_index(volumes, int(chapter_index))
    except Exception:
        return None


def _chapters_for_volume(volumes, volume_index):
    if volume_index is None:
        return None
    try:
        start_ch, end_ch = db.get_volume_chapter_range(volumes, int(volume_index))
        return {"start_chapter": start_ch, "end_chapter": end_ch}
    except Exception:
        return None


def build_foreshadowing_allocation_context(novel_id, scope="all", volume_index=None, chapter_index=None, window=3):
    """Return the deterministic foreshadowing/turning allocation table used by Director reviews."""
    volumes = db.get_volumes(novel_id)
    wb = db.get_latest_worldbuilding(novel_id)
    worldview = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    seeds = _as_list(worldview.get("foreshadowing_seeds"))
    turns = _as_list(worldview.get("key_turning_points"))
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)

    seed_allocations = blueprint.get("foreshadowing_allocations", []) or []
    turn_allocations = blueprint.get("turning_allocations", []) or []

    target_volume = int(volume_index) if volume_index is not None else None
    target_chapter = int(chapter_index) if chapter_index is not None else None
    chapter_min = chapter_max = None
    if scope == "chapter" and target_chapter is not None:
        chapter_min = max(1, target_chapter - int(window or 0))
        chapter_max = target_chapter + int(window or 0)
    elif target_volume is not None:
        vol_range = _chapters_for_volume(volumes, target_volume)
        if vol_range:
            chapter_min = vol_range["start_chapter"]
            chapter_max = vol_range["end_chapter"]

    def in_scope(*chapters):
        if chapter_min is None or chapter_max is None:
            return True
        for chapter in chapters:
            try:
                ch = int(chapter)
            except Exception:
                continue
            if chapter_min <= ch <= chapter_max:
                return True
        return False

    foreshadowing_rows = []
    for idx, seed in enumerate(seeds):
        if idx >= len(seed_allocations):
            continue
        try:
            plant_ch, payoff_ch = seed_allocations[idx]
        except Exception:
            continue
        if not in_scope(plant_ch, payoff_ch):
            continue
        foreshadowing_rows.append({
            "seed_id": f"Seed-{idx + 1}",
            "seed": _seed_label(seed, idx),
            "plant_chapter": int(plant_ch),
            "plant_volume": _chapter_volume_index(volumes, plant_ch),
            "payoff_chapter": int(payoff_ch),
            "payoff_volume": _chapter_volume_index(volumes, payoff_ch),
            "review_rule": "Only require this seed in a chapter when that chapter is plant_chapter or payoff_chapter, or when the chapter outline allocated_tasks explicitly includes it.",
        })

    turning_rows = []
    for idx, turn in enumerate(turns):
        if idx >= len(turn_allocations):
            continue
        try:
            turn_ch = int(turn_allocations[idx])
        except Exception:
            continue
        if not in_scope(turn_ch):
            continue
        turning_rows.append({
            "turn_id": f"Turn-{idx + 1}",
            "turn": _seed_label(turn, idx),
            "chapter": turn_ch,
            "volume": _chapter_volume_index(volumes, turn_ch),
            "review_rule": "Only require this turning point in its assigned chapter, or when the chapter outline allocated_tasks explicitly includes it.",
        })

    if scope == "summary":
        vol_stats = {}
        for idx, seed in enumerate(seeds):
            if idx >= len(seed_allocations):
                continue
            try:
                plant_ch, payoff_ch = seed_allocations[idx]
            except Exception:
                continue
            p_vol = _chapter_volume_index(volumes, plant_ch)
            r_vol = _chapter_volume_index(volumes, payoff_ch)
            if p_vol is not None:
                vol_stats.setdefault(p_vol, {"plants": 0, "payoffs": 0, "turns": 0})
                vol_stats[p_vol]["plants"] += 1
            if r_vol is not None:
                vol_stats.setdefault(r_vol, {"plants": 0, "payoffs": 0, "turns": 0})
                vol_stats[r_vol]["payoffs"] += 1
        for idx, turn in enumerate(turns):
            if idx >= len(turn_allocations):
                continue
            try:
                turn_ch = int(turn_allocations[idx])
            except Exception:
                continue
            t_vol = _chapter_volume_index(volumes, turn_ch)
            if t_vol is not None:
                vol_stats.setdefault(t_vol, {"plants": 0, "payoffs": 0, "turns": 0})
                vol_stats[t_vol]["turns"] += 1
        summary_rows = []
        for v in sorted(vol_stats.keys()):
            summary_rows.append({"volume_index": v, **vol_stats[v]})
        return {
            "source_of_truth": "Python deterministic foreshadowing_blueprint plus chapter outline allocated_tasks",
            "scope": "summary",
            "total_seeds": len(seeds),
            "total_turns": len(turns),
            "total_chapters": blueprint.get("T"),
            "director_review_rules": [
                "This is a summary view. Full detail is available via scope=all or scope=volume.",
                "Worldview seed act/stage/chapter/volume metadata is draft reference only, never a hard obligation.",
            ],
            "per_volume_summary": summary_rows,
        }

    packet = {
        "source_of_truth": "Python deterministic foreshadowing_blueprint plus chapter outline allocated_tasks",
        "scope": scope,
        "target_volume_index": target_volume,
        "target_chapter_index": target_chapter,
        "chapter_scope": {"start_chapter": chapter_min, "end_chapter": chapter_max} if chapter_min is not None else "all",
        "total_chapters": blueprint.get("T"),
        "director_review_rules": [
            "Worldview seed act/stage/chapter/volume metadata is draft reference only, never a hard obligation.",
            "Do not invent new foreshadowing or turning-point obligations during review.",
            "For volume_skeleton review, verify assigned rows appear in the matching chapter allocated_tasks.",
            "For writer/editor review, judge only the current chapter's allocated_tasks plus nearby assigned rows for continuity.",
        ],
        "foreshadowing_allocation_table": foreshadowing_rows,
        "turning_point_allocation_table": turning_rows,
    }
    return packet


def split_generated_prose(text):
    """Return (thinking, prose) for writer output that uses a prose marker."""
    if not text:
        return "", ""
    for marker in ("[START_OF_PROSE]", "[正文開始]"):
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].strip(), text[idx + len(marker):].strip()
    return "", text.strip()


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
    outlines = normalize_outlines(plot_data or {})
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

    allocated_tasks = current_outline.get("allocated_tasks", {}) if isinstance(current_outline, dict) else {}

    packet = {
        "review_scope": "writer_chapter_continuity_and_outline_compliance",
        "chapter_index": target_idx,
        "foreshadowing_turning_allocation_context": build_foreshadowing_allocation_context(
            novel_id,
            scope="chapter",
            chapter_index=target_idx,
            window=3,
        ),
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
            "allocated_tasks_and_clues": allocated_tasks,
            "foreshadowing_review_policy": _allocated_foreshadowing_status(allocated_tasks),
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
    outlines = normalize_outlines(plot_data or {})
    current_outline = next((ch for ch in outlines if ch["chapter_index"] == target_idx), None)

    polished = latest.get("content", "（無潤色後正文）")
    original = previous.get("content") or "（沒有可比較的上一版正文，請只做保守品質檢查）"
    _, polished = split_generated_prose(polished)
    _, original = split_generated_prose(original)

    packet = {
        "review_scope": "editor_before_after_comparison",
        "chapter_index": target_idx,
        "foreshadowing_turning_allocation_context": build_foreshadowing_allocation_context(
            novel_id,
            scope="chapter",
            chapter_index=target_idx,
            window=3,
        ),
        "chapter_outline": current_outline or "（尚未生成章節大綱）",
        "allocated_tasks_and_clues": current_outline.get("allocated_tasks", {}) if isinstance(current_outline, dict) else {},
        "foreshadowing_review_policy": _allocated_foreshadowing_status(
            current_outline.get("allocated_tasks", {}) if isinstance(current_outline, dict) else {}
        ),
        "active_character_cards": _filter_active_characters(characters_text, current_outline or {}),
        "original_prose_before_edit": _snippet(original, 1200, 1600),
        "polished_prose_after_edit": polished,
        "comparison_required": True,
    }
    return json.dumps(packet, ensure_ascii=False, indent=2), polished