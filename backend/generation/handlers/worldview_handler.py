"""Worldview generation handler."""

from __future__ import annotations

from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.story_architect.runner import run_story_architect
from backend.agents.incremental.runner import run_incremental_architect


def run_worldview_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    target_section = getattr(task, "target_section", None)
    if task.task_type == "patch" and target_section:
        return run_incremental_architect(
            task.novel_id,
            target_section,
            prompt,
            stream=task.options.stream,
            force_json=True,
        )
    return run_story_architect(
        task.novel_id,
        prompt,
        stream=task.options.stream,
        force_json=True,
    )


