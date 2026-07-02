"""Director / evaluate handler."""

from __future__ import annotations

from .. import agent_runners
from backend.services.diagnostics import detect_current_stage

from ..task_schema import GenerationTaskRequest


def run_director_task(task: GenerationTaskRequest, context=None):
    prompt = (task.instruction or task.user_prompt or task.hint or "").strip()
    
    if getattr(task, "is_copilot_chat", False) or getattr(task, "user_message", None) is not None:
        user_message = getattr(task, "user_message", None) or task.user_prompt or ""
        return agent_runners.run_copilot_chat(
            task.novel_id,
            user_message,
            stream=task.options.stream,
            force_json=True,
        )

    current_stage = getattr(task, "current_stage", None) or task.stage
    if not current_stage or current_stage == "evaluate":
        current_stage = detect_current_stage(task.novel_id)
        
    return agent_runners.run_director_decision(
        task.novel_id,
        current_stage=current_stage,
        user_prompt=prompt or None,
        chapter_index=task.target.chapter_index,
        volume_index=task.target.volume_index,
        character_review_mode=getattr(task, "character_review_mode", None),
        character_review_hint=getattr(task, "character_review_hint", None),
        character_review_target_content=getattr(task, "character_review_target_content", None),
        suggested_next_chapter=getattr(task, "suggested_next_chapter", None),
        conversation_context=task.conversation_context,
        summary_context=task.summary_context,
        extra_context=task.extra_context,
        loop_count=int(getattr(task, "loop_count", 0) or 0),
        stream=task.options.stream,
        force_json=True,
    )


