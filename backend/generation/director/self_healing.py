# -*- coding: utf-8 -*-
"""
Deterministic Self-Healing Fallback Engine.
Intervenes algorithmically when LLM generation loops repeatedly fail (attempts >= 3),
guaranteeing forward pipeline momentum without crashing or infinite hanging.
"""

from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.generation.modules.scale_architect import build_narrative_scale_spec
from backend.generation.modules.blueprint_planner import generate_planning_blueprint
from backend.generation.modules.geometry_materializer import materialize_formal_geometry


def heal_geometry_stalemate(novel_id: str) -> Dict[str, Any]:
    """
    Algorithmically repairs unpersisted or empty narrative geometry.
    Guarantees that geometry_nodes, edges, and threads are created and stored in SQLite.
    """
    res = materialize_formal_geometry(novel_id, overwrite=True)
    return {
        "healed": True,
        "action": "materialize_formal_geometry",
        "result": res,
    }


def heal_missing_volumes(novel_id: str, target_count: int = 8) -> List[Dict[str, Any]]:
    """
    Synthesizes and repairs missing volumes to meet the minimum threshold,
    preserving existing volumes and appending necessary sequential continuation volumes.
    """
    existing_vols = db.get_volumes(novel_id) or []
    current_count = len(existing_vols)

    if current_count >= target_count:
        return existing_vols

    novel = db.get_novel(novel_id) or {}
    novel_title = novel.get("title") or "未命名作品"

    appended = list(existing_vols)
    for i in range(current_count + 1, target_count + 1):
        vol_data = {
            "volume_index": i,
            "title": f"第 {i} 卷：風雲激盪篇",
            "summary": f"延續前卷衝突，主角陣營在第 {i} 階段面臨更高層級考驗與勢力碰撞。",
            "chapter_count": 40,
        }
        db.save_volume(novel_id, i, vol_data)
        appended.append(vol_data)

    return appended
