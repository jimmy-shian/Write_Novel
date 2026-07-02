"""Volume skeleton handler, including batch expansion across multiple volumes."""

from __future__ import annotations

import json
from typing import Iterable, List

from .. import agent_runners
from backend import db

from ..task_schema import GenerationTaskRequest


def _resolve_volume_indexes(task: GenerationTaskRequest) -> List[int]:
    selected = []
    if isinstance(task.target.selection, list):
        for item in task.target.selection:
            if isinstance(item, dict):
                raw_idx = item.get("volume_index") or item.get("volume") or item.get("id")
            else:
                raw_idx = item
            try:
                idx = int(raw_idx)
            except Exception:
                continue
            if idx > 0 and idx not in selected:
                selected.append(idx)

    if task.target.volume_index is not None and task.target.volume_index not in selected:
        selected.append(int(task.target.volume_index))

    if selected:
        return selected

    volumes = db.get_volumes(task.novel_id) or []
    if task.task_type == "batch_generate" or task.options.batch:
        missing = []
        for vol in volumes:
            try:
                idx = int(vol.get("volume_index"))
            except Exception:
                continue
            if not vol.get("chapters_outline"):
                missing.append(idx)
        if missing:
            return missing

    if volumes:
        try:
            return [int(volumes[0].get("volume_index", 1))]
        except Exception:
            return [1]
    return [1]


def run_volume_skeleton_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    indexes = _resolve_volume_indexes(task)

    if len(indexes) <= 1 and not task.options.batch and task.task_type != "batch_generate":
        volume_index = indexes[0]
        return agent_runners.run_volume_skeleton_planner(
            task.novel_id,
            volume_index=volume_index,
            user_prompt=prompt or None,
            stream=task.options.stream,
            force_json=True,
        )

    def _batch_stream():
        for idx in indexes:
            yield "data: " + json.dumps(
                {"type": "status", "message": f"正在批次生成第 {idx} 卷骨架..."}, ensure_ascii=False
            ) + "\n\n"
            for chunk in agent_runners.run_volume_skeleton_planner(
                task.novel_id,
                volume_index=idx,
                user_prompt=prompt or None,
                stream=task.options.stream,
                force_json=True,
            ):
                yield chunk

    return _batch_stream()

