# -*- coding: utf-8 -*-
import asyncio
import json
import time
import traceback
from functools import partial

from backend import persistence as db
from backend.services import diagnostics
import backend.services.director.context as director_context
from backend.common.llm import call_llm_stream
from backend.common.config import (
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    VOLUME_SKELETON_BATCH_SIZE,
    VOLUME_SKELETON_BATCH_RETRIES,
    VOLUME_SKELETON_SEGMENT_RETRIES,
    VOLUME_SKELETON_COMPLETION_PREFIX_LIMIT,
)
from backend.common.utils import deep_merge_dict, StreamAccumulator
from backend.schemas.constraints import load_retrospective_gold_rules
from backend.schemas.validation import (
    normalize_foreshadowing_output,
    foreshadowing_quantity_error,
    foreshadowing_schema_error,
    volume_plan_validation_error,
    chapter_index_or_none,
    volume_existing_chapter_indexes,
    volume_missing_chapter_indexes,
    parse_requested_chapter_indexes,
    split_consecutive_batches,
    extract_chapters_in_range,
    suggest_segment_split,
    extract_worldview_dict_preserving,
    resolve_single_volume_index,
)
from backend.prompts.common.context import (
    compact_json_data,
    extract_character_basic,
    extract_character_names_list,
    extract_worldview_summary,
    mask_worldview_seeds_and_turns,
    select_worldview_context,
)
from backend.agents.story_architect.prompts import (
    build_story_architect_messages,
    build_worldview_core_messages,
    build_multi_act_structure_messages,
    build_progressive_character_plan_messages,
)
from backend.agents.character_designer.prompts import (
    build_character_designer_messages,
    build_missing_character_designer_messages,
)
from backend.agents.foreshadowing_orchestrator.prompts import build_foreshadowing_messages
from backend.agents.volumes_planner.prompts import build_volumes_planner_messages
from backend.agents.volume_skeleton.prompts import (
    build_volume_skeleton_planner_messages,
    build_volume_skeleton_completion_messages,
    build_incremental_skeleton_messages,
)
from backend.agents.chapter_writer.prompts import build_chapter_writer_messages
from backend.services import narrative_memory
from backend.agents.editor.prompts import build_editor_agent_messages
from backend.agents.copilot.prompts import build_copilot_chat_messages, simplify_plot_data_for_copilot
from backend.agents.director.prompts import (
    build_director_decision_messages,
    build_director_decision_help_messages,
)
from backend.agents.incremental.prompts import (
    build_incremental_architect_messages,
    build_incremental_character_messages,
)

_load_retrospective_gold_rules = load_retrospective_gold_rules
_normalize_foreshadowing_output = normalize_foreshadowing_output
_foreshadowing_quantity_error = foreshadowing_quantity_error
_foreshadowing_schema_error = foreshadowing_schema_error
_extract_worldview_dict_preserving = extract_worldview_dict_preserving
_volume_plan_validation_error = volume_plan_validation_error
_volume_existing_chapter_indexes = volume_existing_chapter_indexes
_volume_missing_chapter_indexes = volume_missing_chapter_indexes
_parse_requested_chapter_indexes = parse_requested_chapter_indexes
_split_consecutive_batches = split_consecutive_batches
_extract_chapters_in_range = extract_chapters_in_range

from backend.agents.shared.context_requests import _handle_director_context_request

GENERIC_ACTIVE_CHARACTER_MARKERS = (
    "主角",
    "配角",
    "角色",
    "人物",
    "未知",
    "待定",
    "群像",
    "路人",
    "眾人",
    "旁白",
    "其他",
)

def _active_character_names_from_outline(outline):
    if not isinstance(outline, dict):
        return []
    raw = outline.get("characters_active") or outline.get("characters") or []
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace("、", ",").split(",")
    elif isinstance(raw, list):
        parts = raw
    else:
        parts = []
    names = []
    for item in parts:
        text = str(item).strip()
        if text:
            names.append(text)
    return names


def _character_alias_set(characters_bible):
    aliases = set()
    try:
        parsed = characters_bible
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        chars = parsed.get("characters", []) if isinstance(parsed, dict) else parsed
        if not isinstance(chars, list):
            return aliases
        for char in chars:
            if not isinstance(char, dict):
                continue
            for key in ("name", "alias", "aliases", "nickname", "nicknames", "also_known_as"):
                value = char.get(key)
                if isinstance(value, str):
                    for part in value.replace("，", ",").replace("、", ",").split(","):
                        part = part.strip()
                        if part:
                            aliases.add(part)
                elif isinstance(value, list):
                    aliases.update(str(v).strip() for v in value if str(v).strip())
    except Exception:
        pass
    return aliases


def _is_generic_active_character_name(name):
    clean = str(name or "").strip()
    if not clean:
        return True
    if len(clean) <= 1:
        return True
    return any(marker in clean for marker in GENERIC_ACTIVE_CHARACTER_MARKERS)


def _missing_named_active_characters(outline, characters_bible):
    aliases = _character_alias_set(characters_bible)
    missing = []
    for name in _active_character_names_from_outline(outline):
        if _is_generic_active_character_name(name):
            continue
        if name in aliases:
            continue
        if any(alias and (alias in name or name in alias) for alias in aliases):
            continue
        missing.append(name)
    seen = set()
    result = []
    for name in missing:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result

# =============================================================================
# 6. Chapter Writer Agent
# =============================================================================
def run_chapter_writer(novel_id, chapter_index, custom_style="Classic Modernism", user_prompt=None, stream=False, force_json=False, context_bundle=None):
    """
    Writing Stage:
    Generate prose based on:
    - worldview summary
    - writing style (user setting)
    - current chapter's detailed outline
    - detailed outline of preceding & succeeding 1 volumes (or nearby chapters)
    - clue retrieval details of the next 3 chapters (if any) + writing content where clue is retrieved
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要（依 stage 選欄位）
    worldview_text = select_worldview_context(wb["content"], current_stage="writer") if wb else "尚無世界觀設定"
    
    char_data = db.get_latest_characters(novel_id)
    characters_bible = char_data["parsed_data"] if (char_data and char_data.get("parsed_data")) else "尚無角色設定"
    
    # Only fetch the current chapter + adjacent chapters from the volume outline, not the entire stitched plot
    all_vols = db.get_volumes(novel_id)
    curr_vol_idx = db.get_chapter_volume_index(all_vols, chapter_index)
    current_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == int(curr_vol_idx or 0)), None)
    
    vol_chapters = []
    if current_vol and current_vol.get("chapters_outline"):
        ch_outline = current_vol["chapters_outline"]
        if isinstance(ch_outline, str):
            try:
                ch_outline = json.loads(ch_outline)
            except Exception:
                ch_outline = []
        if isinstance(ch_outline, list):
            vol_chapters = ch_outline
    
    # Also check adjacent volume for prev/next chapter if at volume boundary
    if chapter_index > 1:
        pre_vol_idx = db.get_chapter_volume_index(all_vols, chapter_index - 1)
        if pre_vol_idx != curr_vol_idx:
            pre_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == int(pre_vol_idx)), None)
            if pre_vol and pre_vol.get("chapters_outline"):
                pre_outline = pre_vol["chapters_outline"]
                if isinstance(pre_outline, str):
                    try:
                        pre_outline = json.loads(pre_outline)
                    except Exception:
                        pre_outline = []
                if isinstance(pre_outline, list):
                    vol_chapters = pre_outline + vol_chapters
    
    total_planned = db.get_total_chapter_count(all_vols)
    if chapter_index < total_planned:
        nxt_vol_idx = db.get_chapter_volume_index(all_vols, chapter_index + 1)
        if nxt_vol_idx != curr_vol_idx:
            nxt_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == int(nxt_vol_idx)), None)
            if nxt_vol and nxt_vol.get("chapters_outline"):
                nxt_outline = nxt_vol["chapters_outline"]
                if isinstance(nxt_outline, str):
                    try:
                        nxt_outline = json.loads(nxt_outline)
                    except Exception:
                        nxt_outline = []
                if isinstance(nxt_outline, list):
                    vol_chapters = vol_chapters + nxt_outline
    
    # Normalize only the relevant chapters
    normalized_outlines = []
    for idx, ch in enumerate(vol_chapters):
        if not isinstance(ch, dict):
            continue
        try:
            raw_idx = ch.get("chapter_index") or ch.get("chapter") or ch.get("chapter_number") or ch.get("index") or ch.get("id") or (idx + 1)
            ch["chapter_index"] = int(raw_idx)
        except (ValueError, TypeError):
            ch["chapter_index"] = idx + 1
        normalized_outlines.append(ch)
    
    normalized_outlines.sort(key=lambda x: x["chapter_index"])
    
    current_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index), None)
    if not current_outline:
        current_outline = {
            "chapter_index": chapter_index,
            "title": f"第 {chapter_index} 章",
            "time_setting": "故事時間",
            "events": [{"scene": "發生場景", "action": "核心情節", "consequence": "引發後果"}],
            "purpose": "推進情節",
            "characters_active": []
        }


        
    pre_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index - 1), None)
    nxt_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index + 1), None)
    
    # 角色上下文改由 chapter writer prompt module 依本章大綱、前後章、伏筆線索與額外指示挑選：
    # 大綱中命名的角色送完整角色卡，其餘角色保留名稱與基本關係，避免先在 agent 層誤刪資料。
    surrounding_plot = ""
    if pre_ch_outline:
        surrounding_plot += f"\n【前一章 (第 {chapter_index - 1} 章) 大綱】\n{json.dumps(pre_ch_outline, ensure_ascii=False, indent=2)}\n"
    if nxt_ch_outline:
        surrounding_plot += f"\n【後一章 (第 {chapter_index + 1} 章) 大綱】\n{json.dumps(nxt_ch_outline, ensure_ascii=False, indent=2)}\n"
        
    pre_vol = next((v for v in all_vols if v["volume_index"] == curr_vol_idx - 1), None)
    next_vol = next((v for v in all_vols if v["volume_index"] == curr_vol_idx + 1), None)
    
    vol_outline_context = ""
    if current_vol:
        current_volume_context = {
            "volume_index": curr_vol_idx,
            "title": current_vol.get("title"),
            "summary": current_vol.get("summary"),
            "factions": current_vol.get("parsed_factions") or current_vol.get("factions"),
            "time_timeline": current_vol.get("time_timeline"),
            "sequence_context": current_vol.get("sequence_context"),
            "applicable_rules": current_vol.get("applicable_rules"),
        }
        vol_outline_context += "\n【當前卷設定與勢力上下文（必須遵守）】\n" + json.dumps(current_volume_context, ensure_ascii=False, indent=2) + "\n"
    if pre_vol:
        vol_outline_context += f"\n【前一卷 (第 {curr_vol_idx - 1} 卷) 全卷概要】\n標題：{pre_vol['title']}\n大綱：{pre_vol['summary']}\n勢力：{pre_vol.get('parsed_factions') or pre_vol.get('factions') or ''}\n"
    if next_vol:
        vol_outline_context += f"\n【後一卷 (第 {curr_vol_idx + 1} 卷) 全卷概要】\n標題：{next_vol['title']}\n大綱：{next_vol['summary']}\n勢力：{next_vol.get('parsed_factions') or next_vol.get('factions') or ''}\n"
        
    clue_payoff_details = ""
    next_three_chaps = [ch for ch in normalized_outlines if chapter_index < ch["chapter_index"] <= chapter_index + 3]
    payoff_clues = []
    for ch in next_three_chaps:
        payoffs = ch.get("allocated_tasks", {}).get("foreshadowing_payoffs", []) or ch.get("foreshadowing_payoff", [])
        if payoffs:
            payoff_clues.append(f"第 {ch.get('chapter_index')} 章預計收回的伏筆：{json.dumps(payoffs, ensure_ascii=False)}")
            
    if payoff_clues:
        clue_payoff_details = "\n【後三章預計將要收回的伏筆內容與寫作線索】\n" + "\n".join(payoff_clues) + "\n*(寫作時請合理埋設對應的前置鋪墊，使後續收回顯得自然流暢)*\n"

    memory_packet = narrative_memory.build_writer_memory_context(novel_id, chapter_index)
    if context_bundle:
        memory_packet["context_bus_reference"] = {
            "context_mode": context_bundle.get("context_mode"),
            "backend_stage": context_bundle.get("backend_stage"),
            "target_reference": context_bundle.get("target_reference"),
        }
    narrative_memory_context = narrative_memory.memory_context_text(memory_packet)

    vol_chars = set()
    for ch in vol_chapters:
        for name in _active_character_names_from_outline(ch):
            if not _is_generic_active_character_name(name):
                vol_chars.add(name)
    required_character_set = sorted(list(vol_chars))

    messages = build_chapter_writer_messages(
        worldview_text, characters_bible, current_outline, surrounding_plot,
        vol_outline_context, clue_payoff_details, custom_style, chapter_index,
        user_prompt=user_prompt,
        narrative_memory_context=narrative_memory_context,
        required_character_set=required_character_set,
    )
    
    db.save_chat_message(
        novel_id,
        "user",
        f"開始寫作第 {chapter_index} 章。風格: {custom_style}。指示: {user_prompt or '無額外指示'}",
        message_type="pipeline"
    )
    
    stream = call_llm_stream("writer", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        if _handle_director_context_request(novel_id, "正文寫作作家", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "正文寫作作家需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
        prose_val = full_text
        thinking_val = ""
        special_words = ["[START_OF_PROSE]", "[正文開始]"]
        for sw in special_words:
            idx = full_text.find(sw)
            if idx != -1:
                thinking_val = full_text[:idx].strip()
                prose_val = full_text[idx + len(sw):].strip()
                break
                
        memory_summary = narrative_memory.build_chapter_memory_summary(
            novel_id,
            chapter_index,
            prose_val,
            outline=current_outline,
        )
        synopsis = memory_summary.get("chapter_summary") or current_outline.get("title", f"第 {chapter_index} 章")
        saved_version = db.save_chapter(novel_id, chapter_index, prose_val, synopsis=synopsis, thinking=thinking_val)
        narrative_memory.store_chapter_memory(
            novel_id,
            chapter_index,
            prose_val,
            source_version=saved_version,
            outline=current_outline,
        )
        db.save_last_agent_run(novel_id, "writer", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文寫作完成！", message_type="pipeline")


# =============================================================================
# 7. Editor Agent
# =============================================================================
