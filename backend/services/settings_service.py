"""Shared settings snapshot and partial update helpers."""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from backend import db
from backend.llm import get_config_for_agent, get_default_config


CANONICAL_AGENT_NAMES = [
    "global",
    "architect",
    "character",
    "volumes",
    "volume_skeleton",
    "plot",
    "writer",
    "editor",
    "copilot",
]

AGENT_ALIASES = {
    "characters": "character",
}

DISPLAY_NAMES = {
    "global": "Global 全域 (預設設置)",
    "architect": "1️⃣ Story Architect (故事結構架構師)",
    "character": "2️⃣ Character Designer (角色設計大師)",
    "characters": "2️⃣ Character Designer (角色設計大師)",
    "volumes": "3️⃣ Volumes Planner (篇卷規劃師)",
    "volume_skeleton": "4️⃣ Volume Skeleton Planner (篇卷骨架規劃師)",
    "plot": "5️⃣ Plot Planner (章節劇情規劃師)",
    "writer": "6️⃣ Chapter Writer (小說正文寫作作家)",
    "editor": "7️⃣ Editor Agent (精緻文風編輯)",
    "copilot": "🧠 Co-Pilot Orchestrator (AI 總監)",
}

NUMERIC_RANGES = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
}


def _get_plot_review_batch_size() -> int:
    try:
        value = int(os.getenv("PLOT_REVIEW_BATCH_SIZE", "3"))
        return value if value > 0 else 3
    except Exception:
        return 3


def normalize_agent_name(agent_name: Optional[str]) -> str:
    raw = (agent_name or "").strip()
    if not raw:
        return ""
    return AGENT_ALIASES.get(raw, raw)


def _coerce_bool(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return 1
        if lowered in {"0", "false", "no", "off"}:
            return 0
    raise ValueError("enable_thinking must be a boolean-like value")


def _coerce_float(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if not math.isfinite(num):
        raise ValueError(f"{field_name} must be finite")
    low, high = NUMERIC_RANGES[field_name]
    if not (low <= num <= high):
        raise ValueError(f"{field_name} must be within {low} and {high}")
    return num


def _coerce_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    try:
        num = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")
    if num <= 0:
        raise ValueError(f"{field_name} must be positive")
    return num


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("string fields must be strings")
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _format_effective_config(agent_name: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    defaults = get_default_config()
    return {
        "api_key": config.get("api_key", ""),
        "base_url": config.get("base_url", defaults["base_url"]),
        "model": config.get("model", ""),
        "temperature": config.get("temperature", defaults["temperature"]),
        "top_p": config.get("top_p", defaults["top_p"]),
        "max_tokens": config.get("max_tokens", defaults["max_tokens"]),
        "enable_thinking": int(config.get("enable_thinking", defaults["enable_thinking"])),
        "display_name": DISPLAY_NAMES.get(agent_name, agent_name),
        "plot_review_batch_size": _get_plot_review_batch_size(),
    }


def _resolve_db_source_name(agent_name: str, configs: Mapping[str, Mapping[str, Any]]) -> str:
    if agent_name in configs:
        return agent_name
    alias = next((alias for alias, canonical in AGENT_ALIASES.items() if canonical == agent_name and alias in configs), None)
    if alias:
        return alias
    return agent_name


def build_settings_snapshot() -> Dict[str, Any]:
    configs = db.get_agent_configs()
    snapshot: Dict[str, Any] = {}

    all_names = set(CANONICAL_AGENT_NAMES) | set(configs.keys())
    for agent_name in sorted(all_names):
        canonical_name = normalize_agent_name(agent_name) or agent_name
        lookup_name = _resolve_db_source_name(canonical_name, configs)
        effective = get_config_for_agent(lookup_name)
        record = _format_effective_config(canonical_name, effective)
        snapshot[canonical_name] = record

    for alias, canonical in AGENT_ALIASES.items():
        if canonical in snapshot:
            alias_record = dict(snapshot[canonical])
            alias_record["alias_of"] = canonical
            snapshot[alias] = alias_record

    try:
        models_config = json.loads(os.getenv("MODELS_CONFIG", "{}"))
    except Exception:
        models_config = {}
    snapshot["_modelsConfig"] = models_config
    return snapshot


def _merge_patch_into_effective_config(agent_name: str, patch: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    normalized_agent = normalize_agent_name(agent_name) or agent_name
    current = dict(get_config_for_agent(normalized_agent))
    warnings = []

    for field in ("api_key", "base_url", "model"):
        if field not in patch:
            continue
        try:
            value = _coerce_str(patch.get(field))
        except ValueError as e:
            raise ValueError(str(e))
        if value is not None:
            current[field] = value

    if "temperature" in patch:
        current["temperature"] = _coerce_float(patch.get("temperature"), "temperature")
    if "top_p" in patch:
        current["top_p"] = _coerce_float(patch.get("top_p"), "top_p")
    if "max_tokens" in patch:
        current["max_tokens"] = _coerce_int(patch.get("max_tokens"), "max_tokens")
    if "enable_thinking" in patch:
        current["enable_thinking"] = _coerce_bool(patch.get("enable_thinking"))

    if not any(key in patch for key in ("api_key", "base_url", "model", "temperature", "top_p", "max_tokens", "enable_thinking")):
        warnings.append("No settings fields were updated.")

    return current, {"warnings": warnings}


def save_settings_patch(agent_name: str, patch: Mapping[str, Any]) -> Dict[str, Any]:
    normalized_agent = normalize_agent_name(agent_name) or agent_name
    effective_config, meta = _merge_patch_into_effective_config(normalized_agent, patch)
    db.save_agent_config(
        normalized_agent,
        effective_config.get("api_key", ""),
        effective_config.get("base_url", ""),
        effective_config.get("model", ""),
        effective_config.get("temperature", get_default_config()["temperature"]),
        effective_config.get("top_p", get_default_config()["top_p"]),
        effective_config.get("max_tokens", get_default_config()["max_tokens"]),
        effective_config.get("enable_thinking", get_default_config()["enable_thinking"]),
    )
    return {
        "agent_name": agent_name,
        "stored_agent_name": normalized_agent,
        "config": _format_effective_config(normalized_agent, effective_config),
        **meta,
    }


def apply_settings_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Support both single-agent partial updates and bulk configs payloads."""
    if "configs" in payload and isinstance(payload["configs"], Mapping):
        results = []
        warnings = []
        for agent_name, agent_patch in payload["configs"].items():
            if not isinstance(agent_patch, Mapping):
                raise ValueError(f"Invalid settings patch for agent '{agent_name}'")
            result = save_settings_patch(agent_name, agent_patch)
            results.append(result)
            warnings.extend(result.get("warnings", []))
        return {
            "status": "success",
            "updated_agents": results,
            "warnings": warnings,
        }

    agent_name = payload.get("agent_name")
    if not agent_name:
        raise ValueError("agent_name is required")

    allowed_patch = {
        key: payload.get(key)
        for key in ("api_key", "base_url", "model", "temperature", "top_p", "max_tokens", "enable_thinking")
        if key in payload
    }
    result = save_settings_patch(agent_name, allowed_patch)
    return {
        "status": "success",
        "updated_agent": result,
        "warnings": result.get("warnings", []),
    }
