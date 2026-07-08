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
from backend.services import narrative_memory
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

from backend.agents.shared.context_requests import _handle_director_context_request

def run_editor_agent(novel_id, chapter_index, edit_instructions=None, stream=False, force_json=False, context_bundle=None):
    """
    Editor Stage:
    Polishes/edits the chapter prose using Senior Editor, replacing the original content directly.
    """
    chapter_data = db.get_latest_chapter(novel_id, chapter_index)
    if not chapter_data:
        raise ValueError(f"Chapter {chapter_index} prose not found for editing!")
        
    original_prose = chapter_data.get("content", "")
    current_synopsis = chapter_data.get("synopsis", "")
    editor_context_packet = narrative_memory.build_editor_context_packet(novel_id, chapter_index, original_prose)
    if context_bundle:
        editor_context_packet["context_bus_reference"] = {
            "context_mode": context_bundle.get("context_mode"),
            "backend_stage": context_bundle.get("backend_stage"),
            "target_reference": context_bundle.get("target_reference"),
        }
    
    messages = build_editor_agent_messages(
        chapter_index,
        edit_instructions,
        original_prose,
        editor_context=narrative_memory.memory_context_text(editor_context_packet),
    )
    
    db.save_chat_message(novel_id, "user", f"調用編輯姬潤色第 {chapter_index} 章。指示: {edit_instructions}", message_type="pipeline")
    
    stream = call_llm_stream("editor", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        if _handle_director_context_request(novel_id, "編輯姬", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "編輯姬需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
        outline = narrative_memory.get_chapter_outline(novel_id, chapter_index)
        memory_summary = narrative_memory.build_chapter_memory_summary(
            novel_id,
            chapter_index,
            full_text,
            outline=outline,
        )
        synopsis = memory_summary.get("chapter_summary") or current_synopsis
        saved_version = db.save_chapter(novel_id, chapter_index, full_text, synopsis=synopsis)
        narrative_memory.store_chapter_memory(
            novel_id,
            chapter_index,
            full_text,
            source_version=saved_version,
            outline=outline,
        )
        db.save_last_agent_run(novel_id, "editor", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已成功潤色替換！", message_type="pipeline")


# =============================================================================
# 8. Copilot / Director Orchestration
# =============================================================================
