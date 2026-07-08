# -*- coding: utf-8 -*-
import asyncio
import json
import time
import traceback
from functools import partial
from backend import persistence as db
from backend.schemas.validation import extract_worldview_dict_preserving

def _tool_json(value):
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _director_tool_signature(tool_name, params):
    """Stable signature used to stop repeated identical Director tool calls."""
    normalized_params = dict(params or {})
    normalized_params.pop("novel_id", None)
    try:
        param_text = json.dumps(normalized_params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        param_text = str(sorted(normalized_params.items()))
    return f"{tool_name or ''}:{param_text}"


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
    signature = _director_tool_signature(tool_name, params)
    return (
        "【總監工具執行結果 - 必須二次評判】\n"
        f"tool_name: {tool_name}\n"
        f"tool_signature: {signature}\n"
        f"parameters:\n{_tool_json(params)}\n\n"
        f"tool_result:\n{_tool_json(tool_result)}\n\n"
        f"post_tool_audit:\n{_tool_json(post_tool_audit or {})}\n\n"
        "請你根據最新資料庫狀態、validation_report、post_tool_audit 與必要的展開內容重新判斷。\n"
        "如果補強後內容仍未達標，禁止輸出 WAIT_USER 或 FINISH；請使用尚未執行過的 TOOL_CALL 繼續展開/補強，或用 CONTINUE/AUTO_REGENERATE/GO_BACK_* 派發正確階段。\n"
        "禁止再次呼叫相同 tool_signature 的工具；若同一範圍已展開或同一硬性校驗已完成，請直接根據既有工具結果做最終流程決策。\n"
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
    from backend.agents.director.runner import run_director_decision
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
