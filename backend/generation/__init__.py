"""Shared generation-task orchestration package."""

from .task_schema import (
    GenerationTaskRequest,
    GenerationTaskResponse,
    GenerationTaskOptions,
    GenerationTaskTarget,
    GenerationTaskFrontendState,
    GenerationPostProcessResult,
    coerce_generation_task_request,
)
from .context_builder import build_generation_context
from .task_router import execute_generation_task, resolve_generation_route, run_routed_generation, stream_generation_task
from .task_validator import prepare_generation_task, resolve_generation_task_target, validate_generation_task_request
