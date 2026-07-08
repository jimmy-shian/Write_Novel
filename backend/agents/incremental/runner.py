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

from backend.agents.volume_skeleton.runner import _extract_incremental_skeleton_chapters

def run_incremental_architect(novel_id, target_section, user_hint, stream=False, force_json=False):
    """
    Incremental Architect Stage:
    Updates a specific section of worldview based on user hint, then auto-merges using patch engine.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = wb["content"] if wb else "尚無世界觀設定"
    
    messages = build_incremental_architect_messages(target_section, worldview_text, user_hint)
    
    db.save_chat_message(novel_id, "user", f"增量世界觀修改。板塊: {target_section}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        from backend.services.incremental_patch.engine import validate_and_merge_incremental_patch
        success, version, err = validate_and_merge_incremental_patch(novel_id, target_section, "PATCH", full_text)
        if success:
            db.save_chat_message(novel_id, "assistant", f"增量世界觀更新完成 (版本 {version})", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"增量世界觀更新合併失敗: {err}"}, ensure_ascii=False) + "\n\n"


def run_incremental_character_designer(novel_id, target_char_index, field_name, user_hint, stream=False, force_json=False):
    """
    Incremental Character Stage:
    Updates a single character field or appends a new character, then auto-merges using patch engine.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    char_data = db.get_latest_characters(novel_id)
    existing_chars_json = char_data["json_data"] if char_data else "{'characters': []}"
    
    target_char_content = ""
    normalized_target_index = target_char_index
    if target_char_index is not None:
        try:
            parsed = json.loads(existing_chars_json)
            chars_list = parsed.get("characters", [])
            raw_idx = int(target_char_index)
            normalized_target_index = db.normalize_char_index(raw_idx, len(chars_list), source='incremental_character_designer')
        except IndexError:
            normalized_target_index = None
        except (ValueError, TypeError):
            pass
        if normalized_target_index is not None and 0 <= normalized_target_index < len(chars_list):
            target_char_content = f"\n【待修改角色的完整原內容】\n{json.dumps(chars_list[normalized_target_index], ensure_ascii=False, indent=2)}"
            
    messages = build_incremental_character_messages(
        worldview_text, existing_chars_json, target_char_content, normalized_target_index, field_name, user_hint
    )
    
    action = "PATCH" if normalized_target_index is not None else "APPEND"
    db.save_chat_message(novel_id, "user", f"增量角色修改。目標: {normalized_target_index if normalized_target_index is not None else '新增'}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("character", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        from backend.services.incremental_patch.engine import validate_and_merge_incremental_patch
        extra = {}
        if normalized_target_index is not None:
            extra["char_index"] = normalized_target_index
        if field_name:
            extra["field_name"] = field_name
        success, version, err = validate_and_merge_incremental_patch(novel_id, "characters", action, full_text, extra)
        if success:
            db.save_chat_message(novel_id, "assistant", f"角色增量更新完成 (版本 {version})", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": f"角色增量更新合併失敗: {err}"}, ensure_ascii=False) + "\n\n"



def run_incremental_volume_skeleton(novel_id, volume_index, user_hint, stream=False, force_json=False):
    """
    Incremental Volume Skeleton Stage:
    Updates a specific volume's skeleton based on user hint, then auto-merges and updates the DB.
    """
    volume_index = int(volume_index)
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = extract_worldview_summary(wb["content"]) if wb else "尚無世界觀設定"
    
    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if v["volume_index"] == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")
        
    existing_skeleton = json.dumps(current_vol.get("chapters_outline") or [], ensure_ascii=False, indent=2)
    
    from backend.agents.incremental.prompts import build_incremental_skeleton_messages
    messages = build_incremental_skeleton_messages(worldview_text, volume_index, existing_skeleton, user_hint)
    
    db.save_chat_message(novel_id, "user", f"增量卷骨架修改。卷: {volume_index}, 要求: {user_hint}", message_type="pipeline")
    stream = call_llm_stream("volume_skeleton", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        from backend.models.parsers import extract_json_block
        parsed = extract_json_block(full_text)
        chapters_skeleton = _extract_incremental_skeleton_chapters(parsed)
        
        if chapters_skeleton:
            db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
            db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷骨架增量更新完成", message_type="pipeline")
        else:
            yield "data: " + json.dumps({"type": "error", "message": "卷骨架增量更新失敗: 未解析到含 chapter_index 的 chapters_skeleton patch"}, ensure_ascii=False) + "\n\n"


