"""Stage order, aliases, and routing helpers."""

from __future__ import annotations

from typing import Dict, Optional


STAGE_ORDER = ["worldview", "foreshadowing", "characters", "volumes", "volume_skeleton", "writer", "editor"]
VALID_STAGES = set(STAGE_ORDER + ["evaluate"])
VALID_SCOPES = {"global", "volume", "chapter", "section", "selection"}
VALID_TASK_TYPES = {"generate", "regenerate", "patch", "batch_generate", "refine", "evaluate"}

STAGE_ALIASES = {
    "character": "characters",
    "characters": "characters",
    "skeleton": "volume_skeleton",
    "macro_skeleton": "volume_skeleton",
    "plot": "volumes",
    "director": "evaluate",
}

TASK_TYPE_ALIASES = {
    "create": "generate",
    "build": "generate",
    "rewrite": "regenerate",
    "replace": "regenerate",
    "modify": "patch",
    "update": "patch",
    "multi_generate": "batch_generate",
    "batch": "batch_generate",
    "segment_generate": "generate",
    "segment_complete": "generate",
    "segment": "generate",
    "seg_generate": "generate",
    "seg_complete": "generate",
    "complete": "generate",
    "review": "evaluate",
    "evaluate": "evaluate",
}

STAGE_TO_AGENT_NAME = {
    "worldview": "architect",
    "characters": "character",
    "foreshadowing": "architect",
    "volumes": "volumes",
    "volume_skeleton": "volume_skeleton",
    "writer": "writer",
    "editor": "editor",
    "evaluate": "copilot",
}

DEFAULT_STAGE_BY_TASK_TYPE = {
    "generate": "worldview",
    "regenerate": "worldview",
    "patch": "worldview",
    "batch_generate": "volume_skeleton",
    "refine": "editor",
    "evaluate": "evaluate",
}

DEFAULT_SCOPE_BY_STAGE = {
    "worldview": "global",
    "characters": "global",
    "foreshadowing": "global",
    "volumes": "global",
    "volume_skeleton": "volume",
    "writer": "chapter",
    "editor": "chapter",
    "evaluate": "global",
}


def normalize_stage_name(stage: Optional[str]) -> str:
    raw = (stage or "").strip()
    if not raw:
        return "worldview"
    return STAGE_ALIASES.get(raw, raw)


def normalize_task_type_name(task_type: Optional[str]) -> str:
    raw = (task_type or "").strip()
    if not raw:
        return "generate"
    return TASK_TYPE_ALIASES.get(raw, raw)


def normalize_scope_name(scope: Optional[str]) -> str:
    raw = (scope or "").strip()
    if not raw:
        return "global"
    return raw


def is_valid_stage(stage: Optional[str]) -> bool:
    return normalize_stage_name(stage) in VALID_STAGES


def is_valid_task_type(task_type: Optional[str]) -> bool:
    return normalize_task_type_name(task_type) in VALID_TASK_TYPES


def is_valid_scope(scope: Optional[str]) -> bool:
    return normalize_scope_name(scope) in VALID_SCOPES


def next_stage(stage: Optional[str]) -> Optional[str]:
    normalized = normalize_stage_name(stage)
    if normalized not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(normalized)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None


def previous_stage(stage: Optional[str]) -> Optional[str]:
    normalized = normalize_stage_name(stage)
    if normalized not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(normalized)
    return STAGE_ORDER[idx - 1] if idx - 1 >= 0 else None


def default_stage_for_task_type(task_type: Optional[str]) -> str:
    return DEFAULT_STAGE_BY_TASK_TYPE.get(normalize_task_type_name(task_type), "worldview")


def default_scope_for_stage(stage: Optional[str]) -> str:
    return DEFAULT_SCOPE_BY_STAGE.get(normalize_stage_name(stage), "global")


def requires_target(stage: Optional[str]) -> bool:
    return normalize_stage_name(stage) in {"volume_skeleton", "writer", "editor"}


def stage_to_agent_name(stage: Optional[str]) -> str:
    return STAGE_TO_AGENT_NAME.get(normalize_stage_name(stage), "copilot")


def is_terminal_stage(stage: Optional[str]) -> bool:
    return normalize_stage_name(stage) == "editor"
