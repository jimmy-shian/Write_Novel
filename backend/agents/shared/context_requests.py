# -*- coding: utf-8 -*-
import asyncio
import json
import time
import traceback
from functools import partial
from backend import persistence as db
from backend.schemas.validation import extract_worldview_dict_preserving

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
