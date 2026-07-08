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

def run_copilot_chat(novel_id, user_message, stream=False, force_json=False):
    """
    AI Copilot Chat: User speaks, Copilot analyzes intent, recommends best flow, and chats.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # extract_worldview_summary 會保留核心設定並在過長時做頭尾裁切，避免總監上下文爆量
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    characters_text = json.dumps({"character_names": extract_character_names_list(char_data["json_data"])}, ensure_ascii=False) if char_data else "尚無角色設定"
    
    # 透過 Python 動態偵測階段，修復先前 current_stage 未定義 Bug
    current_stage = diagnostics.detect_current_stage(novel_id)
    
    if current_stage == "volumes":
        vols = db.get_volumes(novel_id)
        plot_text = json.dumps({"volumes": vols}, ensure_ascii=False, indent=2) if vols else "尚無篇卷規劃"
    else:
        plot_data = db.get_stitched_plot(novel_id)
        raw_plot_text = json.dumps(plot_data, ensure_ascii=False) if plot_data else "尚無章節大綱"
        plot_text = simplify_plot_data_for_copilot(raw_plot_text)
    
    # 建立系統記憶歷史以保證上下文連貫
    history = db.get_chat_memory(novel_id, limit=10)
    history_context = ""
    for h in history:
        history_context += f"【{h['role']}】：{h['content']}\n"

    # 生成 Python 剛性指標檢查報告
    validation_report = diagnostics.generate_validation_report(novel_id)

    messages = build_copilot_chat_messages(
        novel_id, worldview_text, characters_text, plot_text, history_context, user_message, 
        validation_report=validation_report,
        gold_rules_context=_load_retrospective_gold_rules(novel_id)
    )
    
    db.save_chat_message(novel_id, "user", user_message, message_type="chat")
    
    stream = call_llm_stream("copilot", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream, collect_thinking=True)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    full_thinking = acc.thinking
    if full_text.strip():
        db.save_chat_message(novel_id, "assistant", full_text, thinking=full_thinking if full_thinking.strip() else None, message_type="chat")


