"""Volume skeleton handler — one full volume per request, Director dispatches order.

支援三種 task_type：
- generate / regenerate : 走舊版 run_volume_skeleton_planner（向後相容舊呼叫）。
- patch                 : 增量修正單卷骨架。

設計目標：一般 generate/regenerate 一次要求 Agent 生成完整單卷骨架。
         舊 segment task 會被正規化為整卷 generate，不再切段。
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

    # --- 一般生成模式：一次只處理一卷，卷號由總監指定 ---
    volume_index = _resolve_single_volume_index(task)
    return agent_runners.run_volume_skeleton_planner(
        task.novel_id,
        volume_index=volume_index,
        user_prompt=prompt or None,
        stream=task.options.stream,
        force_json=True,
    )
