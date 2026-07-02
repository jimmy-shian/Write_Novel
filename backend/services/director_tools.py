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


def export_tools():
    return TOOL_REGISTRY
