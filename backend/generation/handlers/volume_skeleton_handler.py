"""Volume skeleton handler — one volume per request, Director dispatches order.

支援三種 task_type：
- generate / regenerate : 走舊版 run_volume_skeleton_planner（向後相容舊呼叫）。
- segment_generate      : 總監調度的「分段生成」，只生成指定一段章節；無 while 迴圈。
- segment_complete      : 總監調度的「分段補全（completion）」，以前段成果為脈絡續寫剩餘章節。
- patch                 : 增量修正單卷骨架。

設計目標：分段生成後立即回填 DB + 前端；總監即時 yield 進度；
         一次生成整卷改為「分段生成 + 補全」，由總監統一調度，嚴禁獨立 batch 模式。
"""

from __future__ import annotations

import json
from typing import List

from .. import agent_runners
from backend import db

from ..task_schema import GenerationTaskRequest


def _resolve_single_volume_index(task: GenerationTaskRequest) -> int:
    """
    解析出單一目標卷號。
    優先順序：task.target.volume_index > task.target.selection[0] > DB 第一個缺失卷 > 1
    注意：不再自動批量遍歷所有缺失卷，卷的派發順序完全由總監決定。
    """
    # 1. 直接指定 volume_index
    if task.target.volume_index is not None:
        try:
            return int(task.target.volume_index)
        except Exception:
            pass

    # 2. 從 selection 取第一個
    if isinstance(task.target.selection, list) and task.target.selection:
        item = task.target.selection[0]
        raw_idx = item.get("volume_index") or item.get("volume") or item.get("id") if isinstance(item, dict) else item
        try:
            return int(raw_idx)
        except Exception:
            pass

    # 3. DB 第一個缺失骨架的卷（fallback）
    volumes = db.get_volumes(task.novel_id) or []
    for vol in volumes:
        try:
            idx = int(vol.get("volume_index", 0))
        except Exception:
            continue
        if not vol.get("chapters_outline"):
            return idx

    # 4. 第一卷
    if volumes:
        try:
            return int(volumes[0].get("volume_index", 1))
        except Exception:
            pass
    return 1


def run_volume_skeleton_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()

    # --- patch 模式：增量修正單卷骨架 ---
    if task.task_type == "patch":
        volume_index = _resolve_single_volume_index(task)
        return agent_runners.run_incremental_volume_skeleton(
            task.novel_id,
            volume_index,
            prompt,
            stream=task.options.stream,
            force_json=True,
        )

    # --- 總監調度：分段補全（completion）---
    if task.task_type == "segment_complete":
        return agent_runners.run_volume_skeleton_completion(task, context=context)

    # --- 總監調度：分段生成 ---
    if task.task_type == "segment_generate":
        return agent_runners.run_volume_skeleton_segment(task, context=context)

    # --- 一般生成模式：一次只處理一卷，卷號由總監指定 ---
    volume_index = _resolve_single_volume_index(task)
    return agent_runners.run_volume_skeleton_planner(
        task.novel_id,
        volume_index=volume_index,
        user_prompt=prompt or None,
        stream=task.options.stream,
        force_json=True,
    )
