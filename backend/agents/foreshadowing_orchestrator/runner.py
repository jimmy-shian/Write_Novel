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

def run_foreshadowing_orchestrator(novel_id, user_prompt=None, target_field=None, stream=False, force_json=False):
    """
    Foreshadowing Stage: Generate foreshadowing seeds and/or key turning points.
    Based on worldview text + character bible.

    target_field: None = 兩者都生成（全量）
                  "foreshadowing_seeds"   = 只生成伏筆種子
                  "key_turning_points"    = 只生成關鍵轉折點
    當使用 target_field 時，已存在的另一欄位保留不覆蓋，避免單次 JSON 過長導致解析錯誤。
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = select_worldview_context(wb["content"], current_stage="foreshadowing") if wb else "尚無世界觀設定"
    
    # Remove existing seeds/turns so the agent generates them fresh, not referencing old ones
    try:
        _wv_tmp = json.loads(worldview_text) if worldview_text and worldview_text != "尚無世界觀設定" else None
        if isinstance(_wv_tmp, dict):
            if "worldview_context" in _wv_tmp and isinstance(_wv_tmp["worldview_context"], dict):
                _wv_ctx = _wv_tmp["worldview_context"]
                _wv_ctx.pop("foreshadowing_seeds", None)
                _wv_ctx.pop("key_turning_points", None)
                worldview_text = json.dumps(_wv_tmp, ensure_ascii=False, indent=2)
            else:
                _wv_tmp.pop("foreshadowing_seeds", None)
                _wv_tmp.pop("key_turning_points", None)
                worldview_text = json.dumps(_wv_tmp, ensure_ascii=False, indent=2)
    except Exception:
        pass
    
    char_data = db.get_latest_characters(novel_id)
    characters_json = json.dumps(extract_character_basic(char_data["parsed_data"]), ensure_ascii=False) if char_data else "{'characters': []}"
    
    messages = build_foreshadowing_messages(worldview_text, characters_json, user_prompt, target_field=target_field)
    
    field_label = {"foreshadowing_seeds": "伏筆種子", "key_turning_points": "關鍵轉折點"}.get(target_field or "", "伏筆與轉折")
    db.save_chat_message(novel_id, "user", f"執行{field_label}獨立生成。要求: {user_prompt}", message_type="pipeline")
    
    llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json) # Map to architect model preset
    acc = StreamAccumulator(llm_stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        if _handle_director_context_request(novel_id, "伏筆與轉折編織師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "伏筆與轉折編織師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
        # Parse the JSON block and merge back into worldview.
        from backend.models.parsers import extract_json_block
        parsed_foreshadowing = extract_json_block(full_text)
        normalized_foreshadowing = _normalize_foreshadowing_output(parsed_foreshadowing)
        seeds = normalized_foreshadowing.get("foreshadowing_seeds", [])
        turns = normalized_foreshadowing.get("key_turning_points", [])

        # --- 分批模式：只驗證本批次目標欄位 ---
        if target_field == "foreshadowing_seeds":
            # 只生成 seeds，turns 保留現有值
            if not seeds:
                error_message = "伏筆種子生成失敗：未取得任何有效的 foreshadowing_seeds。請重新生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            schema_error = _foreshadowing_schema_error(seeds, [])  # 只校驗 seeds
            if schema_error:
                error_message = f"伏筆種子生成失敗：JSON 欄位不合規：{schema_error}。請重新生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            wb_dict = _extract_worldview_dict_preserving(wb["content"]) if wb else {}
            if not wb_dict:
                error_message = "世界觀內容為空或無法解析，禁止以空資料覆蓋既有設定。請先完成或修復世界觀生成後再繼續。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            if wb and wb_dict is None:
                error_message = "伏筆種子生成已完成，但既有世界觀不是可安全合併的 JSON；本次不保存。請先修復世界觀後再生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            wb_dict["foreshadowing_seeds"] = seeds
            # 保留現有的 key_turning_points
            updated_content = json.dumps(wb_dict, ensure_ascii=False, indent=2)
            db.save_worldbuilding(novel_id, updated_content, validate=False)
            db.save_last_agent_run(novel_id, "foreshadowing", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
            db.save_chat_message(novel_id, "assistant", f"伏筆種子生成成功！共 {len(seeds)} 個，已寫入世界觀。", message_type="pipeline")
            yield "data: " + json.dumps({"type": "status", "message": f"伏筆種子生成完成，共 {len(seeds)} 個。"}, ensure_ascii=False) + "\n\n"
            return

        elif target_field == "key_turning_points":
            # 只生成 turns，seeds 保留現有值
            if not turns:
                error_message = "關鍵轉折點生成失敗：未取得任何有效的 key_turning_points。請重新生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            schema_error = _foreshadowing_schema_error([], turns)  # 只校驗 turns
            if schema_error:
                error_message = f"關鍵轉折點生成失敗：JSON 欄位不合規：{schema_error}。請重新生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            wb_dict = _extract_worldview_dict_preserving(wb["content"]) if wb else {}
            if not wb_dict:
                error_message = "世界觀內容為空或無法解析，禁止以空資料覆蓋既有設定。請先完成或修復世界觀生成後再繼續。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            if wb and wb_dict is None:
                error_message = "關鍵轉折點生成已完成，但既有世界觀不是可安全合併的 JSON；本次不保存。請先修復世界觀後再生成。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return
            wb_dict["key_turning_points"] = turns
            # 保留現有的 foreshadowing_seeds
            updated_content = json.dumps(wb_dict, ensure_ascii=False, indent=2)
            db.save_worldbuilding(novel_id, updated_content, validate=False)
            db.save_last_agent_run(novel_id, "foreshadowing", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
            # 生成完 turns 後，嘗試預計算分配藍圖
            try:
                if db.get_volumes(novel_id):
                    db.precompute_global_foreshadowing(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to precompute global foreshadowing after key_turning_points: {e}")
            db.save_chat_message(novel_id, "assistant", f"關鍵轉折點生成成功！共 {len(turns)} 個，已寫入世界觀。", message_type="pipeline")
            yield "data: " + json.dumps({"type": "status", "message": f"關鍵轉折點生成完成，共 {len(turns)} 個。"}, ensure_ascii=False) + "\n\n"
            return

        # --- 全量模式（target_field=None）：同時驗證兩個欄位 ---
        quantity_error = _foreshadowing_quantity_error(seeds, turns)
        if quantity_error:
            error_message = f"伏筆與轉折生成失敗：{quantity_error}。請重新生成，不會保存本次不足量輸出。"
            db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
            yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
            return

        schema_error = _foreshadowing_schema_error(seeds, turns)
        if schema_error:
            error_message = f"伏筆與轉折生成失敗：JSON 欄位不合規：{schema_error}。請重新生成，不會保存本次欄位錯誤輸出。"
            db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
            yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
            return

        wb_dict = _extract_worldview_dict_preserving(wb["content"]) if wb else {}
        if not wb_dict:
            error_message = "世界觀內容為空或無法解析，為避免空資料覆蓋既有設定，本次不保存。請先完成或修復核心世界觀生成後再繼續。"
            db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
            yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
            return
        if wb and wb_dict is None:
            error_message = "伏筆與轉折生成已完成，但既有世界觀不是可安全合併的 JSON；為避免覆蓋前面的世界觀資料，本次不保存。請先修復/重新保存世界觀 JSON 後再生成。"
            db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
            yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
            return

        wb_dict["foreshadowing_seeds"] = seeds
        wb_dict["key_turning_points"] = turns
        
        updated_content = json.dumps(wb_dict, ensure_ascii=False, indent=2)
        db.save_worldbuilding(novel_id, updated_content, validate=False)
        db.save_last_agent_run(novel_id, "foreshadowing", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        try:
            if db.get_volumes(novel_id):
                db.precompute_global_foreshadowing(novel_id)
        except Exception as e:
            print(f"[WARN] Failed to precompute global foreshadowing after foreshadowing generation: {e}")
        db.save_chat_message(novel_id, "assistant", f"獨立伏筆與轉折生成成功！已寫入世界觀設定中。", message_type="pipeline")


# =============================================================================
# 3. Volumes Planner Agent
# =============================================================================
# 篇卷規劃校驗 → 已移至 validation.py: volume_plan_validation_error
_volume_plan_validation_error = volume_plan_validation_error



def run_global_foreshadowing_precompute(novel_id):
    """
    [新功能] 預計算全域伏筆與轉折絕對分配藍圖的包裝函數
    """
    db.precompute_global_foreshadowing(novel_id)
