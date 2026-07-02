"""Validation and default-resolution helpers for generation-task payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend import db

from .stage_registry import (
    default_scope_for_stage,
    is_valid_scope,
    is_valid_stage,
    is_valid_task_type,
    normalize_scope_name,
    normalize_stage_name,
    normalize_task_type_name,
    requires_target,
)
from .task_schema import GenerationTaskRequest, coerce_generation_task_request


@dataclass
class GenerationTaskValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    normalized_task: Optional[GenerationTaskRequest] = None


def normalize_generation_task_payload(payload: Any) -> GenerationTaskRequest:
    return coerce_generation_task_request(payload)


def _infer_chapter_index(novel_id: str) -> Optional[int]:
    volumes = db.get_volumes(novel_id) or []
    total = db.get_total_chapter_count(volumes)
    if total <= 0:
        return 1

    written = set()
    for chapter in db.get_all_chapters_latest(novel_id) or []:
        try:
            idx = int(chapter.get("chapter_index"))
        except Exception:
            continue
        written.add(idx)

    for idx in range(1, total + 1):
        if idx not in written:
            return idx
    return total


def _infer_volume_index(novel_id: str) -> Optional[int]:
    volumes = db.get_volumes(novel_id) or []
    if not volumes:
        return 1

    for vol in volumes:
        outline = vol.get("chapters_outline")
        if not outline:
            try:
                return int(vol.get("volume_index"))
            except Exception:
                continue
        if isinstance(outline, str):
            try:
                import json

                outline = json.loads(outline)
            except Exception:
                outline = []
        if not outline:
            try:
                return int(vol.get("volume_index"))
            except Exception:
                continue
    try:
        return int(volumes[0].get("volume_index"))
    except Exception:
        return 1


def resolve_generation_task_target(task: GenerationTaskRequest) -> GenerationTaskRequest:
    """Fill in task target defaults from backend data when the caller omitted them."""
    if task.stage in {"writer", "editor"} and task.target.chapter_index is None:
        task.target.chapter_index = _infer_chapter_index(task.novel_id)

    if task.stage == "volume_skeleton" and task.target.volume_index is None:
        task.target.volume_index = _infer_volume_index(task.novel_id)

    if task.stage == "volumes" and task.scope not in {"global", "volume"}:
        task.scope = "global"

    if task.scope == "selection" and not task.target.selection:
        task.target.selection = []

    return task


def validate_generation_task_request(task: GenerationTaskRequest) -> GenerationTaskValidationResult:
    warnings: List[str] = []
    errors: List[str] = []

    task.task_type = normalize_task_type_name(task.task_type)
    task.stage = normalize_stage_name(task.stage)
    task.scope = normalize_scope_name(task.scope)
    if not task.context_mode:
        task.context_mode = "compact"

    if not is_valid_task_type(task.task_type):
        errors.append(f"Invalid task_type: {task.task_type}")
    if not is_valid_stage(task.stage):
        errors.append(f"Invalid stage: {task.stage}")
    if not is_valid_scope(task.scope):
        errors.append(f"Invalid scope: {task.scope}")
    if task.context_mode not in {"full", "compact", "minimal"}:
        errors.append(f"Invalid context_mode: {task.context_mode}")

    if task.frontend_state and task.frontend_state.current_stage:
        frontend_stage = normalize_stage_name(task.frontend_state.current_stage)
        if frontend_stage != task.stage:
            warnings.append(
                f"frontend_state.current_stage={frontend_stage} is treated as reference only; backend stage stays {task.stage}."
            )

    if requires_target(task.stage):
        if task.stage in {"writer", "editor"} and task.target.chapter_index is None:
            warnings.append("chapter_index was not provided; backend will infer it from DB state.")
        if task.stage == "volume_skeleton" and task.target.volume_index is None:
            warnings.append("volume_index was not provided; backend will infer it from DB state.")

    if task.task_type == "batch_generate" and not task.options.batch:
        warnings.append("batch_generate implies options.batch=true; coercing it on the server.")
        task.options.batch = True

    return GenerationTaskValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        normalized_task=task,
    )


def validate_or_raise(task: GenerationTaskRequest) -> GenerationTaskValidationResult:
    result = validate_generation_task_request(task)
    if not result.ok:
        raise ValueError("; ".join(result.errors))
    return result


def prepare_generation_task(payload: Any) -> Tuple[GenerationTaskRequest, GenerationTaskValidationResult]:
    task = normalize_generation_task_payload(payload)
    task = resolve_generation_task_target(task)
    result = validate_generation_task_request(task)
    return task, result
