# -*- coding: utf-8 -*-
"""Modular generation engines and synthesis components."""

from backend.generation.modules.scale_architect import build_narrative_scale_spec
from backend.generation.modules.blueprint_planner import generate_planning_blueprint
from backend.generation.modules.entity_binder import bind_entities_and_foreshadowings
from backend.generation.modules.geometry_materializer import materialize_formal_geometry

__all__ = [
    "build_narrative_scale_spec",
    "generate_planning_blueprint",
    "bind_entities_and_foreshadowings",
    "materialize_formal_geometry",
]
