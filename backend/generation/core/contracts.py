# -*- coding: utf-8 -*-
"""
Typed Contracts & Schemas for the Modular Generation Subsystem.
Enforces strict structural validity across agents, topology, foreshadowing, and gates.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union


@dataclass
class ActSpec:
    act_id: str
    act_index: int
    title: str
    theme_goal: str
    tension_target: float  # 0.0 to 1.0
    expected_volume_range: List[int] = field(default_factory=list)
    key_turning_points: List[str] = field(default_factory=list)


@dataclass
class NarrativeScaleSpec:
    novel_id: str
    total_volumes: int
    chapters_per_volume: int
    total_chapters: int
    act_count: int
    acts: List[ActSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintNode:
    node_id: str
    act_id: str
    title: str
    milestone_type: str  # inciting_incident | complication | midpoint_turn | crisis | climax | resolution
    importance: str  # critical | major | minor
    tension_level: float = 0.5
    causal_prerequisites: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BlueprintEdge:
    source_id: str
    target_id: str
    edge_type: str  # prerequisite | escalation | revelation | counter_stroke | convergence
    description: str = ""


@dataclass
class BlueprintThread:
    thread_id: str
    thread_type: str  # main | faction | mystery | character_arc
    title: str
    milestone_node_ids: List[str] = field(default_factory=list)


@dataclass
class PlanningBlueprint:
    novel_id: str
    scale_spec: NarrativeScaleSpec
    nodes: Dict[str, BlueprintNode] = field(default_factory=dict)
    edges: List[BlueprintEdge] = field(default_factory=list)
    threads: Dict[str, BlueprintThread] = field(default_factory=dict)
    state: str = "planning_blueprint"  # planning_blueprint -> formal_geometry_graph

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "scale_spec": self.scale_spec.to_dict(),
            "nodes": {nid: asdict(n) for nid, n in self.nodes.items()},
            "edges": [asdict(e) for e in self.edges],
            "threads": {tid: asdict(t) for tid, t in self.threads.items()},
            "state": self.state,
        }


@dataclass
class ForeshadowingBinding:
    foreshadowing_id: str
    title: str
    category: str
    carrier_character_ids: List[str] = field(default_factory=list)
    faction_id: Optional[str] = None
    planned_plant_act_id: Optional[str] = None
    planned_payoff_act_id: Optional[str] = None
    planned_plant_volume: Optional[int] = None
    planned_payoff_volume: Optional[int] = None
    surface_clue: str = ""
    core_truth: str = ""
    attached_node_id: Optional[str] = None
    status: str = "planted"  # planted | resolved | abandoned

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GateResult:
    stage: str
    passed: bool
    structural_ok: bool
    quantitative_ok: bool
    referential_ok: bool
    substantive_ok: bool
    defects: List[str] = field(default_factory=list)
    remediation_hint: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DirectorArbitration:
    action: str  # CONTINUE | AUTO_REGENERATE | REDIRECT | INCREMENTAL_PATCH | TOOL_CALL | WAIT_USER | FINISH
    target: str
    sub_target: Dict[str, Any] = field(default_factory=dict)
    rationale: Dict[str, Any] = field(default_factory=dict)
    directive: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
