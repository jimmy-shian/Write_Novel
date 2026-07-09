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
from backend.agents.director.contracts import EXECUTABLE_DIRECTOR_ACTIONS
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

from backend.agents.shared.tool_followup import (
    _build_tool_followup_context,
    _director_tool_signature,
    _infer_tool_review_range,
    _latest_stage_output_for_tool_review,
    _run_director_followup_after_tool,
)


def _parse_sse_data_chunk(chunk):
    if not chunk or not isinstance(chunk, str) or not chunk.startswith("data:"):
        return None
    payload = chunk[5:].strip()
    if not payload or payload == "[DONE]":
        return {"type": "done"}
    try:
        return json.loads(payload)
    except Exception:
        return None


def _is_director_tool_call(parsed):
    return isinstance(parsed, dict) and (str(parsed.get("action") or "").upper() == "TOOL_CALL" or "tool_call" in parsed)


def _tool_signature_seen(extra_context, signature):
    if not signature:
        return False
    return f"tool_signature: {signature}" in (extra_context or "")

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


def _director_decision_needs_recovery(parsed):
    if not isinstance(parsed, dict):
        return True
    action = str(parsed.get("action") or "").upper().strip()
    if action not in EXECUTABLE_DIRECTOR_ACTIONS:
        return True
    if action in {"CONTINUE", "AUTO_REGENERATE"} and not parsed.get("target"):
        return True
    if action == "TOOL_CALL" or "tool_call" in parsed:
        tool_call = parsed.get("tool_call") or {}
        tool_name = tool_call.get("tool_name")
        if not tool_name or tool_name not in {"invoke_sub_agent", "evaluate_output", "supplement_content", "inspect_content_block", "expand_collapsed_json", "goto_generation_position"}:
            return True
    target = str(parsed.get("target") or "").lower()
    text = json.dumps(parsed, ensure_ascii=False)
    if action == "CONTINUE" and target == "foreshadowing" and not re_search_batch_marker(text):
        return True
    return False


def _director_model_error_message(parsed):
    if not isinstance(parsed, dict):
        return None
    action = str(parsed.get("action") or "").upper().strip()
    if action:
        return None
    for key in ("error", "message", "detail"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _format_director_decision_content(decision):
    return "```json\n" + json.dumps(decision, ensure_ascii=False, indent=2) + "\n```"


def _save_director_decision_message(novel_id, current_stage, decision_text, full_thinking):
    db.save_chat_message(
        novel_id,
        "director",
        f"【總監階段評估 ({current_stage})】\n{decision_text}",
        thinking=full_thinking if full_thinking.strip() else None,
        message_type="director",
    )


def _get_director_decision_error_message(parsed, raw_text):
    if not isinstance(parsed, dict):
        return (
            f"輸出格式非 JSON 物件。請只輸出單一合規 JSON 物件，不要使用 markdown code fence、前後說明或多個 JSON。"
            f"最外層必須是包含 'action' 等欄位的物件，不得將 JSON 包裹在空白鍵或其他鍵值（例如 `\"\"`）底下。\n"
            f"您產生的原始輸出內容為：\n{raw_text}"
        )
    action = str(parsed.get("action") or "").upper().strip()
    model_error = _director_model_error_message(parsed)
    if model_error:
        return f"總監模型回傳錯誤而非決策 JSON：{model_error}"
    if action not in EXECUTABLE_DIRECTOR_ACTIONS:
        return (
            f"action 欄位值 '{action}' 不在合法動作清單中。\n"
            f"合法 action 清單：{list(EXECUTABLE_DIRECTOR_ACTIONS)}\n"
            f"請修正 'action' 欄位。"
        )
    if action in {"CONTINUE", "AUTO_REGENERATE"} and not parsed.get("target"):
        return "當 action 為 CONTINUE 或 AUTO_REGENERATE 時，必須指定 'target' 欄位（例如：'target': 'volume_skeleton'）。請指定 target。"
    if action == "TOOL_CALL" or "tool_call" in parsed:
        tool_call = parsed.get("tool_call") or {}
        tool_name = tool_call.get("tool_name")
        if not tool_name:
            return "當 action 為 TOOL_CALL 時，必須在 'tool_call' 下指定 'tool_name' 欄位。請指定有效的工具名稱。"
        if tool_name not in {"invoke_sub_agent", "evaluate_output", "supplement_content", "inspect_content_block", "expand_collapsed_json", "goto_generation_position"}:
            return f"未知的總監工具名稱：{tool_name}。請使用合法的工具名稱。"
    target = str(parsed.get("target") or "").lower()
    text = json.dumps(parsed, ensure_ascii=False)
    if action == "CONTINUE" and target == "foreshadowing" and not re_search_batch_marker(text):
        return (
            "當前往 foreshadowing 階段時，必須在 'hint' 或 'agent_prompt' 中指定分批生成標籤：\n"
            "- 若要生成伏筆種子，請在 prompt 中加入 [BATCH: foreshadowing_seeds]\n"
            "- 若要生成關鍵轉折，請在 prompt 中加入 [BATCH: key_turning_points]"
        )
    return "JSON 格式不符合總監決策合約，請確認頂層欄位與命名規範。"


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
        STAGES_ORDER = ["worldview", "characters", "foreshadowing", "volumes", "volume_skeleton", "writer", "editor"]
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
                from backend.prompts.common.context import compact_json_data
                compacted = compact_json_data(parsed, max_list_items=5)
                worldview_text = json.dumps(compacted, ensure_ascii=False, indent=2)
            except Exception:
                pass
        if len(worldview_text) > MAX_DIRECTOR_WORLDVIEW_CHARS:
            from backend.prompts.common.context import compact_context_text
            worldview_text = compact_context_text(worldview_text, MAX_DIRECTOR_WORLDVIEW_CHARS, "worldview")
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
    
    requested_stream = bool(stream)
    llm_stream = call_llm_stream("copilot", messages, stream=requested_stream, force_json=force_json)
    acc = StreamAccumulator(llm_stream, collect_thinking=True)
    for chunk in acc:
        event = _parse_sse_data_chunk(chunk)
        if event and event.get("type") == "error":
            yield chunk
            return
    full_text = acc.content
    full_thinking = acc.thinking
    from backend.models.parsers import extract_json_block
    decision_text = full_text
    parsed = extract_json_block(full_text)
    emitted_decision_content = False

    if isinstance(parsed, dict) and parsed:
        decision_text = _format_director_decision_content(parsed)

    if not full_text.strip() and full_thinking.strip():
        parsed_from_thinking = extract_json_block(full_thinking)
        if isinstance(parsed_from_thinking, dict) and parsed_from_thinking and not _director_model_error_message(parsed_from_thinking):
            parsed = parsed_from_thinking
            decision_text = _format_director_decision_content(parsed)
            full_text = decision_text
        else:
            parsed = parsed_from_thinking
            decision_text = full_thinking

    if not decision_text.strip():
        parsed = {}
        decision_text = ""

    model_error = _director_model_error_message(parsed)
    if model_error:
        decision_text = decision_text or json.dumps(parsed, ensure_ascii=False)

    if _director_decision_needs_recovery(parsed):
        err_msg = _get_director_decision_error_message(parsed, decision_text)
        if loop_count < 30:
            yield "data: " + json.dumps({
                "type": "status",
                "message": f"【後端決策校驗】總監決策未通過剛性校驗，準備進行自我修正第 {loop_count + 1}/30 次..."
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({
                "type": "content",
                "delta": f"\n\n【決策校驗失敗】偵測到以下錯誤：\n- {err_msg}\n正在請總監進行自我修正...\n"
            }, ensure_ascii=False) + "\n\n"
            
            combined_extra = "\n\n".join(part for part in (extra_context, f"【系統決策校驗回報 - 自我修正第 {loop_count + 1} 次】\n請修正以下錯誤並重新輸出決策 JSON：\n{err_msg}") if part)
            yield from run_director_decision(
                novel_id,
                current_stage=current_stage,
                user_prompt=user_prompt,
                chapter_index=chapter_index,
                volume_index=volume_index,
                character_review_mode=character_review_mode,
                character_review_hint=character_review_hint,
                character_review_target_content=character_review_target_content,
                suggested_next_chapter=suggested_next_chapter,
                conversation_context=conversation_context,
                summary_context=summary_context,
                extra_context=combined_extra,
                loop_count=loop_count + 1,
                stream=requested_stream,
                force_json=force_json,
            )
            return
        else:
            terminal_msg = "總監連續 30 次決策自癒失敗，已達重試上限。請檢查系統 Prompt 或手動干預。"
            yield "data: " + json.dumps({"type": "error", "message": terminal_msg}, ensure_ascii=False) + "\n\n"
            raise Exception(terminal_msg)

    _save_director_decision_message(novel_id, current_stage, decision_text, full_thinking)

    if not _is_director_tool_call(parsed) and not emitted_decision_content:
        yield "data: " + json.dumps({"type": "content", "delta": decision_text}, ensure_ascii=False) + "\n\n"
        emitted_decision_content = True

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
            tool_signature = _director_tool_signature(tool_name, params)
            if _tool_signature_seen(extra_context, tool_signature):
                yield "data: " + json.dumps({
                    "type": "status",
                    "message": f"總監再次呼叫同一工具：{tool_signature}。後端不補正決策，依總監輸出繼續執行。"
                }, ensure_ascii=False) + "\n\n"
            
            if tool_name == "invoke_sub_agent":
                agent_name = params.get("agent_name")
                task_description = params.get("task_description")
                context = params.get("context") or {}
                
                yield "data: " + json.dumps({"type": "status", "message": f"總監調用工具：正在呼叫子代理人 {agent_name}..."}, ensure_ascii=False) + "\n\n"
                
                from backend.services.director.tools import invoke_sub_agent
                sub_gen = invoke_sub_agent(agent_name, task_description, context, novel_id, stream=requested_stream)
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
                from backend.services.director.tools import evaluate_output
                eval_res = evaluate_output(stage_name, output_content, novel_id)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[評估結果] {json.dumps(eval_res, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, eval_res)
                
            elif tool_name == "supplement_content":
                stage_name = params.get("stage_name")
                original_output = params.get("original_output")
                evaluation_feedback = params.get("evaluation_feedback")
                
                yield "data: " + json.dumps({"type": "status", "message": f"總監調用工具：針對階段 {stage_name} 進行內容補強與局部修正..."}, ensure_ascii=False) + "\n\n"
                from backend.services.director.tools import supplement_content
                supp_gen = supplement_content(stage_name, original_output, evaluation_feedback, novel_id, stream=requested_stream)
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
                            from backend.services.director.tools import evaluate_output, inspect_content_block
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
                from backend.services.director.tools import inspect_content_block
                result = inspect_content_block(novel_id=novel_id, **params)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[展開檢視結果] {json.dumps(result, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            elif tool_name == "expand_collapsed_json":
                from backend.services.director.tools import expand_collapsed_json
                result = expand_collapsed_json(novel_id=novel_id, **params)
                yield "data: " + json.dumps({"type": "content", "delta": f"\n[展開檢視結果] {json.dumps(result, ensure_ascii=False, indent=2)}\n"}, ensure_ascii=False) + "\n\n"
                tool_followup_context = _build_tool_followup_context(tool_name, params, result)

            elif tool_name == "goto_generation_position":
                from backend.services.director.tools import goto_generation_position
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
                    requested_stream,
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
