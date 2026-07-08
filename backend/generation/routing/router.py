"""Unified task routing for generation-task requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from backend.generation.orchestration.context_builder import build_generation_context
from backend.generation.orchestration.lock_manager import pipeline_lock
from backend.generation.orchestration.post_processor import (
    build_non_stream_response,
    iter_post_processed_generation_stream,
)
from backend.generation.orchestration.response_builder import build_failure_response, build_sse_data, build_task_envelope
from backend.generation.handlers import HANDLER_REGISTRY
from .stage_registry import default_stage_for_task_type, is_valid_stage, normalize_stage_name
from .schema import GenerationTaskRequest, GenerationTaskResponse
from .validator import prepare_generation_task


@dataclass
class GenerationRoute:
    stage: str
    task_type: str
    scope: str
    handler_name: str
    handler: Callable[[GenerationTaskRequest, Optional[Dict[str, Any]]], Iterable[str]]
    persist_mode: str = "legacy"
    warnings: List[str] = field(default_factory=list)


def resolve_generation_route(task: GenerationTaskRequest) -> GenerationRoute:
    stage = normalize_stage_name(task.stage)
    if not is_valid_stage(stage):
        stage = default_stage_for_task_type(task.task_type)

    handler = HANDLER_REGISTRY.get(stage)
    handler_name = stage
    warnings: List[str] = []

    if handler is None and task.task_type == "evaluate":
        handler = HANDLER_REGISTRY["evaluate"]
        handler_name = "evaluate"
    elif handler is None:
        fallback_stage = default_stage_for_task_type(task.task_type)
        handler = HANDLER_REGISTRY.get(fallback_stage, HANDLER_REGISTRY["worldview"])
        handler_name = fallback_stage if fallback_stage in HANDLER_REGISTRY else "worldview"
        warnings.append(f"Falling back to {handler_name} handler for task_type={task.task_type}, stage={task.stage}")

    return GenerationRoute(
        stage=stage,
        task_type=task.task_type,
        scope=task.scope,
        handler_name=handler_name,
        handler=handler,
        persist_mode="legacy",
        warnings=warnings,
    )


def run_routed_generation(task: GenerationTaskRequest, context_bundle: Optional[Dict[str, Any]] = None):
    route = resolve_generation_route(task)
    return route.handler(task, context_bundle)


def stream_generation_task(payload: Any):
    """Return an SSE generator for the unified generation-task API."""
    task, validation = prepare_generation_task(payload)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    context_bundle = build_generation_context(task)
    route = resolve_generation_route(task)
    warnings = list(validation.warnings) + list(route.warnings)

    if task.options.dry_run:
        def _dry_run_generator():
            yield build_sse_data(
                build_task_envelope(
                    task,
                    status="completed",
                    result={
                        "dry_run": True,
                        "handler": route.handler_name,
                        "stage": route.stage,
                        "task_type": route.task_type,
                        "scope": route.scope,
                    },
                    patches=[],
                    warnings=warnings,
                    state_updates={"backend_stage": route.stage},
                    error=None,
                    ok=True,
                    extra={
                        "type": "done",
                        "normalized_result": {
                            "dry_run": True,
                            "handler": route.handler_name,
                            "stage": route.stage,
                            "task_type": route.task_type,
                            "scope": route.scope,
                        },
                        "sse_events": [],
                        "lock_released": True,
                    },
                )
            )
        return _dry_run_generator()

    def _generator():
        with pipeline_lock(task.novel_id):
            try:
                source_stream = route.handler(task, context_bundle)
                yield from iter_post_processed_generation_stream(task, source_stream, warnings=warnings)
            except Exception as exc:
                error_message = str(exc)
                failed_stream = [
                    build_sse_data(
                        build_task_envelope(
                            task,
                            status="failed",
                            result={"error": error_message},
                            patches=[],
                            warnings=warnings + [error_message],
                            state_updates={},
                            error=error_message,
                            ok=False,
                            extra={"type": "error"},
                        )
                    )
                ]
                yield from iter_post_processed_generation_stream(
                    task,
                    failed_stream,
                    warnings=warnings + [error_message],
                )

    return _generator()


def execute_generation_task(payload: Any) -> GenerationTaskResponse:
    """Run a unified generation task without keeping the HTTP connection open."""
    task, validation = prepare_generation_task(payload)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    context_bundle = build_generation_context(task)
    route = resolve_generation_route(task)
    warnings = list(validation.warnings) + list(route.warnings)

    if task.options.dry_run:
        return GenerationTaskResponse(
            ok=True,
            task_id=task.task_id,
            task_type=task.task_type,
            stage=task.stage,
            status="completed",
            result={
                "dry_run": True,
                "handler": route.handler_name,
                "stage": route.stage,
                "task_type": route.task_type,
                "scope": route.scope,
            },
            patches=[],
            warnings=warnings,
            state_updates={"backend_stage": route.stage},
            error=None,
        )

    with pipeline_lock(task.novel_id):
        try:
            source_stream = route.handler(task, context_bundle)
            response = build_non_stream_response(task, source_stream, warnings=warnings)
            return response
        except Exception as exc:
            return build_failure_response(task, str(exc), warnings=warnings + [str(exc)])
