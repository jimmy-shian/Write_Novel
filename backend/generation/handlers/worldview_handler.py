"""Worldview generation handler."""

from __future__ import annotations

from .. import agent_runners
from ..task_schema import GenerationTaskRequest


def run_worldview_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    return agent_runners.run_story_architect(
        task.novel_id,
        prompt,
        stream=task.options.stream,
        force_json=True,
    )

