"""Volumes planning handler."""

from __future__ import annotations


from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.volumes_planner.runner import run_volumes_planner


def _resolve_mode(task: GenerationTaskRequest) -> str:
    if task.task_type == "batch_generate":
        return "patch"
    if task.options.overwrite:
        return "generate"
    if task.scope in {"volume", "selection"}:
        return "patch"
    return "generate"


def run_volumes_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    mode = _resolve_mode(task)
    target_vol_idx = task.target.volume_index
    if target_vol_idx is None and task.target.section_index is not None:
        target_vol_idx = task.target.section_index

    return run_volumes_planner(
        task.novel_id,
        user_prompt=prompt or None,
        hint=task.hint,
        mode=mode,
        target_vol_idx=target_vol_idx,
        stream=task.options.stream,
        force_json=True,
    )

