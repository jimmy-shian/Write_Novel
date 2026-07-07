# -*- coding: utf-8 -*-
from typing import Dict, Any

TOOL_REGISTRY = {
    "goto_generation_position": {
        "description": "前往指定生成位置；由總監明確指定下一個 target/stage 與卷章索引，系統會轉成可執行決策",
        "parameters": ["target", "novel_id", "volume_index", "chapter_index", "reason", "agent_prompt", "agent_context"],
    },
    "inspect_content_block": {
        "description": "檢視指定區塊；依總監指定的 stage/block/range 展開資料庫內容，預設每次 15 筆。卷骨架請用 block_name=chapters_outline 與 start_index/end_index；上一輪 Agent 記錄可用 stage_name=last_agent_run、block_name=input_data/output_data。",
        "parameters": ["stage_name", "block_name", "novel_id", "volume_index", "chapter_index", "start_index", "end_index"],
    },
    "invoke_sub_agent": {
        "description": "呼叫指定的下游代理人執行生成任務，傳回結果",
        "parameters": ["agent_name", "task_description", "context", "max_tokens"],
    },
    "evaluate_output": {
        "description": "評斷代理人的輸出結果是否符合通過標準",
        "parameters": ["stage_name", "output_content", "novel_id"],
    },
    "supplement_content": {
        "description": "對不合格的輸出進行補強生成或局部修正",
        "parameters": ["stage_name", "original_output", "evaluation_feedback", "novel_id"],
    },
    "expand_collapsed_json": {
        "description": "分批/分頁展開查看被收合的 JSON 內容，每次指定一小段區間（如 1~10、11~20），避免一次讀取過多超出上下文",
        "parameters": ["stage_name", "field_name", "start_index", "end_index", "novel_id"],
    },
}

def export_tools() -> Dict[str, Any]:
    return TOOL_REGISTRY
