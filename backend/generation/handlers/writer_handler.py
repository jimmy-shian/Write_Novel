"""Chapter writer handler."""

from __future__ import annotations

from .. import agent_runners
from ..task_schema import GenerationTaskRequest


def run_writer_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    chapter_index = task.target.chapter_index
    if chapter_index is None:
        raise ValueError("writer 階段必須由總監明確指定 chapter_index，禁止後端默認第 1 章。")
    return agent_runners.run_chapter_writer(
        task.novel_id,
        chapter_index=chapter_index,
        custom_style="Classic Modernism",
        user_prompt=prompt or None,
        stream=task.options.stream,
        force_json=False,
    )
