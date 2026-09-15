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

    field_label = {"foreshadowing_seeds": "伏筆種子", "key_turning_points": "關鍵轉折點"}.get(target_field or "", "伏筆與轉折")
    db.save_chat_message(novel_id, "user", f"執行{field_label}生成（自動分批累加至 50 條）。要求: {user_prompt}", message_type="pipeline")

    wb_dict = _extract_worldview_dict_preserving(wb["content"]) if wb else {}
    if not wb_dict:
        error_message = "世界觀內容為空或無法解析，禁止以空資料覆蓋既有設定。請先完成或修復世界觀生成後再繼續。"
        db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
        yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    from backend.models.parsers import extract_json_block

    # =========================================================================
    # 模式 A: 伏筆種子分批累加生成 (Target: 50+ 條，每批 15 條)
    # =========================================================================
    if target_field == "foreshadowing_seeds":
        target_count = max(MIN_FORESHADOWING_SEEDS, 50)
        batch_size = 15
        max_batches = 6

        current_seeds = [s for s in (wb_dict.get("foreshadowing_seeds") or []) if isinstance(s, dict)]
        batch_idx = 0

        while len(current_seeds) < target_count and batch_idx < max_batches:
            batch_idx += 1
            needed = min(batch_size, target_count - len(current_seeds))
            start_id = len(current_seeds) + 1
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"正在生成伏筆種子批次 {batch_idx}/{max_batches} (目前已累積 {len(current_seeds)}/{target_count}，本批預計生成 {needed} 個)..."
            }, ensure_ascii=False) + "\n\n"

            messages = build_foreshadowing_messages(
                worldview_text, characters_json, user_prompt,
                target_field="foreshadowing_seeds", novel_id=novel_id,
                batch_size=needed, existing_items=current_seeds, start_id=start_id
            )

            llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
            acc = StreamAccumulator(llm_stream)
            for chunk in acc:
                yield chunk
            batch_text = acc.content

            if _handle_director_context_request(novel_id, "伏筆與轉折編織師", batch_text):
                yield "data: " + json.dumps({"type": "error", "message": "伏筆與轉折編織師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            parsed_foreshadowing = extract_json_block(batch_text)
            normalized_foreshadowing = _normalize_foreshadowing_output(parsed_foreshadowing)
            new_seeds = normalized_foreshadowing.get("foreshadowing_seeds", [])

            if not new_seeds:
                if len(current_seeds) >= 10:
                    break
                error_message = f"伏筆種子批次 {batch_idx} 未取得任何有效的種子輸出。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            existing_names = set(
                str(s.get("name") or "").strip().lower() for s in current_seeds
            )
            for s in new_seeds:
                if not isinstance(s, dict):
                    continue
                s_name = str(s.get("name") or "").strip()
                if not s_name or s_name.lower() in existing_names:
                    continue
                existing_names.add(s_name.lower())
                s["id"] = len(current_seeds) + 1
                current_seeds.append(s)

            wb_dict["foreshadowing_seeds"] = current_seeds
            updated_content = json.dumps(wb_dict, ensure_ascii=False, indent=2)
            db.save_worldbuilding(novel_id, updated_content, validate=False)
            db.save_last_agent_run(novel_id, "foreshadowing", json.dumps(messages, ensure_ascii=False, indent=2), batch_text)
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"伏筆種子批次 {batch_idx} 完成，已成功存入 {len(current_seeds)}/{target_count} 個種子。"
            }, ensure_ascii=False) + "\n\n"

        db.save_chat_message(novel_id, "assistant", f"伏筆種子分批累加生成成功！共 {len(current_seeds)} 個，已寫入世界觀。", message_type="pipeline")
        yield "data: " + json.dumps({"type": "status", "message": f"伏筆種子生成完成，共 {len(current_seeds)} 個。"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    # =========================================================================
    # 模式 B: 關鍵轉折點分批累加生成 (Target: 50+ 條，每批 15 條，聯動伏筆種子)
    # =========================================================================
    elif target_field == "key_turning_points":
        target_count = max(MIN_KEY_TURNING_POINTS, 50)
        batch_size = 15
        max_batches = 6

        current_turns = [t for t in (wb_dict.get("key_turning_points") or []) if isinstance(t, dict)]
        existing_seeds = [s for s in (wb_dict.get("foreshadowing_seeds") or []) if isinstance(s, dict)]
        batch_idx = 0

        while len(current_turns) < target_count and batch_idx < max_batches:
            batch_idx += 1
            needed = min(batch_size, target_count - len(current_turns))
            start_id = len(current_turns) + 1
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"正在規劃關鍵轉折點批次 {batch_idx}/{max_batches} (目前已累積 {len(current_turns)}/{target_count}，本批預計生成 {needed} 個)..."
            }, ensure_ascii=False) + "\n\n"

            messages = build_foreshadowing_messages(
                worldview_text, characters_json, user_prompt,
                target_field="key_turning_points", novel_id=novel_id,
                batch_size=needed, existing_items=current_turns, start_id=start_id,
                established_seeds=existing_seeds,
            )

            llm_stream = call_llm_stream("architect", messages, stream=stream, force_json=force_json)
            acc = StreamAccumulator(llm_stream)
            for chunk in acc:
                yield chunk
            batch_text = acc.content

            if _handle_director_context_request(novel_id, "伏筆與轉折編織師", batch_text):
                yield "data: " + json.dumps({"type": "error", "message": "伏筆與轉折編織師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            parsed_foreshadowing = extract_json_block(batch_text)
            normalized_foreshadowing = _normalize_foreshadowing_output(parsed_foreshadowing)
            new_turns = normalized_foreshadowing.get("key_turning_points", [])

            if not new_turns:
                if len(current_turns) >= 10:
                    break
                error_message = f"關鍵轉折點批次 {batch_idx} 未取得任何有效的轉折點輸出。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            existing_names = set(
                str(t.get("turning_point_name") or t.get("name") or "").strip().lower() for t in current_turns
            )
            for t in new_turns:
                if not isinstance(t, dict):
                    continue
                t_name = str(t.get("turning_point_name") or t.get("name") or "").strip()
                if not t_name or t_name.lower() in existing_names:
                    continue
                existing_names.add(t_name.lower())
                t["id"] = len(current_turns) + 1
                current_turns.append(t)

            wb_dict["key_turning_points"] = current_turns
            updated_content = json.dumps(wb_dict, ensure_ascii=False, indent=2)
            db.save_worldbuilding(novel_id, updated_content, validate=False)
            db.save_last_agent_run(novel_id, "foreshadowing", json.dumps(messages, ensure_ascii=False, indent=2), batch_text)
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"關鍵轉折點批次 {batch_idx} 完成，已成功存入 {len(current_turns)}/{target_count} 個轉折點。"
            }, ensure_ascii=False) + "\n\n"

        try:
            if db.get_volumes(novel_id):
                db.precompute_global_foreshadowing(novel_id)
        except Exception as e:
            print(f"[WARN] Failed to precompute global foreshadowing after key_turning_points: {e}")

        db.save_chat_message(novel_id, "assistant", f"關鍵轉折點分批累加生成成功！共 {len(current_turns)} 個，已寫入世界觀。", message_type="pipeline")
        yield "data: " + json.dumps({"type": "status", "message": f"關鍵轉折點生成完成，共 {len(current_turns)} 個。"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    # =========================================================================
    # 模式 C: 全量模式（target_field=None）：依序執行 seeds 與 turns 兩大批次階段 (各 50+ 條)
    # =========================================================================
    yield "data: " + json.dumps({
        "type": "status",
        "message": "開始全書伏筆與轉折分段組合生成：第一階段【編織伏筆種子網絡（目標 50+ 條）】..."
    }, ensure_ascii=False) + "\n\n"

    for chunk in run_foreshadowing_orchestrator(
        novel_id, user_prompt=user_prompt, target_field="foreshadowing_seeds", stream=stream, force_json=force_json
    ):
        if '"type": "done"' in chunk:
            continue
        yield chunk

    yield "data: " + json.dumps({
        "type": "status",
        "message": "伏筆種子網絡建立就緒！進入第二階段【規劃核心關鍵轉折點（與伏筆網絡聯動，目標 50+ 條）】..."
    }, ensure_ascii=False) + "\n\n"

    for chunk in run_foreshadowing_orchestrator(
        novel_id, user_prompt=user_prompt, target_field="key_turning_points", stream=stream, force_json=force_json
    ):
        yield chunk
    return


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
