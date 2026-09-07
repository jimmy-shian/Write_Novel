# -*- coding: utf-8 -*-
"""
Editor Agent Runner (兩階段評審精修管線)
階段一：Reviewer 產出結構化品質診斷報告 JSON
階段二：Targeted Rewriter 針對瑕疵標記段落進行精準局部修補
"""

import asyncio
import json
import time
import traceback
from functools import partial

from backend import persistence as db
from backend.common.llm import call_llm_stream
from backend.common.utils import StreamAccumulator
from backend.schemas.constraints import load_retrospective_gold_rules
from backend.agents.editor.prompts import (
    build_editor_agent_messages,
    build_reviewer_agent_messages,
    build_targeted_rewriter_messages,
)
from backend.services import narrative_memory
from backend.agents.shared.context_requests import _handle_director_context_request


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

    # 組裝 Editor 提示詞（包含本章場景目標、前章銜接與編輯指示）
    messages = build_editor_agent_messages(
        chapter_index=chapter_index,
        edit_instructions=edit_instructions,
        original_prose=original_prose,
        editor_context=editor_context,
    )

    stream_iter = call_llm_stream("editor", messages, stream=stream, force_json=force_json)
    acc = StreamAccumulator(stream_iter)
    for chunk in acc:
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

        final_prose = cleaned_text if cleaned_text else full_text

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
        db.save_last_agent_run(novel_id, "editor", json.dumps(messages, ensure_ascii=False, indent=2), final_prose)
        db.save_chat_message(novel_id, "assistant", f"第 {chapter_index} 章正文已成功潤色精修完畢！", message_type="pipeline")
