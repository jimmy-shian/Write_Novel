# -*- coding: utf-8 -*-
"""Persistence for planning blueprints and explicit entity bindings."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from backend.persistence.connection import get_db_connection


def save_planning_blueprint(novel_id: str, blueprint: Any) -> None:
    payload = blueprint.to_dict() if hasattr(blueprint, "to_dict") else blueprint
    state = str(payload.get("state") or "planning_blueprint") if isinstance(payload, dict) else "planning_blueprint"
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO narrative_planning_blueprints (novel_id, blueprint_json, state, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (novel_id, json.dumps(payload, ensure_ascii=False), state),
        )


def get_planning_blueprint(novel_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT blueprint_json, state FROM narrative_planning_blueprints WHERE novel_id = ?",
        (novel_id,),
    ).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["blueprint_json"] if hasattr(row, "keys") else row[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        payload.setdefault("state", row["state"] if hasattr(row, "keys") else row[1])
    return payload if isinstance(payload, dict) else None


def save_entity_bindings(novel_id: str, bindings: Iterable[Any]) -> int:
    rows = []
    for binding in bindings:
        payload = binding.to_dict() if hasattr(binding, "to_dict") else binding
        if not isinstance(payload, dict):
            continue
        binding_id = str(payload.get("foreshadowing_id") or payload.get("binding_id") or "").strip()
        if binding_id:
            rows.append((novel_id, binding_id, json.dumps(payload, ensure_ascii=False)))
    conn = get_db_connection()
    # Unit-level callers may construct bindings before creating a novel row;
    # production pipeline rows always have the parent novel. Keep the pure
    # binder usable without violating the FK for those isolated calls.
    parent = conn.execute("SELECT 1 FROM novels WHERE id = ?", (novel_id,)).fetchone()
    if not parent:
        return 0
    with conn:
        conn.execute("DELETE FROM narrative_entity_bindings WHERE novel_id = ?", (novel_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO narrative_entity_bindings (novel_id, binding_id, binding_json, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )
    return len(rows)


def get_entity_bindings(novel_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT binding_json FROM narrative_entity_bindings WHERE novel_id = ? ORDER BY binding_id",
        (novel_id,),
    ).fetchall()
    result = []
    for row in rows:
        try:
            value = json.loads(row["binding_json"] if hasattr(row, "keys") else row[0])
            if isinstance(value, dict):
                result.append(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return result
