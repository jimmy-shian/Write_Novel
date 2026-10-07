# -*- coding: utf-8 -*-
"""
Planning Blueprint Generator.
Constructs macro causal milestones, narrative threads, and causal edges BEFORE volumes.
Persists the blueprint into the geometry repository so downstream stages always have a factual structural spine.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from backend import persistence as db
from backend.geometry.models import (
    GeometryGraph,
    GeometryNode,
    GeometryEdge,
    GeometryThread,
    GeometryParams,
    GeometryComplexity,
    StructuralRole,
    ThreadType,
    EdgeType,
    NodeHierarchy,
)
from backend.generation.core.contracts import PlanningBlueprint, BlueprintNode, BlueprintEdge, BlueprintThread
from backend.generation.modules.scale_architect import build_narrative_scale_spec


def generate_planning_blueprint(novel_id: str, target_volumes: Optional[int] = None) -> PlanningBlueprint:
    """
    Generates and physically persists the initial narrative Planning Blueprint.
    Creates macro milestone nodes, causal edges, and thematic threads for all acts.
    """
    scale_spec = build_narrative_scale_spec(novel_id, target_volumes)
    act_count = scale_spec.act_count
    total_volumes = scale_spec.total_volumes
    ch_per_vol = scale_spec.chapters_per_volume
    total_chapters = scale_spec.total_chapters

    # Construct Geometry Graph objects
    params = GeometryParams(
        target_chapters=total_chapters,
        volume_count=total_volumes,
        chapters_per_volume=ch_per_vol,
        complexity=GeometryComplexity.STANDARD if act_count <= 8 else GeometryComplexity.DENSE,
        main_thread_count=min(6, max(3, act_count // 3)),
        subplot_count=min(16, max(4, act_count)),
        character_arc_count=min(12, max(4, act_count // 2)),
        thematic_thread_count=4,
        seed_for_rng=f"blueprint_{novel_id}",
    )

    graph = GeometryGraph(params=params)

    # 1. Threads
    threads = {
        "thread_main_plot": GeometryThread(
            thread_id="thread_main_plot",
            thread_type=ThreadType.MAIN,
            node_sequence=[],
            structural_skeleton=[],
            metadata={"name": "主線因果推進線", "color": "#2563EB", "description": "全書核心危機與終極目標因果鏈"},
        ),
        "thread_faction_clash": GeometryThread(
            thread_id="thread_faction_clash",
            thread_type=ThreadType.SUBPLOT,
            node_sequence=[],
            structural_skeleton=[],
            metadata={"name": "陣營交鋒與權力爭奪線", "color": "#DC2626", "description": "各勢力博弈、消長與利益碰撞"},
        ),
        "thread_myth_mystery": GeometryThread(
            thread_id="thread_myth_mystery",
            thread_type=ThreadType.THEMATIC,
            node_sequence=[],
            structural_skeleton=[],
            metadata={"name": "世界法則與身世謎團線", "color": "#9333EA", "description": "深層伏筆埋設、神話揭曉與真相拼圖"},
        ),
        "thread_character_arc": GeometryThread(
            thread_id="thread_character_arc",
            thread_type=ThreadType.CHARACTER_ARC,
            node_sequence=[],
            structural_skeleton=[],
            metadata={"name": "主角成長與代價蛻變線", "color": "#059669", "description": "內心創傷、信念衝擊與人格轉向"},
        ),
    }
    graph.threads = threads

    # 2. Nodes: Generate 2~3 milestone nodes per act
    nodes_dict: Dict[str, GeometryNode] = {}
    blueprint_nodes: Dict[str, BlueprintNode] = {}
    blueprint_edges: List[BlueprintEdge] = []
    edges_list: List[GeometryEdge] = []

    prev_node_id: Optional[str] = None
    node_idx = 1
    edge_idx = 1

    for act in scale_spec.acts:
        act_id = act.act_id
        v_start = act.expected_volume_range[0] if act.expected_volume_range else 1
        v_end = act.expected_volume_range[-1] if act.expected_volume_range else v_start
        ch_start = max(1, (v_start - 1) * ch_per_vol + 1)
        ch_end = min(total_chapters, v_end * ch_per_vol)

        # Milestone 1: Act Inciting / Development
        n1_id = f"GEO-NODE-ACT{act.act_index:02d}-01"
        role_1 = StructuralRole.OPEN_THREAD if act.act_index == 1 else StructuralRole.DEVELOP
        n1 = GeometryNode(
            node_id=n1_id,
            structural_role=role_1,
            chapter_window=(ch_start, (ch_start + ch_end) // 2),
            primary_thread="thread_main_plot",
            hierarchy=NodeHierarchy(volume_index=v_start, arc_index=act.act_index, sequence_index=1),
            importance=0.8,
            metadata={"act_id": act_id, "theme_goal": act.theme_goal, "type": "blueprint_milestone"},
        )
        nodes_dict[n1_id] = n1
        threads["thread_main_plot"].node_sequence.append(n1_id)
        threads["thread_main_plot"].structural_skeleton.append(role_1)

        blueprint_nodes[n1_id] = BlueprintNode(
            node_id=n1_id,
            act_id=act_id,
            title=f"{act.title} - 起首事件",
            milestone_type="inciting_incident" if act.act_index == 1 else "complication",
            importance="major",
            tension_level=max(0.2, act.tension_target - 0.15),
        )

        # Milestone 2: Act Turning / Climax
        n2_id = f"GEO-NODE-ACT{act.act_index:02d}-02"
        role_2 = StructuralRole.CLOSE if act.act_index == act_count else StructuralRole.ESCALATE
        n2 = GeometryNode(
            node_id=n2_id,
            structural_role=role_2,
            chapter_window=((ch_start + ch_end) // 2 + 1, ch_end),
            primary_thread="thread_main_plot",
            hierarchy=NodeHierarchy(volume_index=v_end, arc_index=act.act_index, sequence_index=2),
            importance=1.0 if role_2 == StructuralRole.CLOSE else 0.85,
            metadata={"act_id": act_id, "theme_goal": act.theme_goal, "type": "blueprint_milestone"},
        )
        nodes_dict[n2_id] = n2
        threads["thread_main_plot"].node_sequence.append(n2_id)
        threads["thread_main_plot"].structural_skeleton.append(role_2)

        blueprint_nodes[n2_id] = BlueprintNode(
            node_id=n2_id,
            act_id=act_id,
            title=f"{act.title} - 高潮轉折",
            milestone_type="climax" if act.act_index == act_count else "midpoint_turn",
            importance="critical" if role_2 == StructuralRole.CLOSE else "major",
            tension_level=act.tension_target,
            causal_prerequisites=[n1_id],
        )

        # Edge within act: n1 -> n2
        e_inner = GeometryEdge(
            edge_id=f"GEO-EDGE-{edge_idx:03d}",
            source=n1_id,
            target=n2_id,
            edge_type=EdgeType.CAUSES,
            distance=max(1, (ch_start + ch_end) // 2 - ch_start),
            metadata={"description": f"{act.title} 內部因果推進"},
        )
        edge_idx += 1
        edges_list.append(e_inner)
        blueprint_edges.append(BlueprintEdge(
            source_id=n1_id,
            target_id=n2_id,
            edge_type="prerequisite",
            description=f"{act.title} 內部因果推進",
        ))

        # Edge from previous act climax to this act
        if prev_node_id:
            e_inter = GeometryEdge(
                edge_id=f"GEO-EDGE-{edge_idx:03d}",
                source=prev_node_id,
                target=n1_id,
                edge_type=EdgeType.ESCALATES,
                distance=max(1, ch_start - 1),
                metadata={"description": f"跨幕因果激化：第 {act.act_index - 1} 幕 -> 第 {act.act_index} 幕"},
            )
            edge_idx += 1
            edges_list.append(e_inter)
            blueprint_edges.append(BlueprintEdge(
                source_id=prev_node_id,
                target_id=n1_id,
                edge_type="escalation",
                description=f"跨幕因果激化：第 {act.act_index - 1} 幕 -> 第 {act.act_index} 幕",
            ))

        prev_node_id = n2_id

    # 3. Add long-distance foreshadowing edge from Act 1 to Penultimate/Final Act
    if len(scale_spec.acts) >= 3:
        first_node = f"GEO-NODE-ACT01-01"
        payoff_node = f"GEO-NODE-ACT{act_count:02d}-02"
        if first_node in nodes_dict and payoff_node in nodes_dict:
            e_long = GeometryEdge(
                edge_id=f"GEO-EDGE-{edge_idx:03d}",
                source=first_node,
                target=payoff_node,
                edge_type=EdgeType.PAYS_OFF,
                distance=total_chapters - 1,
                metadata={"description": "全書終極伏筆長程回收邊 (Motif A)"},
            )
            edges_list.append(e_long)
            blueprint_edges.append(BlueprintEdge(
                source_id=first_node,
                target_id=payoff_node,
                edge_type="revelation",
                description="全書終極伏筆長程回收邊",
            ))

    graph.nodes = nodes_dict
    graph.edges = edges_list

    blueprint = PlanningBlueprint(
        novel_id=novel_id,
        scale_spec=scale_spec,
        nodes=blueprint_nodes,
        edges=blueprint_edges,
        threads={tid: BlueprintThread(thread_id=tid, thread_type=t.thread_type.value, title=t.metadata.get("name", tid)) for tid, t in threads.items()},
        state="planning_blueprint",
    )
    # Planning data has its own store. It must never populate geometry_*;
    # formal geometry is materialized only after the volume outline gate.
    db.save_planning_blueprint(novel_id, blueprint)
    return blueprint
