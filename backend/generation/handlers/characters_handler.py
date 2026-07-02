"""Character generation handler."""

from __future__ import annotations

from .. import agent_runners
from ..task_schema import GenerationTaskRequest


def _resolve_mode(task: GenerationTaskRequest) -> str:
    if task.task_type == "generate":
        return "generate"
    if task.options.overwrite or task.task_type in {"regenerate", "patch", "refine", "batch_generate"}:
        return "expand"
    if task.scope in {"selection", "chapter", "section"}:
        return "expand"
    return "generate"


def run_characters_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    
    if task.task_type == "patch":
        field_name = getattr(task, "field_name", None)
        target_char_idx = getattr(task, "target_char_index", None)
        if target_char_idx is not None and field_name:
            return agent_runners.run_incremental_character_designer(
                task.novel_id,
                target_char_idx,
                field_name,
                prompt,
                stream=task.options.stream,
                force_json=True,
            )
            
    mode = _resolve_mode(task)
    target_char_index = task.target.section_index
    if target_char_index is None and task.target.chapter_index is not None:
        target_char_index = task.target.chapter_index

    return agent_runners.run_character_designer(
        task.novel_id,
        user_prompt=prompt or None,
        hint=task.hint,
        mode=mode,
        target_char_index=target_char_index,
        stream=task.options.stream,
        force_json=True,
    )


