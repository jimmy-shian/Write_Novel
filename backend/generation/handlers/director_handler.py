"""Director / evaluate handler."""

from __future__ import annotations

from .. import agent_runners
from backend.services.diagnostics import detect_current_stage

from ..task_schema import GenerationTaskRequest


def run_director_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    current_stage = task.stage if task.stage != "evaluate" else detect_current_stage(task.novel_id)
    return agent_runners.run_director_decision(
        task.novel_id,
        current_stage=current_stage,
        user_prompt=prompt or None,
        chapter_index=task.target.chapter_index,
        volume_index=task.target.volume_index,
        conversation_context=task.conversation_context,
        summary_context=task.summary_context,
        extra_context=task.extra_context,
        loop_count=0,
        stream=task.options.stream,
        force_json=True,
    )

