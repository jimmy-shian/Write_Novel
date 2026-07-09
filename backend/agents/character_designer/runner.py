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

def run_character_designer(novel_id, user_prompt=None, hint=None, mode="generate", target_char_index=None, stream=False, force_json=False):
    """
    Character Stage:
    - Mode 'generate': Generate characters based on worldview summary.
    - Mode 'expand': Character expansion using general prompt + director's critique hint.
    - Mode 'modify': Character modification requires hint + original character's full JSON.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # 只傳入世界觀摘要，避免過長導致 API 失敗
    worldview_text = select_worldview_context(wb["content"], current_stage="characters") if wb else "尚無世界觀設定"
    
    existing_char_data = db.get_latest_characters(novel_id)
    existing_chars_json = existing_char_data["json_data"] if existing_char_data else '{"characters": []}'
    
    # 💡 安全防護：如果角色聖經已存在，只做增量/修補，不允許全量重跑覆蓋
    if mode == "generate" and existing_char_data:
        try:
            parsed_chars = json.loads(existing_chars_json)
            if parsed_chars.get("characters") and len(parsed_chars["characters"]) > 0:
                print(f"[CHARACTER DESIGNER] Characters already exist. Falling back to expand mode to prevent wipe.")
                mode = "expand"
                if not hint:
                    hint = "請在現有角色基礎上進行補充或優化設定，不要刪除或重置既有角色。"
        except Exception as e:
            print(f"[WARN] Failed to parse existing characters: {e}")

    messages = build_character_designer_messages(worldview_text, existing_chars_json, user_prompt, hint, mode, target_char_index)
    
    db.save_chat_message(novel_id, "user", f"執行角色設計。模式: {mode}, 指示: {user_prompt or hint}", message_type="pipeline")
    
    stream = call_llm_stream("character", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        if _handle_director_context_request(novel_id, "角色設計師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "角色設計師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
            
        # 💡 增量合併邏輯：在 expand / modify 模式下，LLM 只回傳新增/修改的局部角色清單，將其與現有角色合併後再保存
        if mode in ("expand", "modify"):
            try:
                from backend.models.parsers import extract_json_block
                
                new_parsed = extract_json_block(full_text)
                new_chars = new_parsed.get("characters", []) if isinstance(new_parsed, dict) else (new_parsed if isinstance(new_parsed, list) else [])
                if isinstance(new_chars, dict):
                    new_chars = [new_chars]
                
                # 讀取現有角色
                if existing_char_data and existing_chars_json:
                    try:
                        existing_parsed = json.loads(existing_chars_json)
                        existing_chars = existing_parsed.get("characters", []) if isinstance(existing_parsed, dict) else (existing_parsed if isinstance(existing_parsed, list) else [])
                    except Exception:
                        existing_chars = []
                else:
                    existing_chars = []
                
                if mode == "expand":
                    merged_chars = existing_chars + new_chars
                else: # modify
                    if target_char_index is not None:
                        try:
                            # 正常化索引
                            parsed_chars_len = len(existing_chars)
                            norm_idx = db.normalize_char_index(int(target_char_index), parsed_chars_len, source='character_designer')
                            if 0 <= norm_idx < parsed_chars_len and len(new_chars) > 0:
                                existing_chars[norm_idx] = new_chars[0]
                        except Exception:
                            pass
                        merged_chars = existing_chars
                    else:
                        # 依照姓名核心去重合併（db.save_characters 內部已有去重，這裡直接合併）
                        merged_chars = existing_chars + new_chars
                
                merged_json = {"characters": merged_chars}
                full_text = json.dumps(merged_json, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[WARN] 增量角色合併失敗，使用原始輸出: {e}")
                
        db.save_characters(novel_id, full_text)
        db.save_last_agent_run(novel_id, "characters", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"角色聖經更新完畢！版本已更新。", message_type="pipeline")



# =============================================================================
# 伏筆/轉折校驗與結構計算 → 已移至 validation.py
# 以下為向後相容私有別名，agents.py 內部繼續沿用原名稱呼叫
# =============================================================================
_normalize_foreshadowing_output = normalize_foreshadowing_output
_foreshadowing_quantity_error   = foreshadowing_quantity_error
_foreshadowing_schema_error     = foreshadowing_schema_error
_extract_worldview_dict_preserving = extract_worldview_dict_preserving


