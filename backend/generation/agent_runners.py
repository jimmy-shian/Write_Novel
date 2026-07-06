# -*- coding: utf-8 -*-
"""
AI Novel Factory Agent Runner Functions
Implements the 6-stage golden axis of creation:
Worldview -> Character -> Volume -> Skeleton -> Outline -> Writing
Reinforced with JSON schemas and custom Director hooks.

職責分工（Separation of Concerns）：
- 限制規範 (Constraints)    : constraints.py
- 提示詞組裝 (Prompt Assembly): prompts/prompt_builder.py
- 校驗與結構計算 (Validation)  : validation.py
- 總監上下文 (Director Context): director_context.py
- Pipeline 路由與串流 (本檔)   : agents.py
"""

import json
import traceback
import asyncio
from functools import partial
from backend import db
from backend.services import diagnostics
import backend.services.director_context as director_context
from backend.llm import call_llm_stream

from backend.config import (
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    VOLUME_SKELETON_BATCH_SIZE,
    VOLUME_SKELETON_BATCH_RETRIES,
    VOLUME_SKELETON_SEGMENT_RETRIES,
    VOLUME_SKELETON_COMPLETION_PREFIX_LIMIT,
)
from backend.utils import deep_merge_dict, StreamAccumulator

# --- 限制規範層 (Constraints) ---
from backend.schemas.constraints import (
    load_retrospective_gold_rules,
)

# --- 校驗與結構計算層 (Validation) ---
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

# --- 提示詞組裝層 (Prompt Assembly) ---
from backend.prompts.prompt_builder import (
    get_json_schema_prompt_snippet,
    build_story_architect_messages,
    build_worldview_core_messages,
    build_multi_act_structure_messages,
    build_progressive_character_plan_messages,
    build_character_designer_messages,
    build_foreshadowing_messages,
    build_volumes_planner_messages,
    build_volume_skeleton_planner_messages,
    build_volume_skeleton_completion_messages,
    build_chapter_writer_messages,
    build_editor_agent_messages,
    build_copilot_chat_messages,
    build_director_decision_messages,
    build_director_decision_help_messages,
    build_incremental_architect_messages,
    build_incremental_character_messages,
    build_missing_character_designer_messages,
    extract_worldview_summary,
    select_worldview_context,
    mask_worldview_seeds_and_turns,
    extract_character_names_list,
    extract_character_basic,
)


# Gold rules 載入 → 已移至 constraints.py: load_retrospective_gold_rules
# 提供向後相容的私有別名供本檔內部沿用
_load_retrospective_gold_rules = load_retrospective_gold_rules



def _tool_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _infer_tool_review_range(params, fallback_start=1, fallback_end=15):
    text = " ".join(
        str(params.get(key, ""))
        for key in ("evaluation_feedback", "reason", "hint", "agent_prompt", "original_output")
    )
    for pattern in (r"(\d+)\s*[-~到至]\s*(\d+)", r"第\s*(\d+)\s*[到至]\s*(\d+)"):
        import re
        match = re.search(pattern, text)
        if match:
            try:
                start = max(1, int(match.group(1)))
                end = max(start, int(match.group(2)))
                return start, end
            except Exception:
                pass
    try:
        start = int(params.get("start_index") or fallback_start)
    except Exception:
        start = fallback_start
    try:
        end = int(params.get("end_index") or fallback_end)
    except Exception:
        end = fallback_end
    return max(1, start), max(max(1, start), end)


def _latest_stage_output_for_tool_review(novel_id, stage_name):
    stage = (stage_name or "").strip()
    if stage in ("worldview", "foreshadowing"):
        wb = db.get_latest_worldbuilding(novel_id)
        return wb["content"] if wb else ""
    if stage == "characters":
        char = db.get_latest_characters(novel_id)
        if not char:
            return ""
        return char.get("json_data") or _tool_json(char.get("parsed_data") or {})
    if stage == "volumes":
        return _tool_json({"volumes": db.get_volumes(novel_id)})
    if stage == "volume_skeleton":
        return _tool_json({"volumes": db.get_volumes(novel_id)})
    return ""


def _build_tool_followup_context(tool_name, params, tool_result, post_tool_audit=None):
    return (
        "【總監工具執行結果 - 必須二次評判】\n"
        f"tool_name: {tool_name}\n"
        f"parameters:\n{_tool_json(params)}\n\n"
        f"tool_result:\n{_tool_json(tool_result)}\n\n"
        f"post_tool_audit:\n{_tool_json(post_tool_audit or {})}\n\n"
        "請你根據最新資料庫狀態、validation_report、post_tool_audit 與必要的展開內容重新判斷。\n"
        "如果補強後內容仍未達標，禁止輸出 WAIT_USER 或 FINISH；請使用 TOOL_CALL 繼續展開/補強，或用 CONTINUE/AUTO_REGENERATE/GO_BACK_* 派發正確階段。\n"
        "只有在硬性校驗與你實際展開審查的內容都確認已合格，才可以放行或等待使用者。"
    )


def _run_director_followup_after_tool(
    novel_id,
    current_stage,
    user_prompt,
    extra_context,
    tool_context,
    chapter_index,
    volume_index,
    suggested_next_chapter,
    conversation_context,
    summary_context,
    loop_count,
    stream,
    force_json,
):
    combined_extra = "\n\n".join(part for part in (extra_context, tool_context) if part)
    yield "data: " + json.dumps({
        "type": "status",
        "message": "工具執行完成，正在請總監依更新後資料二次評判..."
    }, ensure_ascii=False) + "\n\n"
    yield from run_director_decision(
        novel_id,
        current_stage=current_stage,
        user_prompt=user_prompt,
        chapter_index=chapter_index,
        volume_index=volume_index,
        suggested_next_chapter=suggested_next_chapter,
        conversation_context=conversation_context,
        summary_context=summary_context,
        extra_context=combined_extra,
        loop_count=loop_count + 1,
        stream=stream,
        force_json=force_json,
    )

import time

async def safe_generator_wrapper(gen, novel_id=None):
    """
    Async wrapper around a sync generator.
    - Detects client disconnect (asyncio.CancelledError) and closes the generator cleanly.
    - Prevents exceptions from propagating after data has been yielded.
    - If it raises before yielding anything, re-raises so FastAPI can send a proper error response.
    - Optionally sends heartbeat SSE events and updates DB heartbeat every 60s.
    """
    loop = asyncio.get_running_loop()
    has_yielded = False
    sentinel = object()
    last_heartbeat = time.time() if novel_id else None
    HEARTBEAT_INTERVAL = 60
    try:
        while True:
            chunk = await loop.run_in_executor(None, partial(next, gen, sentinel))
            if chunk is sentinel:
                break
            has_yielded = True
            yield chunk
            if novel_id and last_heartbeat is not None:
                now = time.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    last_heartbeat = now
                    try:
                        db.update_pipeline_heartbeat(novel_id)
                    except Exception:
                        pass
                    yield "data: " + json.dumps({"type": "heartbeat"}, ensure_ascii=False) + "\n\n"
    except asyncio.CancelledError:
        print("[SAFE_WRAPPER] Client disconnected, stopping generator.")
        try:
            gen.close()
        except (ValueError, RuntimeError):
            pass
    except Exception as e:
        print(f"[SAFE_WRAPPER] Generator raised: {e}")
        traceback.print_exc()
        if has_yielded:
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"伺服器內部錯誤（串流後處理失敗）: {str(e)}"
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        else:
            raise


# =============================================================================
# 1. Worldview Agent (Story Architect)
# =============================================================================
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
    existing_chars_json = existing_char_data["json_data"] if existing_char_data and mode != "generate" else "{'characters': []}"
    
    # 💡 安全防護：如果角色聖經已存在，只做增量/修補，不允許全量重跑覆蓋
    if mode == "generate" and existing_char_data:
        try:
            parsed_chars = json.loads(existing_chars_json)
            if parsed_chars.get("characters") and len(parsed_chars["characters"]) > 0:
                print(f"[CHARACTER DESIGNER] Characters already exist. Falling back to expand mode to prevent wipe.")
                mode = "expand"
                if not hint:
                    hint = "請在現有角色基礎上進行補充或優化設定，不要刪除或重置既有角色。"
        except Exception:
            pass

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


def _extract_director_context_request(content):
    """從 Agent 回傳內容中檢查是否包含「需要總監補充上下文」的請求標記。"""
    parsed = extract_worldview_dict_preserving(content)
    if not isinstance(parsed, dict):
        return ""
    if not (parsed.get("_needs_director_context") or parsed.get("needs_director_context") or parsed.get("context_request")):
        return ""
    request = parsed.get("context_request") or parsed.get("reason") or "下游 Agent 回報資料不足，需要總監補充上下文。"
    missing = parsed.get("missing_data") or []
    if isinstance(missing, list) and missing:
        request += "\n缺少資料：" + "、".join(str(item) for item in missing)
    risk = parsed.get("why_it_blocks_generation")
    if risk:
        request += f"\n阻斷原因：{risk}"
    return request.strip()


def _handle_director_context_request(novel_id, agent_label, full_text):
    """若 Agent 輸出包含 context_request 標記，記錄訊息並回傳 True 以中止保存。"""
    request = _extract_director_context_request(full_text)
    if not request:
        return False
    message = f"{agent_label} 已暫停保存：需要總監補充上下文後再生成。\n{request}"
    db.save_chat_message(novel_id, "assistant", message, message_type="pipeline")
    return True


# =============================================================================
# 2.5 Foreshadowing Orchestrator Agent
# =============================================================================
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


def run_volumes_planner(novel_id, user_prompt=None, hint=None, mode="generate", target_vol_idx=None, stream=False, force_json=False):
    """
    Volumes Planner Stage:
    - Mode 'generate': Generate volumes list based on worldview summary + outline of preceding & succeeding 1 volumes.
    - Mode 'patch': Volume patch/add: passes hint and specifies generating only `[idx]`.
    """
    wb = db.get_latest_worldbuilding(novel_id)
    # generate 模式傳入完整世界觀讓 LLM 自行決定卷數與章數分配
    worldview_text = select_worldview_context(wb["content"], current_stage="volumes") if wb else "尚無世界觀設定"
    
    existing_vols = [] if mode == "generate" else db.get_volumes(novel_id)
    
    messages = build_volumes_planner_messages(worldview_text, existing_vols, user_prompt, hint, mode, target_vol_idx)
    
    db.save_chat_message(novel_id, "user", f"執行篇卷規劃。模式: {mode}, 卷數: {target_vol_idx or '全書'}", message_type="pipeline")
    
    stream = call_llm_stream("volumes", messages, stream=stream, force_json=force_json) # Map to volumes model for volumes planning
    acc = StreamAccumulator(stream)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    if full_text.strip():
        if _handle_director_context_request(novel_id, "篇卷規劃師", full_text):
            yield "data: " + json.dumps({"type": "error", "message": "篇卷規劃師需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            return
        # Parse and save volumes
        from backend.models.parsers import extract_json_block
        parsed_vols = extract_json_block(full_text)
        vols_list = parsed_vols.get("volumes", []) if isinstance(parsed_vols, dict) else (parsed_vols if isinstance(parsed_vols, list) else [])
        
        if vols_list:
            adjusted_vols = []
            for i, vol in enumerate(vols_list):
                try:
                    vol_idx = int(vol.get("volume_index", i + 1))
                except Exception:
                    vol_idx = i + 1
                vol["volume_index"] = vol_idx
                try:
                    vol["chapter_count"] = int(vol.get("chapter_count", 0))
                except Exception:
                    vol["chapter_count"] = 0
                adjusted_vols.append(vol)

            validation_error = _volume_plan_validation_error(adjusted_vols, mode=mode)
            if validation_error:
                error_message = f"篇卷規劃生成失敗：{validation_error}。請重新生成，不會保存本次不合規輸出。"
                db.save_chat_message(novel_id, "assistant", error_message, message_type="pipeline")
                yield "data: " + json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n\n"
                return

            if mode == "patch" and target_vol_idx is not None:
                # Patch mode: upsert only the target volume, preserve all others
                db.save_volumes(novel_id, adjusted_vols, clear_downstream=False, target_vol_idx=target_vol_idx)
            else:
                db.save_volumes(novel_id, adjusted_vols, clear_downstream=True)
            
            # 預計算全局伏筆與轉折藍圖
            try:
                db.precompute_global_foreshadowing(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to precompute global foreshadowing in run_volumes_planner: {e}")
                
        db.save_last_agent_run(novel_id, "volumes", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"篇卷結構已儲存成功！", message_type="pipeline")


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
    Volume Skeleton Stage — 單卷骨架生成。
    每次只處理一卷，卷的派發順序由總監決定（透過 CONTINUE + volume_index）。
    在開始生成前先檢查角色數量是否足夠；若不足，yield need_characters 事件供前端/總監偵測並退回補充。
    內部採用小批次生成方式，避免單次大量輸出截斷。
    """
    # --- 前置角色數量檢查 ---
    char_data = db.get_latest_characters(novel_id)
    char_count = 0
    if char_data and char_data.get("json_data"):
        try:
            parsed_chars = json.loads(char_data["json_data"]) if isinstance(char_data["json_data"], str) else char_data["json_data"]
            char_count = len(parsed_chars.get("characters", []))
        except Exception:
            char_count = 0
    MIN_CHARS_FOR_SKELETON = 3  # 至少需要3個角色才能生成有意義的骨架
    if char_count < MIN_CHARS_FOR_SKELETON:
        msg = f"第 {volume_index} 卷骨架生成前偵測到角色數量不足（目前 {char_count} 位，建議至少 {MIN_CHARS_FOR_SKELETON} 位）。"
        yield "data: " + json.dumps({
            "type": "need_characters",
            "volume_index": int(volume_index),
            "current_char_count": char_count,
            "minimum_required": MIN_CHARS_FOR_SKELETON,
            "message": msg
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "status", "message": msg}, ensure_ascii=False) + "\n\n"
        db.save_chat_message(novel_id, "assistant", msg, message_type="pipeline")
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return
    from backend.models.parsers import extract_json_block

    volume_index = int(volume_index)
    wb = db.get_latest_worldbuilding(novel_id)
    worldview_text = select_worldview_context(wb["content"], current_stage="volume_skeleton") if wb else "尚無世界觀設定"
    worldview_parsed = db.parse_worldview_to_json(wb["content"] if wb else "") if wb else {}

    all_vols = db.get_volumes(novel_id)
    current_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index), None)
    if not current_vol:
        raise ValueError(f"Volume index {volume_index} not found!")

    start_ch, end_ch = db.get_volume_chapter_range(all_vols, volume_index)
    requested_indexes = _parse_requested_chapter_indexes(user_prompt, start_ch, end_ch)
    missing_indexes = _volume_missing_chapter_indexes(all_vols, volume_index)
    if requested_indexes:
        missing_indexes = [idx for idx in requested_indexes if idx in set(missing_indexes)]

    if not missing_indexes:
        db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷骨架已完整，沒有需要補生成的章節。", message_type="pipeline")
        yield "data: " + json.dumps({"type": "content", "delta": f"第 {volume_index} 卷骨架已完整，沒有需要補生成的章節。"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return

    pre_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index - 1), None)
    next_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index + 1), None)
    base_surrounding_context = ""
    if pre_vol:
        base_surrounding_context += f"\n【前 1 卷 (卷 {volume_index - 1}) 大綱概要】\n{pre_vol.get('summary', '')}\n"
    if next_vol:
        base_surrounding_context += f"\n【後 1 卷 (卷 {volume_index + 1}) 大綱概要】\n{next_vol.get('summary', '')}\n"

    all_seeds = worldview_parsed.get("foreshadowing_seeds", [])
    all_turns = worldview_parsed.get("key_turning_points", [])
    blueprint = db.get_global_foreshadowing_blueprint(novel_id)
    foreshadowing_allocations = blueprint.get("foreshadowing_allocations", [])
    turning_allocations = blueprint.get("turning_allocations", [])

    def build_precalc_clues(batch_indexes):
        batch_set = set(batch_indexes)
        assigned = {c: {"plants": [], "payoffs": [], "turns": []} for c in batch_indexes}
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
        for c in batch_indexes:
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
            return "【Python 預先計算好的本批章節伏筆與轉折硬性操作安排】\n" + "\n".join(lines)
        return "【Python 預先計算好的本批章節伏筆與轉折硬性操作安排】\n本批章節無特殊伏筆或轉折任務。"

    remaining = list(missing_indexes)
    total_saved = 0
    batches_done = 0
    db.save_chat_message(
        novel_id,
        "user",
        f"生成第 {volume_index} 卷骨架大綱。缺失章節：{remaining[:80]}{'...' if len(remaining) > 80 else ''}",
        message_type="pipeline"
    )

    while remaining:
        # Re-fetch from DB to ensure we have the most up-to-date outline state
        all_vols = db.get_volumes(novel_id)
        current_missing = _volume_missing_chapter_indexes(all_vols, volume_index)
        if requested_indexes:
            current_missing = [idx for idx in requested_indexes if idx in set(current_missing)]
        remaining = current_missing
        if not remaining:
            break
            
        batch = _split_consecutive_batches(remaining)[0]
        for attempt in range(1, VOLUME_SKELETON_BATCH_RETRIES + 1):
            all_vols = db.get_volumes(novel_id)
            current_vol = next((v for v in all_vols if int(v.get("volume_index", 0)) == volume_index), current_vol)
            batch_start, batch_end = min(batch), max(batch)
            batch_count = len(batch)
            surrounding_context = base_surrounding_context + _build_nearby_skeleton_context(current_vol, batch)
            precalc_clues = build_precalc_clues(batch)
            batch_prompt = (
                f"{user_prompt or '請生成本批缺失章節骨架。'}\n\n"
                f"【本次後端缺章修復任務】只輸出第 {batch_start} 至第 {batch_end} 章，"
                f"且實際必須包含這些 chapter_index：{batch}。不得輸出範圍外章節，不得重寫已存在章節。"
            )
            messages = build_volume_skeleton_planner_messages(
                worldview_text, volume_index, current_vol, batch_start, batch_end, batch_count,
                surrounding_context, precalc_clues, batch_prompt
            )

            yield "data: " + json.dumps({"type": "content", "delta": f"\n[骨架批次] 第 {volume_index} 卷：生成章節 {batch_start}-{batch_end}（第 {attempt} 次）\n"}, ensure_ascii=False) + "\n\n"
            stream = call_llm_stream("volume_skeleton", messages, stream=stream, force_json=force_json)
            accumulated = []
            saw_error = False
            for chunk in stream:
                # Suppress internal done events; this generator emits one final done after all batches.
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
                    yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷章節 {batch_start}-{batch_end} 生成失敗，未取得有效內容。"}, ensure_ascii=False) + "\n\n"
                    yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                    return
                continue

            parsed_skeleton = extract_json_block(full_text)
            chapters_skeleton = _extract_chapters_in_range(parsed_skeleton, batch)
            if chapters_skeleton:
                canonical_map = db.apply_canonical_allocated_tasks_to_chapters(novel_id, chapters_skeleton)
                chapters_skeleton = list(canonical_map.values())
                chapters_skeleton.sort(key=lambda ch: int(ch.get("chapter_index", 0)))
                db.update_volume_outline(novel_id, volume_index, chapters_skeleton)
                total_saved += len(chapters_skeleton)

            all_vols_after = db.get_volumes(novel_id)
            still_missing = set(_volume_missing_chapter_indexes(all_vols_after, volume_index))
            batch_missing = [idx for idx in batch if idx in still_missing]
            if not batch_missing:
                batches_done += 1
                break
            batch = batch_missing
            if attempt >= VOLUME_SKELETON_BATCH_RETRIES:
                yield "data: " + json.dumps({"type": "error", "message": f"第 {volume_index} 卷仍缺失章節：{batch_missing}。已停止，避免無限重試。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

        # Batch completed. The next iteration will re-fetch state from DB.

    db.save_last_agent_run(novel_id, "volume_skeleton", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
    db.save_chat_message(novel_id, "assistant", f"第 {volume_index} 卷缺失骨架批次補全完成，共處理 {batches_done} 批，保存/更新 {total_saved} 章。", message_type="pipeline")
    yield "data: " + json.dumps({"type": "content", "delta": f"\n第 {volume_index} 卷缺失骨架批次補全完成，共處理 {batches_done} 批。"}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


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
    if char_data_for_skeleton and char_data_for_skeleton.get("json_data"):
        try:
            existing_character_names = extract_character_names_list(char_data_for_skeleton["json_data"])
        except Exception:
            existing_character_names = []
    surrounding_context += (
        "\n【既有角色名冊與使用規則】\n"
        + json.dumps({
            "existing_character_names": existing_character_names,
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


# build_missing_character_designer_messages → 已移至 prompts/prompt_builder.py
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


GENERIC_ACTIVE_CHARACTER_MARKERS = (
    "路人", "群眾", "乘客", "學生", "同學", "老師", "教授", "導師", "守衛", "士兵",
    "特務", "警衛", "工作人員", "店員", "醫護", "司機", "記者", "眾人", "旁觀者",
    "巡邏", "黑衣人", "未知人物", "不明", "站靈", "妖魔", "傀儡", "手下", "部下",
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
def run_chapter_writer(novel_id, chapter_index, custom_style="Classic Modernism", user_prompt=None, stream=False, force_json=False):
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

    missing_active_chars = _missing_named_active_characters(current_outline, characters_bible)
    if missing_active_chars:
        missing_text = "、".join(missing_active_chars)
        decision = {
            "action": "INCREMENTAL_APPEND_CHARACTER",
            "target": "characters",
            "hint": (
                f"正文寫作第 {chapter_index} 章前偵測到章節大綱使用未建卡命名角色：{missing_text}。"
                "請根據世界觀、目前章節大綱、本卷設定與角色庫，為這些角色追加完整角色卡；"
                "補卡後重新回到原章節 writer。"
            ),
            "agent_prompt": (
                f"請追加以下缺失角色的完整角色卡：{missing_text}。"
                f"角色首次/本次使用章節為第 {chapter_index} 章，章節大綱如下："
                f"{json.dumps(current_outline, ensure_ascii=False, indent=2)}"
            ),
            "agent_context": "命名角色若沒有角色卡，不得進入正文寫作；補卡必須保存到角色庫，供後續卷章再次使用。",
            "user_intent_summary": "",
            "reason": "章節大綱引用了未存在於角色 Bible 的命名角色，若直接寫作會造成人設缺失與跨卷不一致。",
            "volume_index": curr_vol_idx,
            "chapter_index": chapter_index,
        }
        msg = f"正文寫作暫停：缺失命名角色 {missing_text}。請先追加角色卡。"
        db.save_chat_message(novel_id, "assistant", msg, message_type="pipeline")
        yield "data: " + json.dumps({"type": "error", "message": msg + "\n```json\n" + json.dumps(decision, ensure_ascii=False, indent=2) + "\n```"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
        return
        
    pre_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index - 1), None)
    nxt_ch_outline = next((ch for ch in normalized_outlines if ch["chapter_index"] == chapter_index + 1), None)
    
    # 角色上下文改由 prompt_builder 依本章大綱、前後章、伏筆線索與額外指示挑選：
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

    messages = build_chapter_writer_messages(
        worldview_text, characters_bible, current_outline, surrounding_plot,
        vol_outline_context, clue_payoff_details, custom_style, chapter_index,
        user_prompt=user_prompt
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
                
        db.save_chapter(novel_id, chapter_index, prose_val, synopsis=current_outline.get("title", f"第 {chapter_index} 章"), thinking=thinking_val)
        db.save_last_agent_run(novel_id, "writer", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文寫作完成！", message_type="pipeline")


# =============================================================================
# 7. Editor Agent
# =============================================================================
def run_editor_agent(novel_id, chapter_index, edit_instructions=None, stream=False, force_json=False):
    """
    Editor Stage:
    Polishes/edits the chapter prose using Senior Editor, replacing the original content directly.
    """
    chapter_data = db.get_latest_chapter(novel_id, chapter_index)
    if not chapter_data:
        raise ValueError(f"Chapter {chapter_index} prose not found for editing!")
        
    original_prose = chapter_data.get("content", "")
    current_synopsis = chapter_data.get("synopsis", "")
    
    messages = build_editor_agent_messages(chapter_index, edit_instructions, original_prose)
    
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
        db.save_chapter(novel_id, chapter_index, full_text, synopsis=current_synopsis)
        db.save_last_agent_run(novel_id, "editor", json.dumps(messages, ensure_ascii=False, indent=2), full_text)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已成功潤色替換！", message_type="pipeline")


# =============================================================================
# 8. Copilot / Director Orchestration
# =============================================================================
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


# =============================================================================
# 9. Director Decision Checks (Pipeline Gatekeeper)
# =============================================================================

EXECUTABLE_DIRECTOR_ACTIONS = {
    "CONTINUE",
    "AUTO_REGENERATE",
    "GO_BACK_TO_WORLDVIEW",
    "GO_BACK_TO_CHARACTERS",
    "GO_BACK_TO_SKELETON_EXPANSION",
    "WAIT_USER",
    "FINISH",
    "INCREMENTAL_MODIFY_CHARACTER",
    "INCREMENTAL_APPEND_CHARACTER",
    "INCREMENTAL_MODIFY_SKELETON",
    "INCREMENTAL_MODIFY_CHARACTER_FULL",
    "TOOL_CALL",
}


def _first_missing_skeleton_volume(novel_id):
    vols = db.get_volumes(novel_id)
    for v in sorted(vols, key=lambda item: item.get("volume_index", 0)):
        outline = v.get("chapters_outline")
        if not outline:
            return v.get("volume_index") or 1
        if isinstance(outline, str):
            try:
                outline = json.loads(outline or "[]")
            except Exception:
                return v.get("volume_index") or 1
        if not isinstance(outline, list) or len(outline) == 0:
            return v.get("volume_index") or 1
    return None


def _next_missing_chapter_index(novel_id):
    vols = db.get_volumes(novel_id)
    total_planned = sum(db._get_clean_chapter_count(v) for v in vols) if vols else 0
    if total_planned <= 0:
        total_planned = 1
    written = set()
    for ch in db.get_all_chapters_latest(novel_id):
        try:
            idx = int(ch.get("chapter_index"))
        except Exception:
            continue
        content = ch.get("content") or ""
        if len(content.strip()) >= 100 and "保底" not in content and "占位" not in content:
            written.add(idx)
    for idx in range(1, total_planned + 1):
        if idx not in written:
            return idx
    return total_planned


def _volume_for_chapter(novel_id, chapter_index):
    vols = db.get_volumes(novel_id)
    for v in sorted(vols, key=lambda item: item.get("volume_index", 0)):
        try:
            start, end = db.get_volume_chapter_range(vols, v["volume_index"])
        except Exception:
            continue
        if start <= chapter_index <= end:
            return v.get("volume_index")
    return 1 if vols else None


def _foreshadowing_counts(novel_id):
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb:
        return 0, 0
    try:
        parsed = db.parse_worldview_to_json(wb["content"])
    except Exception:
        parsed = {}
    seeds = parsed.get("foreshadowing_seeds") if isinstance(parsed, dict) else []
    turns = parsed.get("key_turning_points") if isinstance(parsed, dict) else []
    return (
        len(seeds) if isinstance(seeds, list) else 0,
        len(turns) if isinstance(turns, list) else 0,
    )


def _foreshadowing_batch_decision(novel_id, reason_prefix):
    seeds_count, turns_count = _foreshadowing_counts(novel_id)
    if seeds_count < MIN_FORESHADOWING_SEEDS:
        field = "foreshadowing_seeds"
        label = "伏筆種子"
        count_text = f"{seeds_count}/{MIN_FORESHADOWING_SEEDS}"
    elif turns_count < MIN_KEY_TURNING_POINTS:
        field = "key_turning_points"
        label = "關鍵轉折點"
        count_text = f"{turns_count}/{MIN_KEY_TURNING_POINTS}"
    else:
        return None
    prompt = (
        f"[BATCH: {field}]\n"
        f"本次只生成{label}，至少 50 個，必須嚴格輸出該批次 JSON schema；"
        "不得同時輸出另一類資料。"
    )
    return {
        "action": "CONTINUE",
        "target": "foreshadowing",
        "hint": prompt,
        "agent_prompt": prompt,
        "agent_context": f"{label}目前數量：{count_text}。{reason_prefix}",
        "user_intent_summary": "",
        "reason": f"{reason_prefix}後端依剛性門檻補正：{label}仍未達標（{count_text}），派發 foreshadowing 分批生成。",
        "volume_index": None,
        "chapter_index": None,
    }


def _build_recovery_director_decision(novel_id, current_stage, parsed):
    stage = current_stage or diagnostics.detect_current_stage(novel_id)
    reason_prefix = "總監輸出缺少可執行 action/target；"

    if stage in ("worldview", "foreshadowing"):
        batch = _foreshadowing_batch_decision(novel_id, reason_prefix)
        if batch:
            return batch
        return {
            "action": "CONTINUE",
            "target": "characters",
            "hint": "伏筆與關鍵轉折已達標，進入角色聖經生成。",
            "agent_prompt": "請根據已完成的世界觀、伏筆種子與關鍵轉折點，生成完整角色聖經。",
            "agent_context": "",
            "user_intent_summary": "",
            "reason": reason_prefix + "世界觀與伏筆層已達標，補正前往 characters。",
            "volume_index": None,
            "chapter_index": None,
        }

    detected = diagnostics.detect_current_stage(novel_id)
    if detected == "worldview":
        target = "worldview"
    elif detected == "foreshadowing":
        return _foreshadowing_batch_decision(novel_id, reason_prefix) or {
            "action": "CONTINUE", "target": "characters", "hint": "", "agent_prompt": "", "agent_context": "",
            "user_intent_summary": "", "reason": reason_prefix + "補正前往 characters。", "volume_index": None, "chapter_index": None
        }
    elif detected == "characters":
        target = "characters"
    elif detected == "volumes":
        target = "volumes"
    elif detected == "volume_skeleton":
        vol_idx = _first_missing_skeleton_volume(novel_id) or 1
        return {
            "action": "CONTINUE",
            "target": "volume_skeleton",
            "hint": f"請生成第 {vol_idx} 卷章節骨架。",
            "agent_prompt": f"請生成第 {vol_idx} 卷章節骨架。",
            "agent_context": "",
            "user_intent_summary": "",
            "reason": reason_prefix + f"補正前往第 {vol_idx} 卷 volume_skeleton。",
            "volume_index": vol_idx,
            "chapter_index": None,
        }
    elif detected == "writer":
        chapter_idx = _next_missing_chapter_index(novel_id)
        return {
            "action": "CONTINUE",
            "target": "writer",
            "hint": f"請撰寫第 {chapter_idx} 章正文。",
            "agent_prompt": f"請撰寫第 {chapter_idx} 章正文。",
            "agent_context": "",
            "user_intent_summary": "",
            "reason": reason_prefix + f"補正前往 writer 第 {chapter_idx} 章。",
            "volume_index": _volume_for_chapter(novel_id, chapter_idx),
            "chapter_index": chapter_idx,
        }
    else:
        target = "editor"

    return {
        "action": "CONTINUE",
        "target": target,
        "hint": "",
        "agent_prompt": "",
        "agent_context": "",
        "user_intent_summary": "",
        "reason": reason_prefix + f"依偵測階段補正前往 {target}。",
        "volume_index": None,
        "chapter_index": None,
    }


def _director_decision_needs_recovery(parsed):
    if not isinstance(parsed, dict):
        return True
    action = str(parsed.get("action") or "").upper().strip()
    if action not in EXECUTABLE_DIRECTOR_ACTIONS:
        return True
    if action in {"CONTINUE", "AUTO_REGENERATE"} and not parsed.get("target"):
        return True
    target = str(parsed.get("target") or "").lower()
    text = json.dumps(parsed, ensure_ascii=False)
    if action == "CONTINUE" and target == "foreshadowing" and not re_search_batch_marker(text):
        return True
    return False


def _record_director_review_status(novel_id, current_stage, parsed, volume_index=None, chapter_index=None):
    if not isinstance(parsed, dict):
        return
    action = str(parsed.get("action") or "").upper().strip()
    if action == "TOOL_CALL" or "tool_call" in parsed:
        status = "inspecting"
        tool_call = parsed.get("tool_call") or {}
        block_name = (tool_call.get("parameters") or {}).get("block_name")
    elif action in {"CONTINUE", "FINISH"}:
        status = "approved"
        block_name = None
    elif action == "WAIT_USER":
        status = "blocked"
        block_name = None
    else:
        status = "needs_revision"
        block_name = None
    try:
        db.save_director_review_status(
            novel_id,
            current_stage,
            status,
            block_name=block_name,
            volume_index=volume_index,
            chapter_index=chapter_index,
            reason=parsed.get("reason") or parsed.get("hint") or "",
            decision_json=parsed,
        )
    except Exception as exc:
        print(f"[WARN] Failed to save director review status: {exc}")


def re_search_batch_marker(text):
    import re
    return bool(re.search(r"\[BATCH:\s*(foreshadowing_seeds|key_turning_points)\]", text or "", flags=re.IGNORECASE))


def run_director_decision(
    novel_id,
    current_stage,
    user_prompt,
    chapter_index=None,
    volume_index=None,
    character_review_mode=None,
    character_review_hint=None,
    character_review_target_content=None,
    suggested_next_chapter=None,
    conversation_context=None,
    summary_context=None,
    extra_context=None,
    loop_count=0,
    stream=False,
    force_json=False
):
    """
    Gateway review after a stage completes. Returns next action:
    CONTINUE, GO_BACK_TO_WORLDVIEW, GO_BACK_TO_CHARACTERS, GO_BACK_TO_PLOT, WAIT_USER, FINISH.
    """
    detected_stage = diagnostics.detect_current_stage(novel_id)
    if not current_stage or current_stage == "init":
        current_stage = detected_stage
    else:
        STAGES_ORDER = ["worldview", "foreshadowing", "characters", "volumes", "volume_skeleton", "writer", "editor"]
        try:
            detected_idx = STAGES_ORDER.index(detected_stage)
            current_idx = STAGES_ORDER.index(current_stage) if current_stage in STAGES_ORDER else -1
            if detected_idx < current_idx or current_idx == -1:
                print(f"[STAGE OVERRIDE] Override current_stage from '{current_stage}' to '{detected_stage}' due to incomplete database state.")
                current_stage = detected_stage
        except Exception:
            current_stage = detected_stage
    wb = db.get_latest_worldbuilding(novel_id)
    MAX_DIRECTOR_WORLDVIEW_CHARS = 60000 if current_stage == "worldview" else 30000
    worldview_text = select_worldview_context(wb["content"], current_stage=current_stage, query_text=user_prompt or "", limit=MAX_DIRECTOR_WORLDVIEW_CHARS) if wb else "尚無世界觀設定"
    if current_stage not in ("foreshadowing", "worldview"):
        try:
            worldview_text = mask_worldview_seeds_and_turns(worldview_text)
        except Exception:
            pass
    if len(worldview_text) > MAX_DIRECTOR_WORLDVIEW_CHARS:
        print(f"[WARN] Director worldview emergency-truncated from {len(worldview_text)} to {MAX_DIRECTOR_WORLDVIEW_CHARS} chars for novel {novel_id}")
        if current_stage != "worldview":
            try:
                parsed = json.loads(worldview_text)
                from backend.prompts.prompt_builder import compact_json_data
                compacted = compact_json_data(parsed, max_list_items=5)
                worldview_text = json.dumps(compacted, ensure_ascii=False, indent=2)
            except Exception:
                pass
        if len(worldview_text) > MAX_DIRECTOR_WORLDVIEW_CHARS:
            worldview_text = worldview_text[:MAX_DIRECTOR_WORLDVIEW_CHARS] + "\n...[世界觀已截斷]"
    char_data = db.get_latest_characters(novel_id)
    characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    
    if chapter_index is not None:
        try:
            chapter_index = int(chapter_index)
        except (ValueError, TypeError):
            chapter_index = None
            
    plot_text = ""
    written_chapters_text = ""
    
    if current_stage == "worldview":
        plot_text = "世界觀審查階段"
    elif current_stage == "characters":
        plot_text = "角色審查階段"
    elif current_stage == "foreshadowing":
        plot_text = "伏筆與轉折編織審查階段"
    elif current_stage == "volumes":
        vols = db.get_volumes(novel_id)
        simplified_vols = []
        for v in vols:
            v_copy = dict(v)
            if "chapters_outline" in v_copy:
                if isinstance(v_copy["chapters_outline"], list):
                    v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                else:
                    v_copy["chapters_outline"] = "尚未生成骨架"
            simplified_vols.append(v_copy)
        plot_text = json.dumps(simplified_vols, ensure_ascii=False, indent=2) if vols else "尚無篇卷規劃"
        allocation_context = director_context.build_foreshadowing_allocation_context(
            novel_id,
            scope="summary",
        )
        plot_text += "\n\n【Python 預計算伏筆/轉折分配總表（總監審核唯一依據）】\n"
        plot_text += json.dumps(allocation_context, ensure_ascii=False, indent=2)
    elif current_stage == "volume_skeleton":
        # volume_skeleton: 完整骨架(每2卷一組)
        vols = db.get_volumes(novel_id)
        
        # 決定當前活躍/待審查的卷索引
        active_vol_idx = volume_index
        if active_vol_idx is None:
            # 尋找第一個缺失骨架的卷
            for v in vols:
                if not v.get("chapters_outline"):
                    active_vol_idx = v.get("volume_index")
                    break
            if active_vol_idx is None and vols:
                active_vol_idx = vols[-1].get("volume_index")
                
        simplified_vols = []
        for v in vols:
            v_copy = dict(v)
            v_idx = v_copy.get("volume_index")
            # 只有當前活躍卷才展開章節骨架的簡化說明，其餘已完成的卷只傳遞概要以節省 Token
            if v_idx == active_vol_idx:
                if "chapters_outline" in v_copy and isinstance(v_copy["chapters_outline"], list):
                    simplified_chapters = []
                    for ch in v_copy["chapters_outline"]:
                        if isinstance(ch, dict):
                            simplified_ch = {
                                "chapter_index": ch.get("chapter_index"),
                                "chapter_title": ch.get("chapter_title") or ch.get("title") or "未命名章節",
                                "chapter_summary": ch.get("chapter_summary") or ch.get("summary") or "（尚無摘要說明）"
                            }
                            simplified_chapters.append(simplified_ch)
                    v_copy["chapters_outline"] = simplified_chapters
            else:
                if "chapters_outline" in v_copy:
                    if isinstance(v_copy["chapters_outline"], list):
                        v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                    else:
                        v_copy["chapters_outline"] = "尚未生成骨架"
            simplified_vols.append(v_copy)
            
        plot_text = json.dumps(simplified_vols, ensure_ascii=False, indent=2) if vols else "尚無骨架規劃"
        # 補入目標卷的標題與大綱摘要
        if volume_index is not None:
            target_vol = next((v for v in vols if v["volume_index"] == volume_index), None)
            if target_vol:
                vol_highlight = f"\n\n【當前審查之目標卷 - 第 {volume_index} 卷】\n標題：{target_vol.get('title', '')}\n卷概要：{target_vol.get('summary', '')}"
                plot_text += vol_highlight
        allocation_context = director_context.build_foreshadowing_allocation_context(
            novel_id,
            scope="volume",
            volume_index=active_vol_idx,
        )
        plot_text += "\n\n【Python 預計算本卷伏筆/轉折分配表（總監審核唯一依據）】\n"
        plot_text += json.dumps(allocation_context, ensure_ascii=False, indent=2)
    elif current_stage == "writer":
        plot_text, written_chapters_text = director_context.build_writer_review_context(novel_id, chapter_index, characters_text)
        
    elif current_stage == "editor":
        plot_text, written_chapters_text = director_context.build_editor_review_context(novel_id, chapter_index, characters_text)
        
    else:
        plot_data = db.get_stitched_plot(novel_id)
        if not plot_data:
            plot_text = "尚無章節大綱"
        else:
            chapters = plot_data.get("chapters", [])

            indexes = sorted(
                int(ch["chapter_index"])
                for ch in chapters
                if ch.get("chapter_index") is not None
            )

            if indexes:
                existing = set(indexes)

                missing = [
                    i
                    for i in range(indexes[0], indexes[-1] + 1)
                    if i not in existing
                ]

                plot_text = f"""
        大綱檢查報告
        -------------
        總章節數：{len(indexes)}
        章節範圍：{indexes[0]} ~ {indexes[-1]}
        缺失章節數：{len(missing)}
        缺失章節：{missing[:30] if missing else "無"}
        """
            else:
                plot_text = "尚無章節大綱"

        written_ch = db.get_all_chapters_latest(novel_id)
        written_chapters_text = f"已完成正文章節數：{len(written_ch)} 章"
        
    # 生成 Python 剛性指標檢查報告
    validation_report = diagnostics.generate_validation_report(
        novel_id, 
        current_stage=current_stage, 
        active_volume_index=volume_index, 
        active_chapter_index=chapter_index
    )

    if not conversation_context:
        conversation_context = director_context.build_director_conversation_context(novel_id, limit=1)
    director_context_block = director_context.build_director_context_block(
        conversation_context=conversation_context,
        summary_context=summary_context,
        extra_context=extra_context
    )
    
    messages = build_director_decision_messages(
        novel_id, current_stage, worldview_text, characters_text, plot_text, written_chapters_text, 
        user_prompt, validation_report,
        character_review_mode=character_review_mode,
        character_review_hint=character_review_hint,
        character_review_target_content=character_review_target_content,
        suggested_next_chapter=suggested_next_chapter,
        chapter_index=chapter_index,
        director_context_block=director_context_block,
        gold_rules_context=_load_retrospective_gold_rules(novel_id)
    )
    
    stream = call_llm_stream("copilot", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream, collect_thinking=True)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    full_thinking = acc.thinking
    if full_text.strip():
        db.save_chat_message(novel_id, "director", f"【總監階段評估 ({current_stage})】\n{full_text}", thinking=full_thinking if full_thinking.strip() else None, message_type="director")
        
        # Intercept tool call
        from backend.models.parsers import extract_json_block
        parsed = extract_json_block(full_text)

        if _director_decision_needs_recovery(parsed):
            recovery_decision = _build_recovery_director_decision(novel_id, current_stage, parsed)
            yield "data: " + json.dumps({
                "type": "content",
                "delta": "\n\n【後端決策自癒】總監未輸出可執行標準決策，系統依剛性校驗補上最終決策。\n```json\n"
                + json.dumps(recovery_decision, ensure_ascii=False, indent=2)
                + "\n```\n"
            }, ensure_ascii=False) + "\n\n"
            parsed = recovery_decision

        _record_director_review_status(
            novel_id,
            current_stage,
            parsed,
            volume_index=volume_index,
            chapter_index=chapter_index,
        )

        if parsed and isinstance(parsed, dict) and (parsed.get("action") == "TOOL_CALL" or "tool_call" in parsed):
            tool_call = parsed.get("tool_call") or {}
            tool_name = tool_call.get("tool_name")
            params = tool_call.get("parameters") or {}
            tool_followup_context = None
            
            if tool_name == "invoke_sub_agent":
                agent_name = params.get("agent_name")
                task_description = params.get("task_description")
                context = params.get("context") or {}
                
                yield "data: " + json.dumps({"type": "status", "message": f"總監調用工具：正在呼叫子代理人 {agent_name}..."}, ensure_ascii=False) + "\n\n"
                
                from backend.services.director_tools import invoke_sub_agent
                sub_gen = invoke_sub_agent(agent_name, task_description, context, novel_id, stream=stream)
                for sub_chunk in sub_gen:
                    yield sub_chunk
                
                # Check execution result
                res = sub_gen.result
                if res and res.get("success"):
                    yield "data: " + json.dumps({"type": "status", "message": f"子代理人 {agent_name} 執行成功。"}, ensure_ascii=False) + "\n\n"
                    tool_followup_context = _build_tool_followup_context(tool_name, params, res)
                else:
                    err_msg = res.get("error", "未知錯誤") if res else "未取得執行結果"
                    yield "data: " + json.dumps({"type": "error", "message": f"子代理人 {agent_name} 執行失敗: {err_msg}"}, ensure_ascii=False) + "\n\n"
                    tool_followup_context = _build_tool_followup_context(tool_name, params, res or {"success": False, "error": err_msg})
                    
            elif tool_name == "evaluate_output":
                stage_name = params.get("stage_name")
                output_content = params.get("output_content")
                
                yield "data: " + json.dumps({"type": "status", "message": f"總監調用工具：評估階段 {stage_name} 的輸出..."}, ensure_ascii=False) + "\n\n"
                from backend.services.director_tools import evaluate_output
                eval_res = evaluate_output(stage_name, output_content, novel_id)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[評估結果] {json.dumps(eval_res, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, eval_res)
                
            elif tool_name == "supplement_content":
                stage_name = params.get("stage_name")
                original_output = params.get("original_output")
                evaluation_feedback = params.get("evaluation_feedback")
                
                yield "data: " + json.dumps({"type": "status", "message": f"總監調用工具：針對階段 {stage_name} 進行內容補強與局部修正..."}, ensure_ascii=False) + "\n\n"
                from backend.services.director_tools import supplement_content
                supp_gen = supplement_content(stage_name, original_output, evaluation_feedback, novel_id, stream=stream)
                for sub_chunk in supp_gen:
                    yield sub_chunk
                res = supp_gen.result
                if res and res.get("success"):
                    enhanced_content = res.get("enhanced_content")
                    # 💡 [關鍵功能]: 保存補強內容到資料庫中！
                    if stage_name == "worldview":
                        db.save_worldbuilding(novel_id, enhanced_content, validate=False)
                    elif stage_name == "foreshadowing":
                        parsed_enhanced = extract_json_block(enhanced_content)
                        wb = db.get_latest_worldbuilding(novel_id)
                        wb_dict = db.parse_worldview_to_json(wb["content"]) if wb else {}
                        
                        if isinstance(parsed_enhanced, dict):
                            if "foreshadowing_seeds" in parsed_enhanced:
                                wb_dict["foreshadowing_seeds"] = parsed_enhanced["foreshadowing_seeds"]
                            if "key_turning_points" in parsed_enhanced:
                                wb_dict["key_turning_points"] = parsed_enhanced["key_turning_points"]
                            db.save_worldbuilding(novel_id, json.dumps(wb_dict, ensure_ascii=False, indent=2), validate=False)
                        elif isinstance(parsed_enhanced, list):
                            # 若直接回傳 JSON 陣列，判斷其是否為伏筆種子（含有 setup_hint/payoff_hint 等）或轉折點
                            is_seeds = any("setup_hint" in str(item) or "payoff" in str(item) for item in parsed_enhanced[:3])
                            if is_seeds:
                                wb_dict["foreshadowing_seeds"] = parsed_enhanced
                            else:
                                wb_dict["key_turning_points"] = parsed_enhanced
                            db.save_worldbuilding(novel_id, json.dumps(wb_dict, ensure_ascii=False, indent=2), validate=False)
                    elif stage_name == "characters":
                        db.save_characters(novel_id, enhanced_content)
                    elif stage_name == "volumes":
                        parsed_enhanced = extract_json_block(enhanced_content)
                        volumes_payload = parsed_enhanced.get("volumes") if isinstance(parsed_enhanced, dict) else parsed_enhanced
                        if isinstance(volumes_payload, list):
                            db.save_volumes(novel_id, volumes_payload)
                        else:
                            raise ValueError("supplement_content for volumes did not return a volumes list")
                    elif stage_name == "volume_skeleton":
                        parsed_enhanced = extract_json_block(enhanced_content)
                        chapters_skeleton = parsed_enhanced.get("chapters") or parsed_enhanced.get("chapters_outline") or parsed_enhanced
                        if isinstance(chapters_skeleton, list):
                            vol_idx = params.get("volume_index") or 1
                            db.save_volume_skeletons(novel_id, vol_idx, chapters_skeleton)

                    post_tool_audit = {"persisted": True, "stage_name": stage_name}
                    latest_output = _latest_stage_output_for_tool_review(novel_id, stage_name)
                    if latest_output:
                        try:
                            from backend.services.director_tools import evaluate_output, inspect_content_block
                            post_tool_audit["hard_evaluation"] = evaluate_output(stage_name, latest_output, novel_id)
                            if stage_name in ("foreshadowing", "worldview"):
                                start_idx, end_idx = _infer_tool_review_range(params)
                                parsed_latest = db.parse_worldview_to_json(latest_output)
                                fields_to_inspect = []
                                if isinstance(parsed_latest, dict):
                                    if isinstance(parsed_latest.get("foreshadowing_seeds"), list):
                                        fields_to_inspect.append("foreshadowing_seeds")
                                    if isinstance(parsed_latest.get("key_turning_points"), list):
                                        fields_to_inspect.append("key_turning_points")
                                post_tool_audit["expanded_after_persist"] = [
                                    inspect_content_block(stage_name, field, novel_id, start_index=start_idx, end_index=end_idx)
                                    for field in fields_to_inspect
                                ]
                        except Exception as audit_exc:
                            post_tool_audit["audit_error"] = str(audit_exc)

                    yield "data: " + json.dumps({"type": "status", "message": "內容補強與局部修正完成，已自動更新至資料庫，將交回總監二次核驗。"}, ensure_ascii=False) + "\n\n"
                    tool_followup_context = _build_tool_followup_context(tool_name, params, res, post_tool_audit)
                else:
                    yield "data: " + json.dumps({"type": "error", "message": f"內容補強失敗。"}, ensure_ascii=False) + "\n\n"
                    tool_followup_context = _build_tool_followup_context(tool_name, params, res or {"success": False, "error": "內容補強失敗"})



            elif tool_name == "inspect_content_block":
                from backend.services.director_tools import inspect_content_block
                result = inspect_content_block(novel_id=novel_id, **params)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[展開檢視結果] {json.dumps(result, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            elif tool_name == "expand_collapsed_json":
                from backend.services.director_tools import expand_collapsed_json
                result = expand_collapsed_json(novel_id=novel_id, **params)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[展開檢視結果] {json.dumps(result, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            elif tool_name == "goto_generation_position":
                from backend.services.director_tools import goto_generation_position
                result = goto_generation_position(novel_id=novel_id, **params)
                decision = result.get("decision") if isinstance(result, dict) else None
                if decision:
                    yield "data: " + json.dumps({"type": "content", "delta": "\n```json\n" + json.dumps(decision, ensure_ascii=False, indent=2) + "\n```\n"}, ensure_ascii=False) + "\n\n"
                    return
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            else:
                result = {"success": False, "error": f"未知總監工具: {tool_name}"}
                yield "data: " + json.dumps({"type": "error", "message": result["error"]}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            if tool_followup_context:
                yield from _run_director_followup_after_tool(
                    novel_id,
                    current_stage,
                    user_prompt,
                    extra_context,
                    tool_followup_context,
                    chapter_index,
                    volume_index,
                    suggested_next_chapter,
                    conversation_context,
                    summary_context,
                    loop_count,
                    stream,
                    force_json,
                )
                return


def run_director_decision_help(novel_id, current_stage, help_action, help_reason, stream=False, force_json=False):
    """
    Subsequent Help check:
    If Director wants to retrieve full details (like help_worldview, help_plot) mid-stream.
    """
    if not current_stage or current_stage == "init":
        current_stage = diagnostics.detect_current_stage(novel_id)
    wb = db.get_latest_worldbuilding(novel_id)
    char_data = db.get_latest_characters(novel_id)
    worldview_text = "尚無世界觀設定"
    characters_text = "尚無角色設定"
    plot_text = "尚無篇卷大綱"
    
    if "worldview" in help_action:
        worldview_text = select_worldview_context(wb["content"], current_stage="director", force_full=True) if wb else "尚無世界觀設定"
    if "character" in help_action:
        characters_text = char_data["json_data"] if char_data else "尚無角色設定"
    if "plot" in help_action or "volume" in help_action:
        if current_stage == "volumes":
            vols = db.get_volumes(novel_id)
            simplified_vols = []
            for v in vols:
                v_copy = dict(v)
                if "chapters_outline" in v_copy:
                    if isinstance(v_copy["chapters_outline"], list):
                        v_copy["chapters_outline"] = f"已生成 {len(v_copy['chapters_outline'])} 章骨架大綱"
                    else:
                        v_copy["chapters_outline"] = "尚未生成骨架"
                simplified_vols.append(v_copy)
            plot_text = json.dumps({"volumes": simplified_vols}, ensure_ascii=False, indent=2) if simplified_vols else "尚無篇卷規劃"
        else:
            plot_data = db.get_stitched_plot(novel_id)
            plot_text = simplify_plot_data_for_copilot(json.dumps(plot_data, ensure_ascii=False)) if plot_data else "尚無章節大綱"
    
    target_data = ""
    if "worldview" in help_action:
        target_data = f"【完整世界觀設定數據】\n{worldview_text}"
    elif "character" in help_action:
        target_data = f"【完整角色 Bible 數據】\n{characters_text}"
    elif "plot" in help_action or "volume" in help_action:
        target_data = f"【完整篇卷與大綱數據】\n{plot_text}"
        
    messages = build_director_decision_help_messages(help_reason, target_data)
    
    stream = call_llm_stream("copilot", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream, collect_thinking=True)
    for chunk in acc:
        yield chunk
    full_text = acc.content
    full_thinking = acc.thinking
    if full_text.strip():
        db.save_chat_message(novel_id, "director", f"【總監輔助評估 ({current_stage})】\n{full_text}", thinking=full_thinking if full_thinking.strip() else None, message_type="director")


# =============================================================================
# 10. Incremental / Standalone AI Generators (Auxiliary Buttons support)
# =============================================================================
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
        from backend.services.incremental_patch_engine import validate_and_merge_incremental_patch
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
        from backend.services.incremental_patch_engine import validate_and_merge_incremental_patch
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
    
    from backend.prompts.prompt_builder import build_incremental_skeleton_messages
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


def run_global_foreshadowing_precompute(novel_id):
    """
    [新功能] 預計算全域伏筆與轉折絕對分配藍圖的包裝函數
    """
    db.precompute_global_foreshadowing(novel_id)
