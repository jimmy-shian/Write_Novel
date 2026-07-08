"""Generation-task routing and orchestration package."""

from backend.generation.routing.schema import (
    GenerationTaskRequest,
    GenerationTaskResponse,
    GenerationTaskOptions,
    GenerationTaskTarget,
    GenerationTaskFrontendState,
    GenerationPostProcessResult,
    coerce_generation_task_request,
)
from backend.generation.orchestration.context_builder import build_generation_context
from backend.generation.routing.router import execute_generation_task, resolve_generation_route, run_routed_generation, stream_generation_task
from backend.generation.routing.validator import prepare_generation_task, resolve_generation_task_target, validate_generation_task_request
