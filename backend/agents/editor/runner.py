# -*- coding: utf-8 -*-
"""
Editor Agent Runner (兩階段評審精修管線)
階段一：Reviewer 產出結構化品質診斷報告 JSON
階段二：Targeted Rewriter 針對瑕疵標記段落進行精準局部修補
若 Reviewer 判定無需修正，則以原稿進行輕微拋光即可。
"""

import asyncio
import json
import re
import time
import traceback
from functools import partial

from backend import persistence as db
from backend.common import llm
call_llm_stream = llm.call_llm_stream
from backend.common.utils import StreamAccumulator
from backend.schemas.constraints import load_retrospective_gold_rules
from backend.agents.editor.prompts import (
    build_editor_agent_messages,
    build_reviewer_agent_messages,
    build_targeted_rewriter_messages,
)
from backend.services import narrative_memory
from backend.agents.shared.context_requests import _handle_director_context_request
from backend.models.parsers import extract_json_block


# LLM 失敗模式偵測：已知的英文佔位句模式
_LLM_FAILURE_PATTERNS = [
    r"I will now generate",
    r"I will now write",
    r"polished chapter text",
    r"Certainly,? here is",
    r"Here is the (?:polished|revised|edited)",
    r"Let me (?:generate|write|create)",
    r"I'll now produce",
]
_LLM_FAILURE_RE = re.compile("|".join(_LLM_FAILURE_PATTERNS), re.IGNORECASE)


def _is_llm_failure_output(text: str) -> bool:
    """偵測 LLM 輸出是否為英文佔位符/未完成生成，而非正常小說正文。
    此檢查僅攔截明顯的 LLM 系統失敗模式，不做固定比例的語言判斷。
    """
    if not text or len(text.strip()) < 100:
        return True
    from backend.common.refusal_filter import is_refusal_or_disclaimer
    if is_refusal_or_disclaimer(text):
        return True
    # 命中已知英文佔位句模式
    if _LLM_FAILURE_RE.search(text[:500]):
        return True
    return False


def run_editor_agent(novel_id, chapter_index, edit_instructions=None, stream=False, force_json=False, context_bundle=None):
    """
    Editor Stage (兩階段精修):
    1. Reviewer 評審原稿品質與合規性 (POV, 資訊傾倒, 對白, 套路詞)。
    2. 若需修改，由 Targeted Rewriter 局部精修；若原稿優秀則維持原樣或細微拋光。
    """
    chapter_data = db.get_latest_chapter(novel_id, chapter_index)
    if not chapter_data:
        raise ValueError(f"Chapter {chapter_index} prose not found for editing!")

    original_prose = chapter_data.get("content", "")
    current_synopsis = chapter_data.get("synopsis", "")
    outline = narrative_memory.get_chapter_outline(novel_id, chapter_index)

    editor_context_packet = narrative_memory.build_editor_context_packet(novel_id, chapter_index, original_prose)
    if context_bundle:
        editor_context_packet["context_bus_reference"] = {
            "context_mode": context_bundle.get("context_mode"),
            "backend_stage": context_bundle.get("backend_stage"),
            "target_reference": context_bundle.get("target_reference"),
        }
    editor_context = narrative_memory.memory_context_text(editor_context_packet)

    db.save_chat_message(
        novel_id,
        "user",
        f"調用編輯姬審核精修第 {chapter_index} 章。指示: {edit_instructions or '依三層約束標準精修'}",
        message_type="pipeline"
    )

    # =====================================================================
    # 階段一：Reviewer 品質評審 — 輸出結構化診斷 JSON
    # =====================================================================
    diagnostic_report = None
    revision_required = False

    try:
        reviewer_messages = build_reviewer_agent_messages(
            chapter_index=chapter_index,
            original_prose=original_prose,
            scene_contract_or_outline=outline,
            editor_context=editor_context,
        )
        reviewer_iter = llm.call_llm_stream("editor", reviewer_messages, stream=False, force_json=True)
        reviewer_acc = StreamAccumulator(reviewer_iter)
        for _ in reviewer_acc:
            pass
        reviewer_raw = reviewer_acc.content
        if reviewer_raw and reviewer_raw.strip():
            try:
                diagnostic_report = extract_json_block(reviewer_raw)
                if isinstance(diagnostic_report, dict):
                    revision_required = bool(diagnostic_report.get("revision_required", False))
                    # 額外信號：若存在明確瑕疵列表，即使 revision_required 未設，仍需修正
                    if not revision_required:
                        has_issues = any(
                            diagnostic_report.get(k)
                            for k in ("pov_violations", "knowledge_leaks", "info_dump_sections",
                                      "dialogue_issues", "repetition_flags")
                            if isinstance(diagnostic_report.get(k), list) and len(diagnostic_report.get(k, [])) > 0
                        )
                        if has_issues:
                            revision_required = True
            except Exception as parse_err:
                print(f"[EditorAgent] Reviewer JSON parse failed, falling back to single-pass: {parse_err}")
                diagnostic_report = None
    except Exception as reviewer_err:
        print(f"[EditorAgent] Reviewer stage failed, falling back to single-pass: {reviewer_err}")
        diagnostic_report = None

    # 向前端 streaming 報告 Reviewer 結果
    if diagnostic_report is not None:
        yield "data: " + json.dumps({
            "type": "status",
            "message": f"Reviewer 評審完成：{'需要局部精修' if revision_required else '品質良好，進行細微拋光'}",
        }, ensure_ascii=False) + "\n\n"

    # =====================================================================
    # 階段二：決定精修路徑
    # =====================================================================
    if revision_required and diagnostic_report is not None:
        # 路徑 A：Targeted Rewriter — 依診斷報告進行外科手術式局部修補
        rewriter_messages = build_targeted_rewriter_messages(
            chapter_index=chapter_index,
            original_prose=original_prose,
            diagnostic_report=diagnostic_report,
            edit_instructions=edit_instructions,
            editor_context=editor_context,
        )
        stream_iter = llm.call_llm_stream("editor", rewriter_messages, stream=stream, force_json=False)
        messages = rewriter_messages  # 供 save_last_agent_run 使用
    else:
        # 路徑 B：單次拋光 — 原稿品質良好，只做細微潤色
        messages = build_editor_agent_messages(
            chapter_index=chapter_index,
            edit_instructions=edit_instructions,
            original_prose=original_prose,
            editor_context=editor_context,
        )
        stream_iter = llm.call_llm_stream("editor", messages, stream=stream, force_json=force_json)

    acc = StreamAccumulator(stream_iter)
    for chunk in acc:
        if isinstance(chunk, dict):
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
        else:
            yield chunk

    full_text = acc.content
    if full_text.strip():
        # 清理可能輸出的正文標記前綴
        cleaned_text = full_text.strip()
        special_markers = ["[START_OF_PROSE]", "[正文開始]", "【正文開始】", "【正文】", "[正文]", "[PROSE]"]
        for marker in special_markers:
            if marker in cleaned_text:
                idx = cleaned_text.find(marker)
                cleaned_text = cleaned_text[idx + len(marker):].strip()
                break

        if _handle_director_context_request(novel_id, "編輯姬", cleaned_text):
            yield "data: " + json.dumps({"type": "error", "message": "編輯姬需要總監補充上下文，本次不保存成品。"}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        from backend.common.refusal_filter import is_refusal_or_disclaimer, sanitize_meta_narrative
        if is_refusal_or_disclaimer(cleaned_text):
            err_msg = f"第 {chapter_index} 章編輯輸出包含 AI 拒答或安全免責聲明，本次丟棄並保留原稿。"
            yield "data: " + json.dumps({"type": "error", "message": err_msg}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        # LLM 失敗模式偵測：若輸出為英文佔位句或過短，丟棄並保留原稿
        if _is_llm_failure_output(cleaned_text):
            print(f"[EditorAgent] LLM failure detected for chapter {chapter_index}: output discarded, original preserved.")
            yield "data: " + json.dumps({
                "type": "error",
                "message": f"⚠️ 第 {chapter_index} 章編輯輸出偵測到 LLM 失敗模式（英文佔位或過短），已丟棄異常輸出並保留原稿。",
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
            return

        final_prose = sanitize_meta_narrative(cleaned_text if cleaned_text else full_text)

        memory_summary = narrative_memory.build_chapter_memory_summary(
            novel_id,
            chapter_index,
            final_prose,
            outline=outline,
        )
        synopsis = memory_summary.get("chapter_summary") or current_synopsis
        saved_version = db.save_chapter(novel_id, chapter_index, final_prose, synopsis=synopsis)
        narrative_memory.store_chapter_memory(
            novel_id,
            chapter_index,
            final_prose,
            source_version=saved_version,
            outline=outline,
        )

        # 建立草案建議記錄 (Draft Proposal)，供前端「審閱對比 (Diff)」與「一鍵套用/放棄」進行行級差異對比
        if original_prose and original_prose.strip() != final_prose.strip():
            try:
                review_comments_data = [{
                    "type": "editor_refine",
                    "instruction": edit_instructions or "依文學標準潤色精修",
                    "summary": f"第 {chapter_index} 章文字潤色與修辭精修"
                }]
                if diagnostic_report is not None:
                    review_comments_data.append({
                        "type": "reviewer_diagnostic",
                        "revision_required": revision_required,
                        "summary": f"Reviewer 診斷：{'需局部精修' if revision_required else '品質良好'}",
                    })
                db.create_proposal(
                    novel_id=novel_id,
                    chapter_index=chapter_index,
                    proposed_text=final_prose,
                    original_text=original_prose,
                    review_comments=review_comments_data
                )
            except Exception as prop_err:
                print(f"[EditorAgent] create_proposal error: {prop_err}")

        edit_mode = "兩階段精修（Reviewer→Rewriter）" if revision_required else "細微拋光"
        db.save_last_agent_run(novel_id, "editor", json.dumps(messages, ensure_ascii=False, indent=2), final_prose)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已經由{edit_mode}完畢！", message_type="pipeline")
