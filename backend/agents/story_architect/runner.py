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

def run_story_architect(novel_id, user_prompt, stream=False, force_json=False):
    """
    Worldview Stage: Generate worldview based on user's story setting.
    This stage has been refactored into a three-stage pipeline:
    1. Core Worldview (theme, main_conflict, worldview, macro_outline)
    2. Multi-Act Structure (multi_act_structure)
    3. Progressive Character Plan (progressive_character_plan)
    
    If the user_prompt contains [TARGET: ...], we perform targeted incremental generation.
    """
    novel = db.get_novel(novel_id)
    genre = novel.get("genre", "Fantasy")
    style = novel.get("style", "Classic Modernism")
    
    # 讀取已有的世界觀設定
    wb = db.get_latest_worldbuilding(novel_id)
    existing_wb = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    is_initial = not wb or not wb.get("content")
    
    target_part = None
    if user_prompt:
        if "[TARGET: core]" in user_prompt or "[TARGET: worldview]" in user_prompt:
            target_part = "core"
        elif "[TARGET: multi_act_structure]" in user_prompt:
            target_part = "multi_act_structure"
        elif "[TARGET: progressive_character_plan]" in user_prompt:
            target_part = "progressive_character_plan"
            
    if is_initial:
        regen_core = True
        regen_acts = True
        regen_char_plan = True
    else:
        if target_part == "core":
            regen_core = True
            regen_acts = False
            regen_char_plan = False
        elif target_part == "multi_act_structure":
            regen_core = False
            regen_acts = True
            regen_char_plan = False
        elif target_part == "progressive_character_plan":
            regen_core = False
            regen_acts = False
            regen_char_plan = True
        else:
            regen_core = True
            regen_acts = True
            regen_char_plan = True
            
    # 紀錄對話歷史
    db.save_chat_message(novel_id, "user", f"開始生成世界觀。要求: {user_prompt}", message_type="pipeline")
    
    # 階段 1：世界觀核心
    core_json_str = ""
    last_messages = []
    if regen_core:
        yield "data: " + json.dumps({"type": "status", "message": "正在規劃與生成核心世界觀設定（Theme, Conflict, Worldview, Outline）..."}, ensure_ascii=False) + "\n\n"
        messages = build_worldview_core_messages(genre, style, user_prompt)
        last_messages = messages
        llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(llm_stream)
        for chunk in acc:
            yield chunk
        core_json_str = acc.content
    else:
        core_dict = {
            "theme": existing_wb.get("theme", ""),
            "main_conflict": existing_wb.get("main_conflict", ""),
            "worldview": existing_wb.get("worldview", ""),
            "macro_outline": existing_wb.get("macro_outline", "")
        }
        core_json_str = json.dumps(core_dict, ensure_ascii=False, indent=2)
        
    # 階段 2：多幕式結構
    acts_json_str = ""
    if regen_acts:
        yield "data: " + json.dumps({"type": "status", "message": "正在規劃與生成『多幕式劇情起伏結構』(Multi-Act Structure)..."}, ensure_ascii=False) + "\n\n"
        messages = build_multi_act_structure_messages(core_json_str, user_prompt)
        last_messages = messages
        llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(llm_stream)
        for chunk in acc:
            yield chunk
        acts_json_str = acc.content
    else:
        acts_dict = {
            "multi_act_structure": existing_wb.get("multi_act_structure", [])
        }
        acts_json_str = json.dumps(acts_dict, ensure_ascii=False, indent=2)
        
    # 階段 3：角色漸進登場規劃
    char_plan_json_str = ""
    if regen_char_plan:
        yield "data: " + json.dumps({"type": "status", "message": "正在規劃與生成『角色漸進登場規劃策略』(Progressive Character Plan)..."}, ensure_ascii=False) + "\n\n"
        messages = build_progressive_character_plan_messages(core_json_str, acts_json_str, user_prompt)
        last_messages = messages
        llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(llm_stream)
        for chunk in acc:
            yield chunk
        char_plan_json_str = acc.content
    else:
        char_plan_dict = {
            "progressive_character_plan": existing_wb.get("progressive_character_plan", [])
        }
        char_plan_json_str = json.dumps(char_plan_dict, ensure_ascii=False, indent=2)
        
    # 解析各部分的 JSON，並合併
    from backend.models.parsers import extract_json_block
    
    try:
        core_data = extract_json_block(core_json_str) or {}
    except Exception:
        core_data = {}
        
    try:
        acts_data = extract_json_block(acts_json_str) or {}
    except Exception:
        acts_data = {}
        
    try:
        char_plan_data = extract_json_block(char_plan_json_str) or {}
    except Exception:
        char_plan_data = {}
        
    # 合併
    final_worldview = {
        "theme": core_data.get("theme") or existing_wb.get("theme", ""),
        "main_conflict": core_data.get("main_conflict") or existing_wb.get("main_conflict", ""),
        "worldview": core_data.get("worldview") or existing_wb.get("worldview", ""),
        "macro_outline": core_data.get("macro_outline") or existing_wb.get("macro_outline", ""),
        "multi_act_structure": acts_data.get("multi_act_structure") or existing_wb.get("multi_act_structure", []),
        "progressive_character_plan": char_plan_data.get("progressive_character_plan") or existing_wb.get("progressive_character_plan", []),
        "foreshadowing_seeds": existing_wb.get("foreshadowing_seeds", []),
        "key_turning_points": existing_wb.get("key_turning_points", [])
    }
    
    full_text = json.dumps(final_worldview, ensure_ascii=False, indent=2)
    
    # 保存成品
    if full_text.strip():
        if _handle_director_context_request(novel_id, "世界觀架構師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "世界觀架構師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
        db.save_worldbuilding(novel_id, full_text, validate=False)
        db.save_last_agent_run(novel_id, "worldview", json.dumps(last_messages or [], ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"世界觀與大綱起伏結構、角色登場策略生成成功！版本已更新。", message_type="pipeline")


# =============================================================================
# 2. Character Designer Agent
# =============================================================================
