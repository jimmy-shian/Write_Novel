# -*- coding: utf-8 -*-
"""
Environment file (.env) manager for AI Novel Factory.
Handles safe read, update, and synchronization of environment variables with UTF-8 encoding.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

AGENT_ENV_KEY_MAP = {
    "global": {
        "api_key": ["NVIDIA_API_KEY_GLOBAL"],
        "base_url": ["BASE_URL_GLOBAL", "DEFAULT_BASE_URL"],
        "model": ["MODEL_GLOBAL"],
        "temperature": ["TEMPERATURE_GLOBAL", "DEFAULT_TEMPERATURE"],
        "top_p": ["TOP_P_GLOBAL", "DEFAULT_TOP_P"],
        "max_tokens": ["MAX_TOKENS_GLOBAL", "DEFAULT_MAX_TOKENS"],
        "enable_thinking": ["ENABLE_THINKING_GLOBAL", "DEFAULT_ENABLE_THINKING"],
    },
    "architect": {
        "api_key": ["NVIDIA_API_KEY_ARCHITECT"],
        "base_url": ["BASE_URL_ARCHITECT"],
        "model": ["MODEL_ARCHITECT"],
        "temperature": ["TEMPERATURE_ARCHITECT"],
        "top_p": ["TOP_P_ARCHITECT"],
        "max_tokens": ["MAX_TOKENS_ARCHITECT"],
        "enable_thinking": ["ENABLE_THINKING_ARCHITECT"],
    },
    "character": {
        "api_key": ["NVIDIA_API_KEY_CHARACTER"],
        "base_url": ["BASE_URL_CHARACTER"],
        "model": ["MODEL_CHARACTER"],
        "temperature": ["TEMPERATURE_CHARACTER"],
        "top_p": ["TOP_P_CHARACTER"],
        "max_tokens": ["MAX_TOKENS_CHARACTER"],
        "enable_thinking": ["ENABLE_THINKING_CHARACTER"],
    },
    "volumes": {
        "api_key": ["NVIDIA_API_KEY_VOLUMES"],
        "base_url": ["BASE_URL_VOLUMES"],
        "model": ["MODEL_VOLUMES"],
        "temperature": ["TEMPERATURE_VOLUMES"],
        "top_p": ["TOP_P_VOLUMES"],
        "max_tokens": ["MAX_TOKENS_VOLUMES"],
        "enable_thinking": ["ENABLE_THINKING_VOLUMES"],
    },
    "volume_skeleton": {
        "api_key": ["NVIDIA_API_KEY_VOLUME_SKELETON"],
        "base_url": ["BASE_URL_VOLUME_SKELETON"],
        "model": ["MODEL_VOLUME_SKELETON"],
        "temperature": ["TEMPERATURE_VOLUME_SKELETON"],
        "top_p": ["TOP_P_VOLUME_SKELETON"],
        "max_tokens": ["MAX_TOKENS_VOLUME_SKELETON"],
        "enable_thinking": ["ENABLE_THINKING_VOLUME_SKELETON"],
    },
    "plot": {
        "api_key": ["NVIDIA_API_KEY_PLOT"],
        "base_url": ["BASE_URL_PLOT"],
        "model": ["MODEL_PLOT"],
        "temperature": ["TEMPERATURE_PLOT"],
        "top_p": ["TOP_P_PLOT"],
        "max_tokens": ["MAX_TOKENS_PLOT"],
        "enable_thinking": ["ENABLE_THINKING_PLOT"],
    },
    "writer": {
        "api_key": ["NVIDIA_API_KEY_WRITER"],
        "base_url": ["BASE_URL_WRITER"],
        "model": ["MODEL_WRITER"],
        "temperature": ["TEMPERATURE_WRITER"],
        "top_p": ["TOP_P_WRITER"],
        "max_tokens": ["MAX_TOKENS_WRITER"],
        "enable_thinking": ["ENABLE_THINKING_WRITER"],
    },
    "editor": {
        "api_key": ["NVIDIA_API_KEY_EDITOR"],
        "base_url": ["BASE_URL_EDITOR"],
        "model": ["MODEL_EDITOR"],
        "temperature": ["TEMPERATURE_EDITOR"],
        "top_p": ["TOP_P_EDITOR"],
        "max_tokens": ["MAX_TOKENS_EDITOR"],
        "enable_thinking": ["ENABLE_THINKING_EDITOR"],
    },
    "copilot": {
        "api_key": ["NVIDIA_API_KEY_COPILOT"],
        "base_url": ["BASE_URL_COPILOT"],
        "model": ["MODEL_COPILOT"],
        "temperature": ["TEMPERATURE_COPILOT"],
        "top_p": ["TOP_P_COPILOT"],
        "max_tokens": ["MAX_TOKENS_COPILOT"],
        "enable_thinking": ["ENABLE_THINKING_COPILOT"],
    },
}


def _format_env_val(val: Any) -> str:
    """Format value for .env file entry."""
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bool):
        return "1" if val else "0"
    str_val = str(val or "").strip()
    escaped = str_val.replace('"', '\\"')
    return f'"{escaped}"'


def update_env_file(key_values: Mapping[str, Any], env_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Updates the .env file with given key-value pairs while preserving comments and order.
    Also updates os.environ and reloads dotenv.
    Returns the dictionary of updated keys and formatted values.
    """
    target_path = env_path or ENV_PATH
    
    if not target_path.exists():
        # Create empty .env if not exists
        target_path.write_text("", encoding="utf-8")

    content = target_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    updated_keys = set()
    new_lines = []

    # Map of clean keys to update
    updates = {k.strip(): v for k, v in key_values.items() if k.strip()}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        match = re.match(r"^([A-Za-z0-9_]+)\s*=", line)
        if match:
            k = match.group(1)
            if k in updates:
                val_formatted = _format_env_val(updates[k])
                new_lines.append(f"{k}={val_formatted}")
                updated_keys.add(k)
                continue

        new_lines.append(line)

    # Append any keys that were not previously present in .env
    for k, v in updates.items():
        if k not in updated_keys:
            val_formatted = _format_env_val(v)
            new_lines.append(f"{k}={val_formatted}")
            updated_keys.add(k)

    # Ensure trailing newline
    new_content = "\n".join(new_lines).strip() + "\n"
    target_path.write_text(new_content, encoding="utf-8")

    # Hot update os.environ and reload dotenv
    for k, v in updates.items():
        os.environ[k] = str(v)

    load_dotenv(str(target_path), override=True)

    return {k: str(v) for k, v in updates.items()}


def sync_agent_settings_to_env(agent_name: str, config: Mapping[str, Any], env_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Translates an agent's configuration dictionary into .env key-value pairs and writes to .env.
    """
    agent_key = agent_name.lower().strip()
    key_mapping = AGENT_ENV_KEY_MAP.get(agent_key)
    if not key_mapping:
        # Generic uppercase fallback if custom agent
        upper = agent_key.upper()
        key_mapping = {
            "api_key": [f"NVIDIA_API_KEY_{upper}"],
            "base_url": [f"BASE_URL_{upper}"],
            "model": [f"MODEL_{upper}"],
            "temperature": [f"TEMPERATURE_{upper}"],
            "top_p": [f"TOP_P_{upper}"],
            "max_tokens": [f"MAX_TOKENS_{upper}"],
            "enable_thinking": [f"ENABLE_THINKING_{upper}"],
        }

    env_updates: Dict[str, Any] = {}
    for field, env_var_names in key_mapping.items():
        if field in config and config[field] is not None:
            val = config[field]
            for env_var in env_var_names:
                env_updates[env_var] = val

    if env_updates:
        return update_env_file(env_updates, env_path=env_path)
    return {}
