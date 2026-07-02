"""Foreshadowing generation handler."""

from __future__ import annotations

from .. import agent_runners

from ..task_schema import GenerationTaskRequest


def run_foreshadowing_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    return agent_runners.run_foreshadowing_orchestrator(
        task.novel_id,
        user_prompt=prompt or None,
        stream=task.options.stream,
        force_json=True,
    )

