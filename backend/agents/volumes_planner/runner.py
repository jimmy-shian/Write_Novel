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
    MIN_VOLUME_COUNT,
    MAX_VOLUME_COUNT,
    MIN_CHAPTERS_PER_VOLUME,
    MAX_CHAPTERS_PER_VOLUME,
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

def run_volumes_planner(novel_id, user_prompt=None, hint=None, mode="generate", target_vol_idx=None, stream=False, force_json=False):
    """
    Volumes Planner Stage:
    - Mode 'generate': Faction & multi-act progressive batch generation (each batch 2-3 volumes, accumulating to 10-12 volumes).
    - Mode 'patch': Volume patch/add: passes hint and specifies generating only `[idx]`.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = select_worldview_context(wb["content"], current_stage="volumes") if wb else "尚無世界觀設定"

    # 提取已確立角色名冊摘要（供篇卷衝突與角色弧線對齊）
    chars_summary = ""
    try:
        char_data = db.get_latest_characters(novel_id)
        if char_data:
            p = char_data.get("parsed_data") or json.loads(char_data.get("json_data", "{}"))
            raw_c = p.get("characters", []) if isinstance(p, dict) else (p if isinstance(p, list) else [])
            char_lines = []
            for c in raw_c:
                if isinstance(c, dict) and c.get("name"):
                    name = c.get("name")
                    role = c.get("role", "未知定位")
                    faction = c.get("faction") or c.get("affiliation") or "未定"
                    want = str(c.get("want") or c.get("motivation") or "")[:40]
                    secret = str(c.get("secret") or "")[:40]
                    char_lines.append(f"- 【{name}】（陣營: {faction}，定位: {role}，核心追求: {want}，隱藏秘密: {secret}）")
            if char_lines:
                chars_summary = "\n".join(char_lines[:30]) + ("\n...(其餘次要角色略)" if len(char_lines) > 30 else "")
    except Exception as e:
        print(f"[WARN] Failed to load characters summary in volumes_planner: {e}")
        chars_summary = ""

    # 提取全書伏筆網絡與關鍵轉折點摘要（供各卷高潮起伏與懸念收束對齊）
    foreshadowing_summary = ""
    try:
        wb_dict = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
        seeds = wb_dict.get("foreshadowing_seeds", [])
        turns = wb_dict.get("key_turning_points", [])
        fs_lines = []
        if seeds and isinstance(seeds, list):
            fs_lines.append("【核心伏筆種子清單】")
            for s in seeds[:25]:
                if isinstance(s, dict):
                    sid = s.get("id") or s.get("tag", "伏筆")
                    content = s.get("content") or s.get("clue_content") or ""
                    deadline = s.get("payoff_deadline_chapter") or s.get("expected_payoff_window") or "未定"
                    chars = ", ".join(s.get("related_characters", [])) if isinstance(s.get("related_characters"), list) else str(s.get("related_characters", ""))
                    fs_lines.append(f"- [{sid}] {content}（承載角色: {chars}，預計回收章: {deadline}）")
        if turns and isinstance(turns, list):
            fs_lines.append("【關鍵重大轉折點清單】")
            for t in turns[:20]:
                if isinstance(t, dict):
                    tid = t.get("id") or "轉折"
                    evt = t.get("event") or t.get("turning_point") or ""
                    trigger = t.get("trigger_flaw") or t.get("cost") or ""
                    ch = t.get("expected_chapter") or "未定"
                    fs_lines.append(f"- [{tid}] 第 {ch} 章左右：{evt}（代價/觸發: {trigger}）")
        if fs_lines:
            foreshadowing_summary = "\n".join(fs_lines)
    except Exception as e:
        print(f"[WARN] Failed to load foreshadowing summary in volumes_planner: {e}")
        foreshadowing_summary = ""

    from backend.models.parsers import extract_json_block

    if mode == "generate":
        target_volume_count = max(MIN_VOLUME_COUNT, 12)
        batch_size = 3
        max_batches = 6

        # 讀取現有篇卷，若已有一部分合規篇卷可接續規劃
        existing_vols = db.get_volumes(novel_id) or []
        accumulated_vols = []
        for idx, v in enumerate(existing_vols, start=1):
            if isinstance(v, dict) and v.get("title") and v.get("summary"):
                v_copy = dict(v)
                v_copy["volume_index"] = idx
                try:
                    ch_cnt = int(v_copy.get("chapter_count", 0))
                except Exception:
                    ch_cnt = 0
                if MIN_CHAPTERS_PER_VOLUME <= ch_cnt <= MAX_CHAPTERS_PER_VOLUME:
                    accumulated_vols.append(v_copy)

        # 若已達標，無需重新分批生成
        if len(accumulated_vols) >= target_volume_count:
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"全書分卷架構已就緒（已規劃 {len(accumulated_vols)} 卷，符合長篇小說標準），無需重新生成。"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        db.save_chat_message(
            novel_id, "user",
            f"啟動分批篇卷規劃（目標：累積 {target_volume_count} 卷，每批精細推演 {batch_size} 卷，每卷 40-50 章）。要求: {user_prompt or '依世界觀架構分批精細規劃'}",
            message_type="pipeline"
        )

        batch_idx = 0
        last_messages = []
        last_full_text = ""

        while len(accumulated_vols) < target_volume_count and batch_idx < max_batches:
            batch_idx += 1
            start_vol_idx = len(accumulated_vols) + 1
            needed = target_volume_count - len(accumulated_vols)
            this_batch_count = min(batch_size, needed)
            end_vol_idx = start_vol_idx + this_batch_count - 1

            yield "data: " + json.dumps({
                "type": "status",
                "message": f"正在精細規劃第 {start_vol_idx} 至第 {end_vol_idx} 卷（批次 {batch_idx}，目前全書已累積 {len(accumulated_vols)}/{target_volume_count} 卷，每卷 40-50 章）..."
            }, ensure_ascii=False) + "\n\n"

            batch_info = {
                "start_vol_idx": start_vol_idx,
                "end_vol_idx": end_vol_idx,
                "batch_count": this_batch_count,
                "total_target": target_volume_count,
                "previous_volumes": accumulated_vols[-3:] if accumulated_vols else [],
            }

            messages = build_volumes_planner_messages(
                worldview_text=worldview_text,
                existing_vols=accumulated_vols,
                user_prompt=user_prompt,
                hint=hint,
                mode="generate",
                target_vol_idx=None,
                novel_id=novel_id,
                batch_info=batch_info,
                characters_summary=chars_summary,
                foreshadowing_summary=foreshadowing_summary,
            )
            last_messages = messages

            stream_gen = call_llm_stream("volumes", messages, stream=stream, force_json=force_json)
            acc = StreamAccumulator(stream_gen)
            for chunk in acc:
                yield chunk
            batch_text = acc.content
            last_full_text = batch_text

            if not batch_text.strip():
                error_message = f"第 {start_vol_idx}-{end_vol_idx} 卷批次生成無回傳內容。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            if _handle_director_context_request(novel_id, f"篇卷規劃師(卷{start_vol_idx}-{end_vol_idx})", batch_text):
                yield "data: " + json.dumps({"type": "error", "message": "篇卷規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            parsed_vols = extract_json_block(batch_text)
            raw_vols_list = parsed_vols.get("volumes", []) if isinstance(parsed_vols, dict) else (parsed_vols if isinstance(parsed_vols, list) else [])

            if not raw_vols_list:
                error_message = f"第 {start_vol_idx}-{end_vol_idx} 卷批次未能解析出任何合規篇卷列表結構。請重試。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            adjusted_batch_vols = []
            for i, vol in enumerate(raw_vols_list):
                if not isinstance(vol, dict):
                    continue
                expected_idx = start_vol_idx + i
                vol["volume_index"] = expected_idx
                try:
                    vol["chapter_count"] = int(vol.get("chapter_count", 0))
                except Exception:
                    vol["chapter_count"] = 0
                adjusted_batch_vols.append(vol)

            # 單批次結構校驗（is_batch=True，校驗每卷章節 40-50 章與必填欄位，不卡全書總量）
            batch_val_error = _volume_plan_validation_error(adjusted_batch_vols, mode="generate", is_batch=True)
            if batch_val_error:
                error_message = f"第 {start_vol_idx}-{end_vol_idx} 卷批次生成不合規：{batch_val_error}。請重新生成該批次。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            # 將合規批次追加至累積篇卷清單
            accumulated_vols.extend(adjusted_batch_vols)

            # 即時持久化至 DB（第一批時清空舊下游骨架，後續批次累加追加）
            is_first_batch = (batch_idx == 1 and len(existing_vols) == 0)
            db.save_volumes(novel_id, accumulated_vols, clear_downstream=is_first_batch)

            yield "data: " + json.dumps({
                "type": "status",
                "message": f"第 {start_vol_idx} 至第 {end_vol_idx} 卷規劃完成！已成功累積 {len(accumulated_vols)}/{target_volume_count} 卷。"
            }, ensure_ascii=False) + "\n\n"

        # 全批次完成後的總量合規校驗（全書總量必須達標 10-20 卷，每卷 40-50 章）
        final_validation_error = _volume_plan_validation_error(accumulated_vols, mode="generate", is_batch=False)
        if final_validation_error:
            error_message = f"全書篇卷規劃最終驗證未通過：{final_validation_error}。請繼續補充篇卷。"
            db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
            yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        # 預計算全局伏筆與轉折藍圖
        try:
            db.precompute_global_foreshadowing(novel_id)
        except Exception as e:
            print(f"[WARN] Failed to precompute global foreshadowing in run_volumes_planner: {e}")

        db.save_last_agent_run(novel_id, "volumes", json.dumps(last_messages, ensure_ascii=False, indent=2), last_full_text)
        db.save_chat_message(novel_id, "assistant", f"🎉 全書篇卷架構分批規劃圓滿完成！共確立 {len(accumulated_vols)} 卷，每卷 40-50 章，總篇幅完全符合長篇小說標準，結構已成功持久化。", message_type="pipeline")
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    else:
        # Patch mode: 修補指定卷
        existing_vols = db.get_volumes(novel_id)
        messages = build_volumes_planner_messages(
            worldview_text,
            existing_vols,
            user_prompt,
            hint,
            mode,
            target_vol_idx,
            novel_id=novel_id,
            characters_summary=chars_summary,
            foreshadowing_summary=foreshadowing_summary,
        )

        db.save_chat_message(novel_id, "user", f"執行篇卷修補。模式: {mode}, 目標卷: {target_vol_idx or 1}", message_type="pipeline")

        stream_gen = call_llm_stream("volumes", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(stream_gen)
        for chunk in acc:
            yield chunk
        full_text = acc.content

        if full_text.strip():
            if _handle_director_context_request(novel_id, "篇卷規劃師", full_text):
                yield "data: " + json.dumps({"type": "error", "message": "篇卷規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            parsed_vols = extract_json_block(full_text)
            vols_list = parsed_vols.get("volumes", []) if isinstance(parsed_vols, dict) else (parsed_vols if isinstance(parsed_vols, list) else [])

            if not vols_list:
                error_message = "篇卷修補失敗：未能解析出合規篇卷列表結構。請重試。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            adjusted_vols = []
            for i, vol in enumerate(vols_list):
                try:
                    vol_idx = int(vol.get("volume_index", target_vol_idx or (i + 1)))
                except Exception:
                    vol_idx = target_vol_idx or (i + 1)
                vol["volume_index"] = vol_idx
                try:
                    vol["chapter_count"] = int(vol.get("chapter_count", 0))
                except Exception:
                    vol["chapter_count"] = 0
                adjusted_vols.append(vol)

            validation_error = _volume_plan_validation_error(adjusted_vols, mode="patch", is_batch=True)
            if validation_error:
                error_message = f"篇卷修補失敗：{validation_error}。請重新修補，不會保存本次不合規輸出。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            db.save_volumes(novel_id, adjusted_vols, clear_downstream=False, target_vol_idx=target_vol_idx)
            try:
                db.precompute_global_foreshadowing(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to precompute global foreshadowing in run_volumes_planner patch: {e}")

            db.save_last_agent_run(novel_id, "volumes", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
            db.save_chat_message(novel_id, "assistant", f"第 {target_vol_idx or 1} 卷修補已儲存成功！", message_type="pipeline")
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


# =============================================================================
# 4. Volume Skeleton Planner Agent
# =============================================================================


# =============================================================================
# 章節索引計算工具 → 已移至 validation.py
# 以下為向後相容私有別名
# =============================================================================
_chapter_index_or_none         = chapter_index_or_none
_volume_existing_chapter_indexes = volume_existing_chapter_indexes
_volume_missing_chapter_indexes  = volume_missing_chapter_indexes
_parse_requested_chapter_indexes = parse_requested_chapter_indexes
_split_consecutive_batches       = split_consecutive_batches
_extract_chapters_in_range       = extract_chapters_in_range


