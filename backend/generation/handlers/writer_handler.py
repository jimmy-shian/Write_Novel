"""Chapter writer handler."""

from __future__ import annotations

from backend.generation.routing.schema import GenerationTaskRequest
from backend.agents.chapter_writer.runner import run_chapter_writer


def run_writer_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    chapter_index = task.target.chapter_index
    if chapter_index is None and task.frontend_state:
        chapter_index = getattr(task.frontend_state, "active_chapter_index", None) or getattr(task.frontend_state, "selected_chapter", None)
    if chapter_index is None:
        from backend import persistence as db
        from backend.services.diagnostics import _find_next_unwritten_chapter_index
        try:
            chapter_index = _find_next_unwritten_chapter_index(task.novel_id)
        except Exception:
            chapter_index = None
    if chapter_index is None:
        raise ValueError("writer 階段必須由總監明確指定 chapter_index，且無法自動修復當前章節。")
    try:
        chapter_index = int(chapter_index)
    except (ValueError, TypeError):
        pass
    return run_chapter_writer(
        task.novel_id,
        chapter_index=chapter_index,
        custom_style="Classic Modernism",
        user_prompt=prompt or None,
        stream=task.options.stream,
        force_json=False,
        context_bundle=context,
    )
