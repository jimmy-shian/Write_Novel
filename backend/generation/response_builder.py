"""Unified API / SSE response builders for generation tasks."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

from .task_schema import GenerationPostProcessResult, GenerationTaskRequest, GenerationTaskResponse


def build_task_envelope(
    task: GenerationTaskRequest,
    *,
    status: str,
    event_type: Optional[str] = None,
    delta: Optional[str] = None,
    content: Optional[str] = None,
    result: Any = None,
    patches: Optional[list] = None,
    warnings: Optional[list] = None,
    state_updates: Optional[Dict[str, Any]] = None,
    error: Any = None,
    ok: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    envelope = {
        "ok": ok,
        "task_id": task.task_id,
        "task_type": task.task_type,
        "stage": task.stage,
        "scope": task.scope,
        "status": status,
        "event": event_type,
        "delta": delta,
        "content": content,
        "result": result,
        "patches": patches or [],
        "warnings": warnings or [],
        "state_updates": state_updates or {},
        "error": error,
    }
    if extra:
        envelope.update(extra)
    return envelope


def build_sse_data(envelope: Dict[str, Any]) -> str:
    return "data: " + json.dumps(envelope, ensure_ascii=False) + "\n\n"


def build_success_response(post_result: GenerationPostProcessResult) -> GenerationTaskResponse:
    return GenerationTaskResponse(
        ok=post_result.ok,
        task_id=post_result.task_id,
        task_type=post_result.task_type,
        stage=post_result.stage,
        status="completed" if post_result.ok else "failed",
        result=post_result.normalized_result,
        patches=post_result.patches,
        warnings=post_result.warnings,
        state_updates=post_result.state_updates,
        error=post_result.error,
    )


def build_failure_response(task: GenerationTaskRequest, error: Any, warnings: Optional[list] = None) -> GenerationTaskResponse:
    return GenerationTaskResponse(
        ok=False,
        task_id=task.task_id,
        task_type=task.task_type,
        stage=task.stage,
        status="failed",
        result=None,
        patches=[],
        warnings=warnings or [],
        error=error,
    )
