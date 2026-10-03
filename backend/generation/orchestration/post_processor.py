"""Shared normalization and post-processing for generation-task results."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend import persistence as db
from backend.services.diagnostics import detect_current_stage
from backend.models.parsers import extract_json_block

from backend.generation.orchestration.response_builder import build_task_envelope, build_sse_data, build_success_response, build_failure_response
from backend.generation.routing.schema import GenerationPostProcessResult, GenerationTaskRequest, GenerationTaskResponse


def parse_sse_event(chunk: str) -> Optional[Dict[str, Any]]:
    if not chunk or not isinstance(chunk, str):
        return None
    text = chunk.strip()
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if payload == "[DONE]":
        return {"type": "done"}
    try:
        return json.loads(payload)
    except Exception:
        return None


def _normalize_text_by_stage(raw: Any, target_stage: str) -> Any:
    content_str = (raw or "").strip() if isinstance(raw, str) else ""
    if not content_str:
        return {}

    parsed = None
    try:
        parsed = extract_json_block(content_str)
    except Exception:
        parsed = None

    # Priority 1: Writer and Editor stages strictly produce chapter prose
    if target_stage in {"writer", "editor"}:
        if isinstance(parsed, dict):
            stripped = content_str.strip()
            # Only unwrap if the entire response constitutes a JSON wrapper envelope,
            # never when an embedded code block is surrounded by story prose.
            is_root_envelope = (
                (stripped.startswith("{") and stripped.endswith("}"))
                or (stripped.startswith("```") and stripped.endswith("```"))
            )
            if is_root_envelope:
                # If wrapped in markdown code fence, ensure it is a single outer block
                if stripped.startswith("```") and stripped.endswith("```"):
                    lines = stripped.splitlines()
                    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
                        inner_lines = lines[1:-1]
                        if any(l.strip().startswith("```") for l in inner_lines):
                            inner_content = stripped[3:-3].strip()
                            if inner_content.lower().startswith("json"):
                                inner_content = inner_content[4:].strip()
                            try:
                                json_obj = json.loads(inner_content)
                                is_root_envelope = isinstance(json_obj, dict)
                            except Exception:
                                is_root_envelope = False

                if is_root_envelope:
                    if "content" in parsed and isinstance(parsed["content"], str):
                        return {"text": parsed["content"]}
                    if "text" in parsed and isinstance(parsed["text"], str):
                        return {"text": parsed["text"]}
        return {"text": content_str}

    # Priority 2: Structured stages expecting JSON schemas
    if isinstance(parsed, (dict, list)) and parsed:
        return parsed

    return parsed if parsed is not None else {"text": content_str}


def _normalize_result_text(task: GenerationTaskRequest, raw_text: str) -> Any:
    return _normalize_text_by_stage(raw_text, task.stage)


def _derive_patches(task: GenerationTaskRequest, normalized_result: Any) -> List[Dict[str, Any]]:
    patches: List[Dict[str, Any]] = []

    if task.stage in {"writer", "editor"}:
        chapter_index = (task.target.chapter_index if task.target else None) or 1
        content = ""
        if isinstance(normalized_result, dict) and "text" in normalized_result:
            content = normalized_result["text"]
        elif isinstance(normalized_result, str):
            content = normalized_result
        if content:
            patches.append(
                {
                    "op": "replace",
                    "path": f"/chapters/{chapter_index}/content",
                    "value": content,
                }
            )
        return patches

    if isinstance(normalized_result, dict):
        for key, value in normalized_result.items():
            if key in {"result", "status", "error"}:
                continue
            patches.append({"op": "replace", "path": f"/{key}", "value": value})
    elif isinstance(normalized_result, list):
        patches.append({"op": "replace", "path": f"/{task.stage}", "value": normalized_result})
    elif normalized_result not in (None, "", {}):
        patches.append({"op": "replace", "path": f"/{task.stage}", "value": normalized_result})

    return patches


def _build_state_updates(task: GenerationTaskRequest) -> Dict[str, Any]:
    novel_id = task.novel_id
    updates: Dict[str, Any] = {
        "backend_stage": detect_current_stage(novel_id),
    }

    wb = db.get_latest_worldbuilding(novel_id)
    char = db.get_latest_characters(novel_id)
    plot = db.get_stitched_plot(novel_id)
    vols = db.get_volumes(novel_id)

    if wb:
        updates["worldbuilding"] = {
            "version": wb.get("version"),
            "content": wb.get("content"),
        }
    if char:
        updates["characters"] = {
            "version": char.get("version"),
            "parsed_data": char.get("parsed_data"),
        }
    if plot:
        updates["plot"] = plot
    if vols:
        updates["volumes"] = vols

    if getattr(db, "has_geometry", None) and db.has_geometry(novel_id):
        updates["geometry"] = db.get_geometry_stats(novel_id)

    if task.stage in {"writer", "editor"} and task.target.chapter_index is not None:
        chapter = db.get_latest_chapter(novel_id, int(task.target.chapter_index))
        if chapter:
            updates["chapter"] = chapter

    return updates


def build_post_process_result(
    task: GenerationTaskRequest,
    *,
    raw_text: str,
    sse_events: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
    error: Any = None,
    ok: bool = True,
) -> GenerationPostProcessResult:
    normalized_result = _normalize_result_text(task, raw_text)
    patches = _derive_patches(task, normalized_result)
    state_updates = _build_state_updates(task)
    return GenerationPostProcessResult(
        ok=ok,
        task_id=task.task_id,
        task_type=task.task_type,
        stage=task.stage,
        normalized_result=normalized_result,
        patches=patches,
        state_updates=state_updates,
        sse_events=sse_events or [],
        warnings=warnings or [],
        error=error,
        lock_released=False,
    )


def build_final_response(task: GenerationTaskRequest, post_result: GenerationPostProcessResult) -> GenerationTaskResponse:
    response = build_success_response(post_result)
    response.status = "completed" if post_result.ok else "failed"
    return response


def iter_post_processed_generation_stream(
    task: GenerationTaskRequest,
    stream: Iterable[str],
    *,
    warnings: Optional[List[str]] = None,
) -> Iterable[str]:
    """Pass through agent SSE while standardizing the final done envelope."""
    collected_text: List[str] = []
    event_log: List[Dict[str, Any]] = []
    failed = False
    failure_message: Optional[str] = None
    import time
    last_heartbeat = time.time()

    try:
        for chunk in stream:
            now = time.time()
            if now - last_heartbeat > 15:
                try:
                    if task and getattr(task, "novel_id", None):
                        db.update_pipeline_heartbeat(task.novel_id)
                except Exception as exc:
                    print(f"[WARN] Pipeline heartbeat update failed (novel {getattr(task, 'novel_id', None)}): {exc}")
                last_heartbeat = now

            event = parse_sse_event(chunk)
            if event:
                event_type = event.get("type")
                if event_type == "content":
                    collected_text.append(event.get("delta", ""))
                    event_log.append({"type": "content"})
                elif event_type == "thinking":
                    event_log.append({"type": "thinking"})
                elif event_type == "status":
                    event_log.append({"type": "status", "message": event.get("message", "")})
                elif event_type == "retrying":
                    event_log.append({"type": "retrying", "message": event.get("message", "")})
                elif event_type == "error":
                    failed = True
                    failure_message = event.get("message") or "Agent returned an error."
                    event_log.append({"type": "error", "message": failure_message})
                    yield chunk
                    continue
                elif event_type == "done":
                    # We replace legacy done events with a unified envelope at the end.
                    continue
            yield chunk
    except Exception as exc:
        failed = True
        failure_message = str(exc)
        event_log.append({"type": "error", "message": failure_message})
        yield build_sse_data(
            build_task_envelope(
                task,
                status="failed",
                result={"error": failure_message},
                patches=[],
                warnings=warnings or [],
                state_updates=_build_state_updates(task),
                error=failure_message,
                ok=False,
                extra={"type": "error"},
            )
        )
    finally:
        raw_text = "".join(collected_text)
        post_result = build_post_process_result(
            task,
            raw_text=raw_text,
            sse_events=event_log,
            warnings=warnings or [],
            error=failure_message,
            ok=not failed,
        )
        post_result.lock_released = True
        final_response = build_final_response(task, post_result)
        yield build_sse_data(
            build_task_envelope(
                task,
                status=final_response.status,
                result=post_result.normalized_result,
                patches=post_result.patches,
                warnings=post_result.warnings,
                state_updates=post_result.state_updates,
                error=post_result.error,
                ok=post_result.ok,
                extra={
                    "type": "done",
                    "normalized_result": post_result.normalized_result,
                    "sse_events": post_result.sse_events,
                    "lock_released": True,
                },
            )
        )


def build_non_stream_response(task: GenerationTaskRequest, stream: Iterable[str], warnings: Optional[List[str]] = None) -> GenerationTaskResponse:
    collected = []
    event_log = []
    failed = False
    failure_message = None

    try:
        for chunk in stream:
            event = parse_sse_event(chunk)
            if not event:
                continue
            event_type = event.get("type")
            if event_type == "content":
                collected.append(event.get("delta", ""))
            elif event_type == "thinking":
                collected.append(event.get("delta", ""))
            elif event_type == "error":
                failed = True
                failure_message = event.get("message")
            event_log.append(event)
    except Exception as exc:
        failed = True
        failure_message = str(exc)
        event_log.append({"type": "error", "message": failure_message})

    post_result = build_post_process_result(
        task,
        raw_text="".join(collected),
        sse_events=event_log,
        warnings=warnings or [],
        error=failure_message,
        ok=not failed,
    )
    post_result.lock_released = True
    if post_result.ok:
        return build_success_response(post_result)
    return build_failure_response(task, post_result.error, warnings=post_result.warnings)
