"""Chapter editor handler."""

from __future__ import annotations


from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.editor.runner import run_editor_agent


def run_editor_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    chapter_index = task.target.chapter_index
    if chapter_index is None:
        raise ValueError("editor 階段必須由總監明確指定 chapter_index，禁止後端默認第 1 章。")
    return run_editor_agent(
        task.novel_id,
        chapter_index=chapter_index,
        edit_instructions=prompt or None,
        stream=task.options.stream,
        force_json=False,
        context_bundle=context,
    )
