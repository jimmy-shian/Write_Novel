# -*- coding: utf-8 -*-
"""
Director Tool System - 總監 Agent 三大核心工具
1. invoke_sub_agent()     - 呼叫其他代理人
2. evaluate_output()      - 評斷其他代理人的輸出結果
3. supplement_content()   - 執行部分內容的補強與生成
"""

import json
import time
from typing import Optional, Dict, Any, List

from backend import db
from backend.llm import call_llm_stream
from backend.utils import StreamAccumulator
from backend.schemas.agent_json import APPROVAL_CRITERIA_REGISTRY, format_criteria_for_prompt
from backend.schemas.validation import (
    normalize_foreshadowing_output,
    foreshadowing_quantity_error,
    foreshadowing_schema_error,
    volume_plan_validation_error,
)
from backend.schemas.constraints import load_retrospective_gold_rules
from backend.models.parsers import extract_json_block

MAX_RETRIES = 10

TOOL_REGISTRY = {
    "goto_generation_position": {
        "description": "前往指定生成位置；由總監明確指定下一個 target/stage 與卷章索引，系統會轉成可執行決策",
        "parameters": ["target", "novel_id", "volume_index", "chapter_index", "reason", "agent_prompt", "agent_context"],
    },
    "inspect_content_block": {
        "description": "檢視指定區塊；依總監指定的 stage/block/range 展開資料庫內容，預設每次 15 筆",
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
        "description": "分批/分頁展開查看被收合的 JSON 內容，每次指定一小段區間（如 1~10、11~20），避免一次讀取過多導致截斷",
        "parameters": ["stage_name", "field_name", "start_index", "end_index", "novel_id"],
    },
}


class SubAgentGenerator:
    """包裝子代理人執行的生成器，以便外部獲取最終解析結果"""
    def __init__(self, gen):
        self.gen = gen
        self.result = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.gen)
        except StopIteration as e:
            # 如果有 return 值，保存起來
            self.result = e.value
            raise


def invoke_sub_agent(
    agent_name: str,
    task_description: str,
    context: Dict[str, Any],
    novel_id: str,
    stream: bool = True,
    force_json: bool = False,
    max_retries: int = MAX_RETRIES,
):
    """
    [Tool 1] 總監呼叫其他代理人
    支援自動 retry，最大 10 次，若格式錯誤則退回重新呼叫
    """
    def _run():
        from backend.prompts.prompt_builder import build_director_sub_agent_messages

        retries = 0
        last_error = ""

        while retries < max_retries:
            retries += 1
            try:
                messages = build_director_sub_agent_messages(
                    agent_name, task_description, context,
                    retry_hint=last_error if last_error else None,
                    retry_count=retries,
                )
                llm_stream = call_llm_stream(agent_name, messages, stream=stream, force_json=force_json)
                acc = StreamAccumulator(llm_stream)
                for chunk in acc:
                    yield chunk

                full_text = acc.content
                parsed = extract_json_block(full_text)
                if parsed:
                    return {
                        "success": True,
                        "result": parsed,
                        "agent_name": agent_name,
                        "retries_used": retries,
                    }

                last_error = f"JSON block extraction failed, raw output: {full_text[:200]}..."
                time.sleep(1)

            except Exception as e:
                last_error = str(e)
                time.sleep(min(2 ** (retries - 1), 30))

        return {
            "success": False,
            "error": last_error,
            "agent_name": agent_name,
            "retries_used": retries,
        }

    return SubAgentGenerator(_run())


def evaluate_output(stage_name: str, output_content: str, novel_id: str) -> Dict[str, Any]:
    """
    [Tool 2] 評斷代理人的輸出結果
    透過 APPROVAL_CRITERIA_REGISTRY 進行硬性校驗
    """
    criteria = APPROVAL_CRITERIA_REGISTRY.get(stage_name)
    if not criteria:
        return {"passed": True, "message": "無該階段標準，視為通過", "issues": []}

    issues = []

    if stage_name == "foreshadowing":
        parsed = extract_json_block(output_content)
        normalized = normalize_foreshadowing_output(parsed)
        seeds = normalized.get("foreshadowing_seeds", [])
        turns = normalized.get("key_turning_points", [])
        q_err = foreshadowing_quantity_error(seeds, turns)
        if q_err:
            issues.append(q_err)
        s_err = foreshadowing_schema_error(seeds, turns)
        if s_err:
            issues.append(s_err)

    elif stage_name == "volumes":
        parsed = extract_json_block(output_content)
        vols = parsed.get("volumes", []) if isinstance(parsed, dict) else []
        v_err = volume_plan_validation_error(vols, mode="generate")
        if v_err:
            issues.append(v_err)

    elif stage_name == "worldview":
        parsed = extract_json_block(output_content)
        if isinstance(parsed, dict):
            required = ["theme", "main_conflict", "worldview", "macro_outline"]
            for field in required:
                if not parsed.get(field):
                    issues.append(f"缺少必填欄位: {field}")

    criteria_prompt = format_criteria_for_prompt(stage_name)

    return {
        "passed": len(issues) == 0,
        "message": "通過" if len(issues) == 0 else "; ".join(issues),
        "issues": issues,
        "criteria_reference": criteria_prompt,
    }


def supplement_content(
    stage_name: str,
    original_output: str,
    evaluation_feedback: str,
    novel_id: str,
    stream: bool = True,
    force_json: bool = False,
):
    """
    [Tool 3] 執行部分內容的補強與生成
    當 evaluate_output 回報不合格時，Director 調用此工具進行 content enhancement
    """
    def _run():
        from backend.prompts.prompt_builder import build_supplement_messages

        messages = build_supplement_messages(
            stage_name, original_output, evaluation_feedback, novel_id
        )
        llm_stream = call_llm_stream("copilot", messages, stream=stream, force_json=force_json)
        acc = StreamAccumulator(llm_stream)
        for chunk in acc:
            yield chunk

        return {
            "success": True,
            "enhanced_content": acc.content,
            "stage": stage_name,
        }

    return SubAgentGenerator(_run())


def expand_collapsed_json(
    stage_name: str,
    field_name: str,
    start_index: int,
    end_index: int,
    novel_id: str
) -> Dict[str, Any]:
    """
    [Tool 4] 允許總監分批展開查看被收合的 JSON 陣列內容 (如 1~10, 11~20)
    避免一次載入全部 50 個項目導致 Token 溢出或截斷，使總監能精準評估。
    """
    if stage_name in ("foreshadowing", "worldview"):
        wb = db.get_latest_worldbuilding(novel_id)
        if not wb:
            return {"success": False, "error": "世界觀設定為空"}
        try:
            parsed = json.loads(wb["content"])
        except Exception:
            parsed = db.parse_worldview_to_json(wb["content"])
            
        if not isinstance(parsed, dict):
            return {"success": False, "error": "無法解析世界觀 JSON"}
            
        items = parsed.get(field_name, [])
        if not isinstance(items, list):
            return {"success": False, "error": f"欄位 {field_name} 不是列表"}
            
        total_count = len(items)
        # Convert 1-based indexing to 0-based slice
        start_offset = max(0, start_index - 1)
        end_offset = max(start_offset, end_index)
        sub_items = items[start_offset:end_offset]
        
        return {
            "success": True,
            "stage_name": stage_name,
            "field_name": field_name,
            "start_index": start_index,
            "end_index": end_index,
            "total_count": total_count,
            "returned_count": len(sub_items),
            "items": sub_items,
            "step_description": f"已展開查看 {field_name} 的第 {start_index} 到 {end_index} 個項目 (總計 {total_count} 個)。"
        }
    else:
        return {"success": False, "error": f"不支援的階段: {stage_name}"}


def goto_generation_position(
    target: str,
    novel_id: str,
    volume_index: Optional[int] = None,
    chapter_index: Optional[int] = None,
    reason: str = "",
    agent_prompt: str = "",
    agent_context: str = "",
    **_: Any,
) -> Dict[str, Any]:
    """
    [Tool] Convert a Director navigation intent into a normal executable decision.
    The frontend should not invent this decision; the Director chooses the target.
    """
    return {
        "success": True,
        "decision": {
            "action": "CONTINUE",
            "target": target,
            "volume_index": volume_index,
            "chapter_index": chapter_index,
            "reason": reason or f"總監指定前往 {target}",
            "hint": agent_prompt or reason or "",
            "agent_prompt": agent_prompt or "",
            "agent_context": agent_context or "",
        },
    }


def _coerce_range(start_index: Any = None, end_index: Any = None, default_size: int = 15) -> tuple[int, int]:
    try:
        start = int(start_index or 1)
    except Exception:
        start = 1
    try:
        end = int(end_index or (start + default_size - 1))
    except Exception:
        end = start + default_size - 1
    start = max(1, start)
    end = max(start, end)
    return start, end


def _page_items(items: List[Any], start_index: int, end_index: int) -> Dict[str, Any]:
    start_offset = max(0, start_index - 1)
    end_offset = max(start_offset, end_index)
    return {
        "start_index": start_index,
        "end_index": end_index,
        "total_count": len(items),
        "returned_count": len(items[start_offset:end_offset]),
        "items": items[start_offset:end_offset],
    }


def inspect_content_block(
    stage_name: str,
    block_name: str,
    novel_id: str,
    volume_index: Optional[int] = None,
    chapter_index: Optional[int] = None,
    start_index: int = 1,
    end_index: Optional[int] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    [Tool] Inspect a concrete persisted block chosen by the Director.
    This is the preferred path for long inputs: counts stay in validation reports,
    and details are paged by explicit location/range.
    """
    stage = (stage_name or "").strip()
    block = (block_name or "").strip()
    start, end = _coerce_range(start_index, end_index)

    if stage in ("worldview", "foreshadowing"):
        wb = db.get_latest_worldbuilding(novel_id)
        if not wb:
            return {"success": False, "error": "世界觀設定為空"}
        try:
            parsed = json.loads(wb["content"])
        except Exception:
            parsed = db.parse_worldview_to_json(wb["content"])
        if not isinstance(parsed, dict):
            return {"success": False, "error": "無法解析世界觀 JSON"}
        value = parsed.get(block)
        if isinstance(value, list):
            return {"success": True, "stage_name": stage, "block_name": block, **_page_items(value, start, end)}
        return {"success": True, "stage_name": stage, "block_name": block, "value": value}

    if stage == "characters":
        char_data = db.get_latest_characters(novel_id)
        parsed = char_data.get("parsed_data") if char_data else None
        chars = parsed.get("characters", []) if isinstance(parsed, dict) else []
        if block in ("characters", "角色", ""):
            return {"success": True, "stage_name": stage, "block_name": "characters", **_page_items(chars, start, end)}
        return {"success": False, "error": f"不支援的角色區塊: {block}"}

    if stage in ("volumes", "volume_skeleton"):
        vols = db.get_volumes(novel_id)
        if stage == "volumes" or block in ("volumes", "篇卷", ""):
            return {"success": True, "stage_name": stage, "block_name": "volumes", **_page_items(vols, start, end)}
        try:
            vol_idx = int(volume_index) if volume_index is not None else None
        except Exception:
            vol_idx = None
        target_vol = next((v for v in vols if int(v.get("volume_index", 0)) == int(vol_idx or 0)), None)
        if not target_vol:
            return {"success": False, "error": f"找不到第 {vol_idx} 卷"}
        chapters = target_vol.get("chapters_outline") or []
        if isinstance(chapters, str):
            try:
                chapters = json.loads(chapters)
            except Exception:
                chapters = []
        return {
            "success": True,
            "stage_name": stage,
            "block_name": "chapters_outline",
            "volume_index": vol_idx,
            **_page_items(chapters if isinstance(chapters, list) else [], start, end),
        }

    if stage in ("writer", "editor"):
        try:
            ch_idx = int(chapter_index or 1)
        except Exception:
            ch_idx = 1
        chapter = db.get_latest_chapter(novel_id, ch_idx)
        return {
            "success": bool(chapter),
            "stage_name": stage,
            "block_name": block or "chapter",
            "chapter_index": ch_idx,
            "chapter": dict(chapter) if chapter else None,
            "error": None if chapter else f"第 {ch_idx} 章尚無正文",
        }

    return {"success": False, "error": f"不支援的階段: {stage}"}


def export_tools():
    return TOOL_REGISTRY
