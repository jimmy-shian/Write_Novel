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

def _build_nearby_skeleton_context(volume, batch_indexes):
    """從同卷中提取鄰近批次章節的既有骨架，作為銜接上下文提示詞片段。"""
    chapters = volume.get("chapters_outline") if isinstance(volume, dict) else []
    if isinstance(chapters, str):
        try:
            chapters = json.loads(chapters)
        except Exception:
            chapters = []
    if not isinstance(chapters, list) or not batch_indexes:
        return ""
    lo, hi = min(batch_indexes), max(batch_indexes)
    nearby = []
    for ch in chapters:
        idx = chapter_index_or_none(ch)
        if idx is not None and (lo - 2 <= idx <= hi + 2) and idx not in set(batch_indexes):
            nearby.append(ch)
    if not nearby:
        return ""
    nearby.sort(key=lambda item: int(item.get("chapter_index", 0)))
    return "\n【同卷鄰近既有骨架（只供銜接，不要重寫這些章）】\n" + json.dumps(nearby, ensure_ascii=False, indent=2) + "\n"



def run_volume_skeleton_planner(novel_id, volume_index, user_prompt=None, stream=False, force_json=False):
    """
    Volume Skeleton Stage — full-volume generation.

    This definition intentionally overrides the historical batch implementation
    above. A normal volume_skeleton generate/regenerate call now asks the LLM for
    one complete volume in a single request; incremental patch remains separate.
    """
    from backend.models.parsers import extract_json_block

    volume_index = int(volume_index)
    char_data = db.get_latest_characters(novel_id)
    char_count = 0
    if char_data and char_data.get("json_data"):
        try:
            parsed_chars = json.loads(char_data["json_data"]) if isinstance(char_data["json_data"], str) else char_data["json_data"]
            char_count = len(parsed_chars.get("characters", []))
        except Exception:
            char_count = 0
    min_chars_for_skeleton = 3
    if char_count < min_chars_for_skeleton:
        msg = f"第 {volume_index} 卷骨架生成前偵測到角色數量不足（目前 {char_count} 位，建議至少 {min_chars_for_skeleton} 位）。"
        yield "data: " + json.dumps({
            "type": "need_characters",
            "volume_index": volume_index,
            "current_char_count": char_count,
            "minimum_required": min_chars_for_skeleton,
            "message": msg,
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "status", "message": msg}, ensure_ascii=False) + "\n\n"
        db.save_chat_message(novel_id, "assistant", msg, message_type="pipeline")
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = select_worldview_context(wb["content"], current_stage="volume_skeleton") if wb else "尚無世界觀設定"
    worldview_parsed = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}
    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")

    start_ch, end_ch = db.get_volume_chapter_range(all_vols, volume_index)
    full_indexes = list(range(start_ch, end_ch + 1))
    missing_indexes = _volume_missing_chapter_indexes(all_vols, volume_index)
    if not missing_indexes:
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷骨架已完整，沒有需要補生成的章節。", message_type="pipeline")
        yield "data: " + json.dumps({"type": "content", "delta": f"第 {volume_index} 卷骨架已完整，沒有需要補生成的章節。"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    pre_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index - 1), None)
    next_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index + 1), None)
    surrounding_context = ""
    if pre_vol:
        surrounding_context += f"\n【前 1 卷 (卷 {volume_index - 1}) 大綱概要】\n{pre_vol.get('summary', '')}\n"
    if next_vol:
        surrounding_context += f"\n【後 1 卷 (卷 {volume_index + 1}) 大綱概要】\n{next_vol.get('summary', '')}\n"
    surrounding_context += _build_nearby_skeleton_context(current_vol, full_indexes)
    char_data_for_skeleton = db.get_latest_characters(novel_id)
    existing_character_names = []
    existing_character_briefs = {"characters": []}
    if char_data_for_skeleton and char_data_for_skeleton.get("json_data"):
        try:
            existing_character_names = extract_character_names_list(char_data_for_skeleton["json_data"])
            existing_character_briefs = extract_character_basic(char_data_for_skeleton.get("parsed_data") or char_data_for_skeleton["json_data"])
        except Exception:
            existing_character_names = []
            existing_character_briefs = {"characters": []}
    surrounding_context += (
        "\n【既有角色名冊、基本角色卡與使用規則】\n"
        + json.dumps({
            "existing_character_names": existing_character_names,
            "existing_character_briefs": existing_character_briefs,
            "rule": (
                "characters_active 優先使用此名冊中的既有命名角色。若本卷劇情確實需要新增命名角色，"
                "可在章節骨架中使用具體姓名，但不得假裝已有角色卡；總監審核時必須先補角色卡再進入正文。"
                "功能性群眾、守衛、路人可作為非命名角色使用。"
            ),
        }, ensure_ascii=False, indent=2)
        + "\n"
    )

    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)
    foreshadowing_allocations = blueprint.get("foreshadowing_allocations", [])
    turning_allocations = blueprint.get("turning_allocations", [])

    def task_text(item):
        if isinstance(item, dict):
            for key in ("name", "title", "summary", "description", "content", "seed", "setup_hint", "payoff_hint"):
                if item.get(key):
                    return str(item.get(key))
            return json.dumps(item, ensure_ascii=False)
        return str(item)

    table = {
        ch: {
            "chapter_index": ch,
            "foreshadowing_plants": [],
            "foreshadowing_payoffs": [],
            "turning_points": [],
        }
        for ch in full_indexes
    }
    chapter_set = set(full_indexes)
    for idx, seed in enumerate(all_seeds if isinstance(all_seeds, list) else []):
        if idx >= len(foreshadowing_allocations):
            continue
        try:
            plant_ch, payoff_ch = foreshadowing_allocations[idx]
        except Exception:
            continue
        seed_id = f"Seed-{idx + 1}"
        seed_value = task_text(seed)
        if plant_ch in chapter_set:
            table[int(plant_ch)]["foreshadowing_plants"].append({
                "seed_id": seed_id,
                "seed": seed_value,
                "plant_chapter": int(plant_ch),
                "payoff_chapter": int(payoff_ch),
                "instruction": "在本章自然埋設此線索，不能提前揭露答案；須服務本章劇情。",
            })
        if payoff_ch in chapter_set:
            table[int(payoff_ch)]["foreshadowing_payoffs"].append({
                "seed_id": seed_id,
                "seed": seed_value,
                "plant_chapter": int(plant_ch),
                "payoff_chapter": int(payoff_ch),
                "instruction": "在本章回收此線索，需讓此前鋪墊與本章結果形成清楚因果。",
            })
    for idx, turn in enumerate(all_turns if isinstance(all_turns, list) else []):
        if idx >= len(turning_allocations):
            continue
        try:
            turn_ch = int(turning_allocations[idx])
        except Exception:
            continue
        if turn_ch in chapter_set:
            table[turn_ch]["turning_points"].append({
                "turn_id": f"Turn-{idx + 1}",
                "turn": task_text(turn),
                "chapter": turn_ch,
                "instruction": "本章必須承載此關鍵轉折，事件因果要從前文自然推導。",
            })

    task_rows = [table[ch] for ch in full_indexes]
    non_empty_rows = [
        row for row in task_rows
        if row["foreshadowing_plants"] or row["foreshadowing_payoffs"] or row["turning_points"]
    ]
    precalc_clues = "【Python 預先計算好的本卷逐章伏筆/轉折硬性操作表】\n" + json.dumps({
        "source_of_truth": "Python deterministic foreshadowing_blueprint",
        "volume_index": volume_index,
        "chapter_range": [start_ch, end_ch],
        "rule": "每章 allocated_tasks 必須逐字依此表填寫；空陣列代表該章沒有硬性伏筆/轉折任務，不得自行新增。",
        "all_chapter_allocated_tasks": task_rows,
        "non_empty_task_summary": non_empty_rows,
    }, ensure_ascii=False, indent=2)

    prompt = (
        f"{user_prompt or '請生成本卷完整章節骨架。'}\n\n"
        f"【本次後端整卷生成任務】一次輸出第 {start_ch} 至第 {end_ch} 章的完整卷骨架，"
        f"必須包含這些 chapter_index：{full_indexes}。不得切段、不得只輸出缺失片段。"
    )
    messages = build_volume_skeleton_planner_messages(
        worldview_text, volume_index, current_vol, start_ch, end_ch, len(full_indexes),
        surrounding_context, precalc_clues, prompt
    )

    db.save_chat_message(
        novel_id,
        "user",
        f"生成第 {volume_index} 卷完整骨架大綱。完整章節範圍：第 {start_ch}-{end_ch} 章；目前缺失章節：{missing_indexes[:80]}{'...' if len(missing_indexes) > 80 else ''}",
        message_type="pipeline",
    )

    full_text = ""
    saved_count = 0
    for attempt in range(1, VOLUME_SKELETON_BATCH_RETRIES + 1):
        yield "data: " + json.dumps({"type": "content", "delta": f"\n[整卷骨架] 第 {volume_index} 卷：一次生成第 {start_ch}-{end_ch} 章（第 {attempt} 次）\n"}, ensure_ascii=False) + "\n\n"
        llm_stream = call_llm_stream("volume_skeleton", messages, stream=stream, force_json=force_json)
        accumulated = []
        saw_error = False
        for chunk in llm_stream:
            if chunk.startswith("data:"):
                try:
                    data = json.loads(chunk[5:].strip())
                    if data.get("type") == "done":
                        continue
                    if data.get("type") == "content":
                        accumulated.append(data.get("delta", ""))
                    elif data.get("type") == "error":
                        saw_error = True
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            yield chunk

        full_text = "".join(accumulated)
        if full_text.strip() and _handle_director_context_request(novel_id, "篇卷骨架規劃師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "篇卷骨架規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return
        if not full_text.strip() or saw_error:
            if attempt >= VOLUME_SKELETON_BATCH_RETRIES:
                yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷完整骨架生成失敗，未取得有效內容。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return
            continue

        parsed_skeleton = extract_json_block(full_text)
        chapters_skeleton = _extract_chapters_in_range(parsed_skeleton, full_indexes)
        parsed_indexes = {chapter_index_or_none(ch) for ch in chapters_skeleton}
        missing_after_parse = sorted(set(full_indexes) - parsed_indexes)
        if missing_after_parse:
            if attempt >= VOLUME_SKELETON_BATCH_RETRIES:
                yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷完整骨架仍缺失章節：{missing_after_parse}。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return
            continue

        canonical_map = db.apply_canonical_allocated_tasks_to_chapters(novel_id, chapters_skeleton)
        chapters_skeleton = list(canonical_map.values())
        chapters_skeleton.sort(key=lambda ch: int(ch.get("chapter_index", 0)))
        db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
        saved_count = len(chapters_skeleton)
        break

    db.save_last_agent_run(novel_id, "volume_skeleton", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
    db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷完整骨架生成完成，一次保存/更新 {saved_count} 章。", message_type="pipeline")
    yield "data: " + json.dumps({"type": "content", "delta": f"\n第 {volume_index} 卷完整骨架生成完成，一次保存/更新 {saved_count} 章。"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


# build_missing_character_designer_messages lives with the character designer prompts.
# 本檔透過頂層 import 直接使用，無需額外別名


# =============================================================================
# 4-B. Volume Skeleton — 分段生成 / 補全 (總監調度的分段模式)
# =============================================================================
# 設計原則：
#   1. 每次只生成「總監指定」的一段章節（segment_generate / segment_complete）；
#      handler 內不再有 while remaining 批次迴圈。
#   2. 每段生成並寫入 DB 後，立即 yield partial_state 事件，讓前端即時回填，
#      不再等待整卷完成。
#   3. Python 在每段開始/結束 yield status 事件，讓總監與使用者即時看到進度，
#      避免生成過程中系統看起來像當機。
#   4. 補全段採 completion 模式：把前段已生成章節 JSON 作為 assistant 前綴，
#      要求 LLM 續寫剩餘章節，解決一次生成整卷易斷層的問題。
# =============================================================================


def _emit_partial_state(novel_id, volume_index):
    """生成後立即回填：讀取最新 volumes 並組裝 partial_state SSE 事件。"""
    try:
        vols = db.get_volumes(novel_id)
        return "data: " + json.dumps(
            {"type": "partial_state", "state_updates": {"volumes": vols}},
            ensure_ascii=False,
        ) + "\n\n"
    except Exception as e:
        print(f"[SEGMENT PARTIAL_STATE] Failed to emit partial_state: {e}")
        return ""


def _emit_status(message):
    return "data: " + json.dumps({"type": "status", "message": message}, ensure_ascii=False) + "\n\n"


def _resolve_segment_chapter_range(task, volume_index):
    """
    解析總監指定之「分段章節範圍」。
    優先：task.target.selection（含 chapter_index 列表或 {start,end}）
    次之：task.target.chapter_index 單章
    最後：本卷所有缺失章節（fallback，供直接呼叫）
    回傳排序後的章節索引 list。
    """
    all_vols = db.get_volumes(task.novel_id)
    start_ch, end_ch = db.get_volume_chapter_range(all_vols, volume_index)

    selection = getattr(task.target, "selection", None)
    if isinstance(selection, list) and selection:
        idxs = []
        has_chapter_range_in_selection = False
        for item in selection:
            if isinstance(item, dict):
                raw = item.get("chapter_index") or item.get("chapter") or item.get("index")
                if raw is not None:
                    try:
                        v = int(raw)
                        if start_ch <= v <= end_ch:
                            idxs.append(v)
                    except Exception:
                        pass
                rr = item.get("chapter_range") or item.get("range")
                if isinstance(rr, list) and len(rr) == 2:
                    has_chapter_range_in_selection = True
                    try:
                        lo, hi = int(rr[0]), int(rr[1])
                        idxs.extend(range(max(start_ch, lo), min(end_ch, hi) + 1))
                    except Exception:
                        pass
            elif isinstance(item, (int, float)):
                try:
                    v = int(item)
                    if start_ch <= v <= end_ch:
                        idxs.append(v)
                except Exception:
                    pass
        # 如果 selection 中只有 chapter_range 而無具體 chapter_index，後端仍按 range 展開
        # 但前端傳來的 selection 通常已包含具體 chapter_index 列表，優先使用
        if idxs:
            return sorted(set(idxs))

    if task.target.chapter_index is not None:
        try:
            v = int(task.target.chapter_index)
            if start_ch <= v <= end_ch:
                return [v]
        except Exception:
            pass

    # For segment_complete, we should NOT fall back to all missing chapters
    # as completion mode is meant for bounded suffixes only.
    # The task should carry explicit chapter_range/selection.
    if task.task_type == "segment_complete":
        # Return empty to signal missing range; caller will handle as error
        return []

    missing = _volume_missing_chapter_indexes(all_vols, volume_index)
    return missing


def _build_segment_shared_context(novel_id, volume_index, batch_indexes):
    """組裝分段生成/補全共用的上下文：世界觀、鄰近卷概要、預計算伏筆線索。"""
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = select_worldview_context(wb["content"], current_stage="volume_skeleton") if wb else "尚無世界觀設定"
    worldview_parsed = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}

    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")

    base_surrounding_context = ""
    pre_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index - 1), None)
    next_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index + 1), None)
    if pre_vol:
        base_surrounding_context += f"\n【前 1 卷 (卷 {volume_index - 1}) 大綱概要】\n{pre_vol.get('summary', '')}\n"
    if next_vol:
        base_surrounding_context += f"\n【後 1 卷 (卷 {volume_index + 1}) 大綱概要】\n{next_vol.get('summary', '')}\n"

    surrounding_context = base_surrounding_context + _build_nearby_skeleton_context(current_vol, batch_indexes)

    # 預計算伏筆/轉折線索（沿用 run_volume_skeleton_planner 內部邏輯）
    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)
    foreshadowing_allocations = blueprint.get("foreshadowing_allocations", [])
    turning_allocations = blueprint.get("turning_allocations", [])

    def build_precalc_clues(batch_idxs):
        batch_set = set(batch_idxs)
        assigned = {c: {"plants": [], "payoffs": [], "turns": []} for c in batch_idxs}
        for idx, seed in enumerate(all_seeds if isinstance(all_seeds, list) else []):
            if idx >= len(foreshadowing_allocations):
                continue
            try:
                P, R = foreshadowing_allocations[idx]
            except Exception:
                continue
            if P in batch_set:
                R_vol_idx = db.get_chapter_volume_index(all_vols, R)
                assigned[P]["plants"].append(f"[Seed-{idx+1}] {seed}。未來第 {R_vol_idx} 卷（第 {R} 章）回收。")
            if R in batch_set:
                P_vol_idx = db.get_chapter_volume_index(all_vols, P)
                assigned[R]["payoffs"].append(f"[Seed-{idx+1}] {seed}。此前第 {P_vol_idx} 卷（第 {P} 章）已埋設。")
        for jdx, turn in enumerate(all_turns if isinstance(all_turns, list) else []):
            if jdx >= len(turning_allocations):
                continue
            K = turning_allocations[jdx]
            if K in batch_set:
                assigned[K]["turns"].append(f"[Turn-{jdx+1}] {turn}")
        lines = []
        for c in batch_idxs:
            tasks = assigned[c]
            if tasks["plants"] or tasks["payoffs"] or tasks["turns"]:
                lines.append(f"- 第 {c} 章任務要求：")
                for p in tasks["plants"]:
                    lines.append(f"  * foreshadowing_plants: {p}")
                for rf in tasks["payoffs"]:
                    lines.append(f"  * foreshadowing_payoffs: {rf}")
                for t in tasks["turns"]:
                    lines.append(f"  * turning_points: {t}")
        if lines:
            return "【Python 預先計算好的本段章節伏筆與轉折硬性操作安排】\n" + "\n".join(lines)
        return "【Python 預先計算好的本段章節伏筆與轉折硬性操作安排】\n本段章節無特殊伏筆或轉折任務。"

    precalc_clues = build_precalc_clues(batch_indexes)
    return worldview_text, current_vol, surrounding_context, precalc_clues


def _persist_segment_and_emit(novel_id, volume_index, chapters_skeleton, total_batches_planned, batch_idx):
    """
    將本段骨架寫入 DB，並 yield 進度 + 即時回填事件。
    回傳 (saved_count, full_text_placeholder) 供後續 last_agent_run 記錄。
    """
    saved = 0
    if chapters_skeleton:
        canonical_map = db.apply_canonical_allocated_tasks_to_chapters(novel_id, chapters_skeleton)
        chapters_skeleton = list(canonical_map.values())
        chapters_skeleton.sort(key=lambda ch: int(ch.get("chapter_index", 0)))
        db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
        saved = len(chapters_skeleton)
        yield _emit_status(f"第 {volume_index} 卷 分段進度 {batch_idx}/{total_batches_planned}：已生成 {saved} 章並寫入資料庫。")
        yield _emit_partial_state(novel_id, volume_index)
    else:
        yield _emit_status(f"第 {volume_index} 卷 分段進度 {batch_idx}/{total_batches_planned}：本段未取得有效章節。")
    return saved


def run_volume_skeleton_segment(task, context=None):
    """
    分段生成 runner（segment_generate）：只生成總監指定的單一段章節。
    生成後立即寫入 DB 並 yield partial_state + status，最後 yield done 結束本次 task。
    沒有 while 迴圈；下一段由總監在前端看到 done 後再次派發。
    """
    from backend.models.parsers import extract_json_block
    novel_id = task.novel_id
    volume_index = resolve_single_volume_index(task)
    volume_index = int(volume_index)

    # 前置角色數量檢查（沿用既有保護）
    char_data = db.get_latest_characters(novel_id)
    char_count = 0
    if char_data and char_data.get("json_data"):
        try:
            parsed_chars = json.loads(char_data["json_data"]) if isinstance(char_data["json_data"], str) else char_data["json_data"]
            char_count = len(parsed_chars.get("characters", []))
        except Exception:
            char_count = 0
    MIN_CHARS_FOR_SKELETON = 3
    if char_count < MIN_CHARS_FOR_SKELETON:
        msg = f"第 {volume_index} 卷分段生成前偵測到角色數量不足（目前 {char_count} 位，建議至少 {MIN_CHARS_FOR_SKELETON} 位）。"
        yield "data: " + json.dumps({"type": "need_characters", "volume_index": volume_index, "current_char_count": char_count, "minimum_required": MIN_CHARS_FOR_SKELETON, "message": msg}, ensure_ascii=False) + "\n\n"
        yield _emit_status(msg)
        db.save_chat_message(novel_id, "assistant", msg, message_type="pipeline")
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    batch_indexes = _resolve_segment_chapter_range(task, volume_index)
    if not batch_indexes:
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷分段生成：本段範圍已無缺失章節。", message_type="pipeline")
        yield _emit_status(f"第 {volume_index} 卷分段生成：本段範圍已完整，無需生成。")
        yield "data: " + json.dumps({"type": "content", "delta": f"第 {volume_index} 卷本段範圍已完整。"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    batch_start, batch_end = min(batch_indexes), max(batch_indexes)
    batch_count = len(batch_indexes)

    worldview_text, current_vol, surrounding_context, precalc_clues = _build_segment_shared_context(novel_id, volume_index, batch_indexes)

    db.save_chat_message(novel_id, "user", f"分段生成第 {volume_index} 卷骨架。本段章節：{batch_indexes[:80]}", message_type="pipeline")

    yield _emit_status(f"🏗️ 第 {volume_index} 卷 分段生成中：第 {batch_start}-{batch_end} 章（共 {batch_count} 章）…")

    batch_prompt = (
        f"{prompt or '請生成本段缺失章節骨架。'}\n\n"
        f"【本次後端分段任務】只輸出第 {batch_start} 至第 {batch_end} 章，"
        f"且實際必須包含這些 chapter_index：{batch_indexes}。不得輸出範圍外章節，不得重寫已存在章節。"
    )
    messages = build_volume_skeleton_planner_messages(
        worldview_text, volume_index, current_vol, batch_start, batch_end, batch_count,
        surrounding_context, precalc_clues, batch_prompt
    )

    observed_full_text = ""
    for attempt in range(1, VOLUME_SKELETON_SEGMENT_RETRIES + 1):
        yield _emit_status(f"第 {volume_index} 卷 分段生成：第 {batch_start}-{batch_end} 章（第 {attempt} 次嘗試）…")
        stream = call_llm_stream("volume_skeleton", messages, stream=task.options.stream, force_json=True)
        accumulated = []
        saw_error = False
        for chunk in stream:
            if chunk.startswith("data:"):
                try:
                    data = json.loads(chunk[5:].strip())
                    if data.get("type") == "done":
                        continue
                    if data.get("type") == "content":
                        accumulated.append(data.get("delta", ""))
                    elif data.get("type") == "error":
                        saw_error = True
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            yield chunk

        full_text = "".join(accumulated)
        observed_full_text = full_text
        if full_text.strip() and _handle_director_context_request(novel_id, "篇卷骨架規劃師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "篇卷骨架規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return
        if not full_text.strip() or saw_error:
            if attempt >= VOLUME_SKELETON_SEGMENT_RETRIES:
                yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷分段 {batch_start}-{batch_end} 生成失敗，未取得有效內容。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return
            continue

        parsed_skeleton = extract_json_block(full_text)
        chapters_skeleton = _extract_chapters_in_range(parsed_skeleton, batch_indexes)
        if chapters_skeleton:
            gen = _persist_segment_and_emit(novel_id, volume_index, chapters_skeleton, total_batches_planned=1, batch_idx=1)
            for c in gen:
                yield c
            break

        # 解析失敗重試
        all_vols_after = db.get_volumes(novel_id)
        still_missing = set(_volume_missing_chapter_indexes(all_vols_after, volume_index))
        batch_missing = [idx for idx in batch_indexes if idx in still_missing]
        if not batch_missing:
            yield _emit_status(f"第 {volume_index} 卷 分段 {batch_start}-{batch_end} 已存在於資料庫，跳過。")
            break
        if attempt >= VOLUME_SKELETON_SEGMENT_RETRIES:
            yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷分段 {batch_start}-{batch_end} 仍缺失章節：{batch_missing}。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

    db.save_last_agent_run(novel_id, "volume_skeleton", json.dumps(messages, ensure_ascii=False, indent=2), observed_full_text)
    db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷分段生成完成：第 {batch_start}-{batch_end} 章。", message_type="pipeline")
    yield _emit_status(f"✅ 第 {volume_index} 卷分段生成完成：第 {batch_start}-{batch_end} 章。")
    yield "data: " + json.dumps({"type": "content", "delta": f"\n第 {volume_index} 卷分段生成完成：第 {batch_start}-{batch_end} 章。\n"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


def run_volume_skeleton_completion(task, context=None):
    """
    分段補全 runner（segment_complete）：以已生成前段為脈絡，用 completion 模式
    補全剩餘章節。生成後立即寫入 DB 並 yield partial_state + status，最後 done。
    """
    from backend.models.parsers import extract_json_block
    novel_id = task.novel_id
    volume_index = resolve_single_volume_index(task)
    volume_index = int(volume_index)
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()

    batch_indexes = _resolve_segment_chapter_range(task, volume_index)
    if not batch_indexes:
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷補全：本段範圍已無缺失章節。", message_type="pipeline")
        yield _emit_status(f"第 {volume_index} 卷補全：本段範圍已完整，無需補全。")
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    batch_start, batch_end = min(batch_indexes), max(batch_indexes)
    batch_count = len(batch_indexes)

    worldview_text, current_vol, surrounding_context, precalc_clues = _build_segment_shared_context(novel_id, volume_index, batch_indexes)

    # 讀取已生成的前段章節（chapter_index < batch_start），作為 completion 前綴脈絡
    prior_chapters = []
    raw_outline = current_vol.get("chapters_outline")
    if isinstance(raw_outline, str):
        try:
            raw_outline = json.loads(raw_outline)
        except Exception:
            raw_outline = []
    if isinstance(raw_outline, list):
        for ch in raw_outline:
            idx = chapter_index_or_none(ch)
            if idx is not None and idx < batch_start:
                prior_chapters.append(ch)
    prior_chapters.sort(key=lambda ch: int(ch.get("chapter_index", 0)))
    prior_chapters = prior_chapters[-VOLUME_SKELETON_COMPLETION_PREFIX_LIMIT:]
    prior_segment_json = json.dumps(prior_chapters, ensure_ascii=False, indent=2) if prior_chapters else "[]"

    db.save_chat_message(novel_id, "user", f"分段補全第 {volume_index} 卷骨架。補全章節：{batch_indexes[:80]}，前段已生成 {len(prior_chapters)} 章。", message_type="pipeline")

    yield _emit_status(f"🏗️ 第 {volume_index} 卷 分段補全中（completion）：第 {batch_start}-{batch_end} 章，銜接前段 {len(prior_chapters)} 章…")

    messages = build_volume_skeleton_completion_messages(
        worldview_text, volume_index, current_vol, batch_start, batch_end, batch_count,
        surrounding_context, precalc_clues, prompt, prior_segment_json
    )

    observed_full_text = ""
    for attempt in range(1, VOLUME_SKELETON_SEGMENT_RETRIES + 1):
        yield _emit_status(f"第 {volume_index} 卷 補全：第 {batch_start}-{batch_end} 章（第 {attempt} 次嘗試，銜接前段）…")
        stream = call_llm_stream("volume_skeleton", messages, stream=task.options.stream, force_json=True)
        accumulated = []
        saw_error = False
        for chunk in stream:
            if chunk.startswith("data:"):
                try:
                    data = json.loads(chunk[5:].strip())
                    if data.get("type") == "done":
                        continue
                    if data.get("type") == "content":
                        accumulated.append(data.get("delta", ""))
                    elif data.get("type") == "error":
                        saw_error = True
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            yield chunk

        full_text = "".join(accumulated)
        observed_full_text = full_text
        if full_text.strip() and _handle_director_context_request(novel_id, "篇卷骨架規劃師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "篇卷骨架規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return
        if not full_text.strip() or saw_error:
            if attempt >= VOLUME_SKELETON_SEGMENT_RETRIES:
                yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷補全 {batch_start}-{batch_end} 失敗，未取得有效內容。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return
            continue

        parsed_skeleton = extract_json_block(full_text)
        chapters_skeleton = _extract_chapters_in_range(parsed_skeleton, batch_indexes)
        if chapters_skeleton:
            gen = _persist_segment_and_emit(novel_id, volume_index, chapters_skeleton, total_batches_planned=1, batch_idx=1)
            for c in gen:
                yield c
            break

        all_vols_after = db.get_volumes(novel_id)
        still_missing = set(_volume_missing_chapter_indexes(all_vols_after, volume_index))
        batch_missing = [idx for idx in batch_indexes if idx in still_missing]
        if not batch_missing:
            yield _emit_status(f"第 {volume_index} 卷 補全 {batch_start}-{batch_end} 已存在於資料庫，跳過。")
            break
        if attempt >= VOLUME_SKELETON_SEGMENT_RETRIES:
            yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷補全 {batch_start}-{batch_end} 仍缺失章節：{batch_missing}。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

    db.save_last_agent_run(novel_id, "volume_skeleton", json.dumps(messages, ensure_ascii=False, indent=2), observed_full_text)
    db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷分段補全完成：第 {batch_start}-{batch_end} 章（completion 銜接前段 {len(prior_chapters)} 章）。", message_type="pipeline")
    yield _emit_status(f"✅ 第 {volume_index} 卷補全完成：第 {batch_start}-{batch_end} 章。")
    yield "data: " + json.dumps({"type": "content", "delta": f"\n第 {volume_index} 卷補全完成：第 {batch_start}-{batch_end} 章。\n"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"






def _normalize_chapter_list(chapters):
    normalized = []
    for idx, ch in enumerate(chapters or []):
        if not isinstance(ch, dict):
            continue
        item = dict(ch)
        try:
            raw_idx = item.get("chapter_index") or item.get("chapter") or item.get("chapter_number") or item.get("index") or item.get("id") or (idx + 1)
            item["chapter_index"] = int(raw_idx)
        except Exception:
            item["chapter_index"] = idx + 1
        normalized.append(item)
    normalized.sort(key=lambda x: x["chapter_index"])
    return normalized

def _extract_incremental_skeleton_chapters(parsed):
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return []
    for key in ("chapters_skeleton", "chapter_patches", "chapters", "patches"):
        value = parsed.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    for key in ("chapter", "chapter_patch", "skeleton"):
        value = parsed.get(key)
        if isinstance(value, dict):
            return [value]
    if parsed.get("chapter_index") is not None:
        return [parsed]
    return []


def _collect_volume_skeleton_chapters(novel_id):
    skeleton_chapters = []
    for vol in db.get_volumes(novel_id):
        ch_list = vol.get("chapters_outline")
        if isinstance(ch_list, list):
            skeleton_chapters.extend(ch_list)
    return _normalize_chapter_list(skeleton_chapters)

