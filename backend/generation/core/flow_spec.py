# -*- coding: utf-8 -*-
"""
Topological-First Generation Flow Specifications.
Defines the authoritative stage order, dynamic act formulas, and stage progression rules.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any

# Authoritative Topo-First Generation Sequence
# Stage A: Worldview -> Stage B: Scale & Dynamic Acts -> Stage C: Planning Blueprint ->
# Stage D: Entity & Foreshadowing Binding -> Stage E: Volumes Outline ->
# Stage F: Formal Geometry Graph -> Stage G: Semantics (Macro, Char, Cross) ->
# Stage H: Volume Skeletons -> Stage I/J: Writer & Editor -> Stage K: Reconciliation
TOPO_STAGE_ORDER = [
    "worldview",
    "narrative_scale",
    "planning_blueprint",
    "characters",
    "foreshadowing",
    "volumes",
    "geometry",
    "macro_semantic",
    "character_semantic",
    "cross_relation",
    "volume_skeleton",
    "writer",
    "editor",
    "reconciliation",
]

# Backward-compatible stage aliases for frontend / legacy task requests
STAGE_ALIASES: Dict[str, str] = {
    "worldbuilding": "worldview",
    "scale": "narrative_scale",
    "blueprint": "planning_blueprint",
    "character": "characters",
    "characters": "characters",
    "character_bible": "characters",
    "foreshadowings": "foreshadowing",
    "seeds": "foreshadowing",
    "turns": "foreshadowing",
    "plot": "volumes",
    "volume": "volumes",
    "geom": "geometry",
    "story_geometry": "geometry",
    "macro": "macro_semantic",
    "char_sem": "character_semantic",
    "cross": "cross_relation",
    "skeleton": "volume_skeleton",
    "skeletons": "volume_skeleton",
    "macro_skeleton": "volume_skeleton",
    "write": "writer",
    "edit": "editor",
    "director": "evaluate",
    "review": "evaluate",
}


def normalize_stage_name(stage: Optional[str]) -> str:
    raw = (stage or "").strip()
    if not raw:
        return "worldview"
    return STAGE_ALIASES.get(raw, raw)


def compute_dynamic_acts(volume_count: int, target_chapters: Optional[int] = None) -> int:
    """
    Computes the dynamic number of narrative acts based on target volume scale,
    eradicating the rigid 3-act hardcode.
    """
    v = max(1, int(volume_count or 1))
    if v <= 2:
        return 5  # Classic 5-act dramatic arch
    elif v <= 5:
        return 8  # Expanded 8-act structure (2 acts per volume roughly)
    elif v <= 10:
        return 12  # Multi-volume spiral arcs
    elif v <= 16:
        return 16  # Grand epic multi-act
    else:
        # Ultra-long novel: ~1 act per volume plus bookend acts
        return min(32, v + 4)


def get_stage_prerequisites(stage: str) -> List[str]:
    """Returns the mandatory predecessor stages required before executing the given stage."""
    norm = normalize_stage_name(stage)
    prereq_map: Dict[str, List[str]] = {
        "worldview": [],
        "narrative_scale": ["worldview"],
        "planning_blueprint": ["worldview", "narrative_scale"],
        "characters": ["worldview", "planning_blueprint"],
        "foreshadowing": ["worldview", "planning_blueprint", "characters"],
        "volumes": ["worldview", "planning_blueprint", "characters", "foreshadowing"],
        "geometry": ["volumes"],
        "macro_semantic": ["geometry"],
        "character_semantic": ["geometry", "characters"],
        "cross_relation": ["geometry", "macro_semantic", "character_semantic"],
        "volume_skeleton": ["volumes", "geometry"],
        "writer": ["volume_skeleton"],
        "editor": ["writer"],
        "reconciliation": ["editor"],
    }
    return prereq_map.get(norm, [])
