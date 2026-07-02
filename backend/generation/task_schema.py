"""Canonical payload / response schema for generation tasks."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .stage_registry import (
    default_scope_for_stage,
    default_stage_for_task_type,
    normalize_scope_name,
    normalize_stage_name,
    normalize_task_type_name,
)


TASK_TYPES = ("generate", "regenerate", "patch", "batch_generate", "refine", "evaluate")
TASK_SCOPES = ("global", "volume", "chapter", "section", "selection")
CONTEXT_MODES = ("full", "compact", "minimal")


class GenerationTaskTarget(BaseModel):
    volume_id: Optional[str] = None
    chapter_id: Optional[str] = None
    section_id: Optional[str] = None
    volume_index: Optional[int] = None
    chapter_index: Optional[int] = None
    section_index: Optional[int] = None
    selection: Optional[List[Any]] = None

    class Config:
        extra = "allow"


class GenerationTaskOptions(BaseModel):
    batch: bool = False
    overwrite: bool = False
    stream: bool = True
    dry_run: bool = False

    class Config:
        extra = "allow"


class GenerationTaskFrontendState(BaseModel):
    current_stage: Optional[str] = None
    selected_volume: Optional[Any] = None
    selected_chapter: Optional[Any] = None

    class Config:
        extra = "allow"


class GenerationTaskRequest(BaseModel):
    novel_id: str
    task_type: str = "generate"
    stage: Optional[str] = None
    scope: str = "global"
    target: GenerationTaskTarget = Field(default_factory=GenerationTaskTarget)
    context_mode: str = "compact"
    options: GenerationTaskOptions = Field(default_factory=GenerationTaskOptions)
    frontend_state: GenerationTaskFrontendState = Field(default_factory=GenerationTaskFrontendState)
    instruction: Optional[str] = None
    user_prompt: Optional[str] = None
    hint: Optional[str] = None
    task_id: Optional[str] = None
    conversation_context: Optional[str] = None
    summary_context: Optional[str] = None
    extra_context: Optional[str] = None

    class Config:
        extra = "allow"


class GenerationTaskResponse(BaseModel):
    ok: bool
    task_id: str
    task_type: str
    stage: str
    status: str
    result: Any = None
    patches: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    state_updates: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Any] = None

    class Config:
        extra = "allow"


class GenerationPostProcessResult(BaseModel):
    ok: bool
    task_id: str
    task_type: str
    stage: str
    normalized_result: Any = None
    patches: List[Dict[str, Any]] = Field(default_factory=list)
    state_updates: Dict[str, Any] = Field(default_factory=dict)
    sse_events: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error: Optional[Any] = None
    lock_released: bool = False

    class Config:
        extra = "allow"


def coerce_generation_task_request(payload: Any) -> GenerationTaskRequest:
    """Normalize aliases and generate a task id when the caller omits one."""
    if isinstance(payload, GenerationTaskRequest):
        task = payload
    else:
        if hasattr(payload, "dict"):
            data = payload.dict()
        elif isinstance(payload, dict):
            data = dict(payload)
        else:
            raise TypeError(f"Unsupported generation task payload type: {type(payload)!r}")

        if not data.get("instruction") and data.get("user_prompt"):
            data["instruction"] = data.get("user_prompt")
        if not data.get("task_id"):
            data["task_id"] = str(uuid.uuid4())

        if "stream" in data:
            options = data.get("options") if isinstance(data.get("options"), dict) else {}
            if not isinstance(options, dict):
                options = {}
            options.setdefault("stream", bool(data.get("stream")))
            data["options"] = options
        if "force_json" in data:
            options = data.get("options") if isinstance(data.get("options"), dict) else {}
            if not isinstance(options, dict):
                options = {}
            options.setdefault("force_json", bool(data.get("force_json")))
            data["options"] = options

        data["task_type"] = normalize_task_type_name(data.get("task_type"))
        if not data.get("stage"):
            data["stage"] = default_stage_for_task_type(data["task_type"])
        data["stage"] = normalize_stage_name(data.get("stage"))
        if not data.get("scope"):
            data["scope"] = default_scope_for_stage(data["stage"])
        data["scope"] = normalize_scope_name(data.get("scope"))
        if not data.get("context_mode"):
            data["context_mode"] = "compact"

        if not data.get("target"):
            data["target"] = {}
        if not data.get("options"):
            data["options"] = {}
        if not data.get("frontend_state"):
            data["frontend_state"] = {}

        task = GenerationTaskRequest(**data)

    if not task.task_id:
        task.task_id = str(uuid.uuid4())
    task.task_type = normalize_task_type_name(task.task_type)
    task.stage = normalize_stage_name(task.stage)
    if not task.scope:
        task.scope = default_scope_for_stage(task.stage)
    task.scope = normalize_scope_name(task.scope)
    if not task.context_mode:
        task.context_mode = "compact"
    return task
