# -*- coding: utf-8 -*-
"""Core specifications, contracts, and rigid gates for modular generation."""

from backend.generation.core.flow_spec import (
    TOPO_STAGE_ORDER,
    STAGE_ALIASES,
    normalize_stage_name,
    compute_dynamic_acts,
    get_stage_prerequisites,
)
from backend.generation.core.contracts import (
    ActSpec,
    NarrativeScaleSpec,
    BlueprintNode,
    BlueprintEdge,
    BlueprintThread,
    PlanningBlueprint,
    ForeshadowingBinding,
    GateResult,
    DirectorArbitration,
)
from backend.generation.core.gates import evaluate_stage_rigid_gate

__all__ = [
    "TOPO_STAGE_ORDER",
    "STAGE_ALIASES",
    "normalize_stage_name",
    "compute_dynamic_acts",
    "get_stage_prerequisites",
    "ActSpec",
    "NarrativeScaleSpec",
    "BlueprintNode",
    "BlueprintEdge",
    "BlueprintThread",
    "PlanningBlueprint",
    "ForeshadowingBinding",
    "GateResult",
    "DirectorArbitration",
    "evaluate_stage_rigid_gate",
]
