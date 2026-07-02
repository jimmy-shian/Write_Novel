"""Chapter editor handler."""

from __future__ import annotations

from .. import agent_runners

from ..task_schema import GenerationTaskRequest


def run_editor_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    chapter_index = task.target.chapter_index
    if chapter_index is None:
        chapter_index = 1
    return agent_runners.run_editor_agent(
        task.novel_id,
        chapter_index=chapter_index,
        edit_instructions=prompt or None,
        stream=task.options.stream,
        force_json=False,
    )

