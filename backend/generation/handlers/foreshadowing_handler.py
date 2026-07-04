"""Foreshadowing generation handler — supports split target_field generation.

Director 需要在 agent_prompt 中帶入 [BATCH: foreshadowing_seeds] 或 [BATCH: key_turning_points]
標記，後端會自動解析並僅生成對應類別的資料，保留另一類已有的資料不被覆蓋。
這避免了單次生成 50+ 條伏筆 + 50+ 條轉折點導致 JSON 過長而解析錯誤。
"""

from __future__ import annotations

import re

from .. import agent_runners

from ..task_schema import GenerationTaskRequest


def _extract_batch_target(task: GenerationTaskRequest) -> str | None:
    """從 agent_prompt 或 instruction 中提取 [BATCH: xxx] 標記。"""
    texts_to_check = [
        getattr(task, "agent_prompt", None) or "",
        task.instruction or "",
        task.hint or "",
        task.user_prompt or "",
    ]
    for text in texts_to_check:
        if not text:
            continue
        m = re.search(r'\[BATCH:\s*(foreshadowing_seeds|key_turning_points)\]', text, re.IGNORECASE)
        if m:
            return m.group(1).lower().strip()
    return None


def run_foreshadowing_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()

    # 優先從 task 直接屬性讀取（若前端或 copilot 已明確傳入）
    target_field = getattr(task, "target_field", None) or None

    # 若未直接傳入，從 agent_prompt / instruction 中解析 [BATCH: xxx] 標記
    if not target_field:
        target_field = _extract_batch_target(task)

    return agent_runners.run_foreshadowing_orchestrator(
        task.novel_id,
        user_prompt=prompt or None,
        target_field=target_field,
        stream=task.options.stream,
        force_json=True,
    )
