# -*- coding: utf-8 -*-
"""
Challenger M2 Adversarial Empirical Verification Suite
File: tests/unit/test_challenger_m2_adversarial.py

Adversarially stress-tests Milestone 2:
1. TopologyGate (10-volume valid graph pass, 2-node / 3-node / 10-node cycles fail 100%, thread pathway discontinuity)
2. ForeshadowingGate (decoupled reachability pass, temporal reversal fail, orphan payoffs & dangling plants fail)
3. TwistGate (strict 9-dimension event validation, empty strings, non-lists, missing events)
4. CharacterGate (terminal spoilers DEAD/KILLED/BETRAYED/etc. & destiny keys destined_death/future_fate/etc.)
5. LocalRepairCoordinator (4-tier diagnosis & execution, Level 3 rollback on cycle, STORY_CANON_LOCKED security guard)
"""

import copy
import pytest
from typing import Dict, Any, List, Tuple

from backend.geometry.models import (
    GeometryGraph,
    GeometryNode,
    GeometryEdge,
    GeometryParams,
    GeometryComplexity,
    NodeHierarchy,
    EdgeType,
    CAUSAL_EDGE_TYPES,
    NON_CAUSAL_EDGE_TYPES,
    StructuralRole,
    NodeType,
    ForeshadowingDemand,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    NodeStoryContract,
    MasterGraphEdgeContract,
)
from backend.geometry.generator import GeometryGenerator
from backend.generation.director.completion_gates import (
    TopologyGate,
    ForeshadowingGate,
    TwistGate,
    WorldviewGate,
    CharacterGate,
    StoryCompletionGate,
)
from backend.generation.director.master_graph_service import MasterGraphService
from backend.generation.director.impact_analyzer import (
    ImpactAnalyzer,
    LocalRepairCoordinator,
    RepairTier,
    RepairRequest,
)
from backend.geometry.repair import (
    GeometryRepairCondition,
    RepairOperation,
    RepairProposal,
)


@pytest.fixture(scope="module")
def base_10vol_graph() -> GeometryGraph:
    """Generate a deterministic 10-volume 24-thread Master Graph."""
    params = GeometryParams(
        target_chapters=300,
        volume_count=10,
        chapters_per_volume=30,
        complexity=GeometryComplexity.STANDARD,
        main_thread_count=6,
        subplot_count=18,
        character_arc_count=6,
        relationship_arc_count=4,
        thematic_thread_count=4,
        seed_for_rng="challenger_m2_seed_42",
    )
    generator = GeometryGenerator(params)
    return generator.generate()


# =============================================================================
# 1. TopologyGate Adversarial Tests
# =============================================================================

class TestTopologyGateAdversarial:
    """Empirical adversarial stress-testing of TopologyGate."""

    def test_generated_10vol_graph_with_endpoints_passes(self, base_10vol_graph):
        """Verify standard 10-volume graph with in-degree 0 start and out-degree 0 end nodes PASSES TopologyGate."""
        res = TopologyGate.evaluate(base_10vol_graph)
        assert res.passed is True, f"TopologyGate failed on standard graph: {res.defects}"
        assert res.structural_ok is True
        assert res.quantitative_ok is True
        assert res.referential_ok is True
        assert res.metrics["start_nodes_count"] > 0, "Graph must have in-degree 0 start nodes"
        assert res.metrics["end_nodes_count"] > 0, "Graph must have out-degree 0 end nodes"
        assert res.metrics["cycle_errors_count"] == 0
        assert res.metrics["verified_24_threads_count"] == 24

    def test_adversarial_2_node_cycle_fails_100_percent(self, base_10vol_graph):
        """Inject a 2-node causal cycle (A -> B -> A) and verify TopologyGate fails 100% of the time."""
        graph = copy.deepcopy(base_10vol_graph)
        causal_edges = graph.get_causal_edges()
        assert len(causal_edges) > 0
        target_edge = causal_edges[0]
        u, v = target_edge.source, target_edge.target

        # Inject reverse causal edge B -> A
        graph.add_edge(GeometryEdge(
            edge_id="ADVERSARIAL_CYCLE_2NODE",
            source=v,
            target=u,
            edge_type=EdgeType.CAUSES,
            distance=1,
        ))

        res = TopologyGate.evaluate(graph)
        assert res.passed is False, "TopologyGate must fail on 2-node causal cycle"
        assert res.structural_ok is False
        assert any("環" in d or "Cycle" in d or "cycle" in d for d in res.defects)

    def test_adversarial_3_node_cycle_fails_100_percent(self, base_10vol_graph):
        """Inject a 3-node causal cycle (A -> B -> C -> A) and verify TopologyGate fails 100% of the time."""
        graph = copy.deepcopy(base_10vol_graph)
        t_nodes = graph.threads["TM01"].node_sequence
        assert len(t_nodes) >= 3
        a, b, c = t_nodes[0], t_nodes[1], t_nodes[2]

        graph.add_edge(GeometryEdge(
            edge_id="ADVERSARIAL_CYCLE_3NODE_BACK",
            source=c,
            target=a,
            edge_type=EdgeType.ENABLES,
            distance=1,
        ))

        res = TopologyGate.evaluate(graph)
        assert res.passed is False, "TopologyGate must fail on 3-node causal cycle"
        assert res.structural_ok is False
        assert any("環" in d or "Cycle" in d or "cycle" in d for d in res.defects)

    def test_adversarial_10_node_cycle_fails_100_percent(self, base_10vol_graph):
        """Inject a 10-node causal cycle (N0 -> N1 -> ... -> N9 -> N0) and verify TopologyGate fails 100% of the time."""
        graph = copy.deepcopy(base_10vol_graph)
        t_nodes = graph.threads["TM01"].node_sequence
        assert len(t_nodes) >= 10, "Thread TM01 must have at least 10 nodes"
        first_node = t_nodes[0]
        tenth_node = t_nodes[9]

        graph.add_edge(GeometryEdge(
            edge_id="ADVERSARIAL_CYCLE_10NODE_BACK",
            source=tenth_node,
            target=first_node,
            edge_type=EdgeType.ESCALATES,
            distance=9,
        ))

        res = TopologyGate.evaluate(graph)
        assert res.passed is False, "TopologyGate must fail on 10-node causal cycle"
        assert res.structural_ok is False
        assert any("環" in d or "Cycle" in d or "cycle" in d for d in res.defects)

    def test_adversarial_non_causal_cycle_does_not_fail_topology_gate(self, base_10vol_graph):
        """Non-causal edges (ECHOES, PARALLELS) can form thematic cycles without breaking causal DAG."""
        graph = copy.deepcopy(base_10vol_graph)
        t_nodes = graph.threads["TM01"].node_sequence
        u, v = t_nodes[0], t_nodes[1]

        graph.add_edge(GeometryEdge(
            edge_id="THEMATIC_ECHO_EDGE",
            source=v,
            target=u,
            edge_type=EdgeType.ECHOES,
            distance=1,
        ))

        res = TopologyGate.evaluate(graph)
        assert res.passed is True, "TopologyGate must NOT fail on non-causal thematic edge cycles"

    def test_break_thread_pathway_detected_as_discontinuity(self, base_10vol_graph):
        """Break a thread pathway and verify TopologyGate detects narrative thread discontinuity."""
        graph = copy.deepcopy(base_10vol_graph)
        isolated_nid = "DISCONNECTED_ISLAND_NODE"
        graph.add_node(GeometryNode(
            node_id=isolated_nid,
            hierarchy=NodeHierarchy(1, 1, 1),
            chapter_window=(1, 1),
            primary_thread="TS05",
            thread_memberships=["TS05"],
            structural_role=StructuralRole.DEVELOP,
            node_type=NodeType.DEVELOPMENT,
        ))
        thread = graph.threads["TS05"]
        original_seq = list(thread.node_sequence)
        thread.node_sequence = [original_seq[0], isolated_nid, original_seq[1]]

        res = TopologyGate.evaluate(graph)
        assert res.passed is False, "TopologyGate must fail when thread pathway is broken"
        assert any("TS05" in d and ("無法到達" in d or "中斷" in d) for d in res.defects)


# =============================================================================
# 2. ForeshadowingGate Adversarial Tests
# =============================================================================

class TestForeshadowingGateAdversarial:
    """Empirical adversarial stress-testing of ForeshadowingGate."""

    def test_decoupled_reachability_across_threads_passes(self, base_10vol_graph):
        """
        Clue plant in Volume 1 branch TS01 and payoff in Volume 3 main thread TM01
        with NO causal DAG connection between them must PASS ForeshadowingGate.
        """
        graph = copy.deepcopy(base_10vol_graph)

        # Clear existing foreshadowing tasks
        for n in graph.nodes.values():
            if n.story_contract:
                n.story_contract.foreshadowing_tasks = []

        # Plant node from branch TS01 configured in Volume 1
        plant_nid = graph.threads["TS01"].node_sequence[0]
        plant_node = graph.get_node(plant_nid)
        plant_node.hierarchy.volume_index = 1
        plant_node.chapter_window = (15, 15)

        # Payoff node from main thread TM01 in Volume 3
        tm01_vol3_nodes = [
            graph.get_node(nid) for nid in graph.threads["TM01"].node_sequence
            if graph.get_node(nid).hierarchy.volume_index == 3
        ]
        assert len(tm01_vol3_nodes) > 0
        payoff_node = tm01_vol3_nodes[0]
        payoff_node.chapter_window = (75, 75)

        # Verify NO causal DAG path from plant_node to payoff_node
        adj = {nid: set() for nid in graph.nodes}
        for e in graph.get_causal_edges():
            adj[e.source].add(e.target)
        assert TopologyGate._is_reachable(adj, plant_node.node_id, payoff_node.node_id) is False, \
            "Precondition: TS01 vol 1 node and TM01 vol 3 node must NOT be causally connected"

        # Plant clue in TS01 vol 1
        plant_contract = plant_node.ensure_story_contract()
        plant_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_CROSS_DECOUPLED_001",
            "role": "PLANT",
            "summary": "支線 TS01 卷一埋下失落徽章",
        })

        # Payoff clue in TM01 vol 3
        payoff_contract = payoff_node.ensure_story_contract()
        payoff_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_CROSS_DECOUPLED_001",
            "role": "PAYOFF",
            "summary": "主線 TM01 卷三揭曉徽章真身",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is True, f"ForeshadowingGate should pass decoupled reachability: {res.defects}"
        assert res.metrics["closed_clues"] == 1
        assert res.metrics["temporal_violations"] == 0

    def test_temporal_reversal_chapter_based_fails(self, base_10vol_graph):
        """Create a payoff in Chapter 5 and plant in Chapter 10, verify ForeshadowingGate FAILS with temporal violation."""
        graph = copy.deepcopy(base_10vol_graph)

        n1 = list(graph.nodes.values())[0]
        n2 = list(graph.nodes.values())[1]

        n1.chapter_window = (5, 5)
        n2.chapter_window = (10, 10)

        c1 = n1.ensure_story_contract()
        c2 = n2.ensure_story_contract()

        c1.foreshadowing_tasks = [{
            "clue_id": "FSH_TIME_TRAVEL_PARADOX",
            "role": "PAYOFF",
            "summary": "第五章提前揭秘",
        }]

        c2.foreshadowing_tasks = [{
            "clue_id": "FSH_TIME_TRAVEL_PARADOX",
            "role": "PLANT",
            "summary": "第十章才埋設伏筆",
        }]

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False, "ForeshadowingGate must fail when payoff precedes plant"
        assert res.structural_ok is False
        assert any("時序倒置" in d for d in res.defects)

    def test_temporal_reversal_volume_based_fails(self, base_10vol_graph):
        """Create a payoff in Volume 1 and plant in Volume 5 (without chapter mappings), verify ForeshadowingGate FAILS."""
        graph = copy.deepcopy(base_10vol_graph)

        v1_nodes = [n for n in graph.nodes.values() if n.hierarchy.volume_index == 1]
        v5_nodes = [n for n in graph.nodes.values() if n.hierarchy.volume_index == 5]

        payoff_node = v1_nodes[0]
        plant_node = v5_nodes[0]

        # Ensure chapter window does not override volume
        payoff_node.chapter_window = (0, 0)
        plant_node.chapter_window = (0, 0)

        cp = payoff_node.ensure_story_contract()
        cp.chapter_mappings = []
        cp.foreshadowing_tasks = [{
            "clue_id": "FSH_VOL_PARADOX",
            "role": "PAYOFF",
            "summary": "卷一提前揭示真相",
        }]

        cpl = plant_node.ensure_story_contract()
        cpl.chapter_mappings = []
        cpl.foreshadowing_tasks = [{
            "clue_id": "FSH_VOL_PARADOX",
            "role": "PLANT",
            "summary": "卷五才埋設種子",
        }]

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert any("時序倒置" in d for d in res.defects)

    def test_three_stage_turn_temporal_violation_fails(self, base_10vol_graph):
        """Plant at chapter 2, Turn at chapter 10, Payoff at chapter 6 -> Turn is after Payoff, verify FAILS."""
        graph = copy.deepcopy(base_10vol_graph)
        nodes = list(graph.nodes.values())[:3]

        n_plant, n_turn, n_payoff = nodes[0], nodes[1], nodes[2]

        n_plant.chapter_window = (2, 2)
        n_turn.chapter_window = (10, 10)
        n_payoff.chapter_window = (6, 6)

        c_plant = n_plant.ensure_story_contract()
        c_plant.foreshadowing_tasks = [{"clue_id": "FSH_3STAGE", "role": "PLANT"}]

        c_turn = n_turn.ensure_story_contract()
        c_turn.foreshadowing_tasks = [{"clue_id": "FSH_3STAGE", "role": "TURN"}]

        c_payoff = n_payoff.ensure_story_contract()
        c_payoff.foreshadowing_tasks = [{"clue_id": "FSH_3STAGE", "role": "PAYOFF"}]

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert any("三段式轉折時序違規" in d for d in res.defects)

    def test_orphan_payoff_fails_gate(self, base_10vol_graph):
        """Payoff without Plant must fail ForeshadowingGate."""
        graph = copy.deepcopy(base_10vol_graph)
        n = list(graph.nodes.values())[0]
        c = n.ensure_story_contract()
        c.foreshadowing_tasks = [{
            "clue_id": "FSH_ORPHAN_ONLY",
            "role": "PAYOFF",
            "summary": "懸空回收無埋設",
        }]

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert res.referential_ok is False
        assert any("孤立回收" in d for d in res.defects)

    def test_dangling_plant_fails_gate(self, base_10vol_graph):
        """Plant without Payoff must fail ForeshadowingGate."""
        graph = copy.deepcopy(base_10vol_graph)
        n = list(graph.nodes.values())[0]
        c = n.ensure_story_contract()
        c.foreshadowing_tasks = [{
            "clue_id": "FSH_DANGLING_ONLY",
            "role": "PLANT",
            "summary": "懸空埋設無回收",
        }]

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert res.quantitative_ok is False
        assert any("未閉環" in d for d in res.defects)


# =============================================================================
# 3. TwistGate Adversarial Tests
# =============================================================================

class TestTwistGateAdversarial:
    """Empirical adversarial stress-testing of TwistGate 9-dimension integrity."""

    @pytest.fixture
    def core_node_graph(self, base_10vol_graph) -> Tuple[GeometryGraph, GeometryNode]:
        """Prepare graph where all core nodes have valid 9-dimension events."""
        graph = copy.deepcopy(base_10vol_graph)
        for idx, node in enumerate(graph.nodes.values()):
            if TwistGate.is_core_node(node):
                c = node.ensure_story_contract()
                c.story_events = [
                    StoryEventContract(
                        event_id=f"EV_VALID_{idx}",
                        node_id=node.node_id,
                        event_summary="標準完整九維事件摘要",
                        participant_entities=[{"char_id": "C01", "role": "LEAD"}],
                        action_motives=[{"char_id": "C01", "motive": "揭開真相"}],
                        causal_preconditions=["EV_PREV_01"],
                        core_conflict="要塞圍困戰正面突破",
                        direct_outcome="突圍成功並取得信物",
                        state_mutations=[{"char_id": "C01", "type": "RESOLVE_BOOST"}],
                        downstream_impact=["引發大軍全域搜捕"],
                        clue_bindings=["FSH_001"],
                    )
                ]
        core_node = [n for n in graph.nodes.values() if TwistGate.is_core_node(n)][0]
        return graph, core_node

    def test_valid_core_nodes_pass_twist_gate(self, core_node_graph):
        """Baseline check: 100% complete core nodes pass TwistGate."""
        graph, _ = core_node_graph
        res = TwistGate.evaluate(graph, strict=True)
        assert res.passed is True, f"TwistGate should pass on complete core nodes: {res.defects}"

    @pytest.mark.parametrize("dim_field, invalid_val", [
        ("event_summary", ""),
        ("event_summary", "   "),
        ("participant_entities", []),
        ("participant_entities", "not_a_list"),
        ("action_motives", []),
        ("action_motives", {"not": "a_list"}),
        ("causal_preconditions", "not_a_list"),
        ("core_conflict", ""),
        ("core_conflict", "   "),
        ("direct_outcome", ""),
        ("direct_outcome", "   "),
        ("state_mutations", []),
        ("state_mutations", "not_a_list"),
        ("downstream_impact", []),
        ("downstream_impact", 12345),
        ("clue_bindings", []),
        ("clue_bindings", None),
    ])
    def test_omitting_or_corrupting_any_dimension_fails_twist_gate(self, core_node_graph, dim_field, invalid_val):
        """Adversarially corrupt each of the 9 dimensions individually on a core node; verify TwistGate FAILS 100%."""
        graph, core_node = copy.deepcopy(core_node_graph)
        event = core_node.story_contract.story_events[0]
        setattr(event, dim_field, invalid_val)

        res = TwistGate.evaluate(graph, strict=True)
        assert res.passed is False, f"TwistGate must FAIL when {dim_field}={repr(invalid_val)}"
        assert any(dim_field in d for d in res.defects), f"Defect message must mention {dim_field}: {res.defects}"

    def test_core_node_without_events_fails_twist_gate(self, core_node_graph):
        """Core node with empty story_events list fails TwistGate."""
        graph, core_node = copy.deepcopy(core_node_graph)
        core_node.story_contract.story_events = []

        res = TwistGate.evaluate(graph, strict=True)
        assert res.passed is False
        assert any("story_events 為空" in d for d in res.defects)


# =============================================================================
# 4. CharacterGate Adversarial Tests
# =============================================================================

class TestCharacterGateAdversarial:
    """Empirical adversarial stress-testing of CharacterGate anti-spoiler guards."""

    @pytest.fixture
    def clean_character_graph(self, base_10vol_graph) -> GeometryGraph:
        """Graph with 70 clean de-destined character slots."""
        graph = copy.deepcopy(base_10vol_graph)
        for idx, node in enumerate(graph.nodes.values()):
            c = node.ensure_story_contract()
            c.character_slots = [{
                "character_id": f"CHAR_{idx % 75:03d}",
                "role_in_node": "INSPECT",
                "initial_status": "ACTIVE",
            }]
        return graph

    def test_clean_character_graph_passes(self, clean_character_graph):
        """Clean objective profiles PASS CharacterGate."""
        res = CharacterGate.evaluate(clean_character_graph, min_roster_count=70)
        assert res.passed is True, f"Clean character graph should pass: {res.defects}"
        assert res.metrics["spoiler_violations_count"] == 0

    @pytest.mark.parametrize("spoiler_status", [
        "DEAD", "KILLED", "DECEASED", "BETRAYED", "FALLEN", "CORRUPTED", "SLAIN"
    ])
    def test_terminal_status_spoilers_fail_character_gate(self, clean_character_graph, spoiler_status):
        """Inject terminal spoilers into initial_status; verify CharacterGate FAILS 100%."""
        graph = copy.deepcopy(clean_character_graph)
        first_node = list(graph.nodes.values())[0]
        first_node.story_contract.character_slots[0]["initial_status"] = spoiler_status

        res = CharacterGate.evaluate(graph, min_roster_count=70)
        assert res.passed is False, f"CharacterGate must fail on terminal status {spoiler_status}"
        assert res.structural_ok is False
        assert any(spoiler_status in d and "終局劇透" in d for d in res.defects)

    @pytest.mark.parametrize("spoiler_key", [
        "destined_death", "will_betray", "future_fate", "spoiler_death_chapter", "destiny_ending"
    ])
    def test_destiny_keys_fail_character_gate(self, clean_character_graph, spoiler_key):
        """Inject prophetic destiny keys into character slot; verify CharacterGate FAILS 100%."""
        graph = copy.deepcopy(clean_character_graph)
        first_node = list(graph.nodes.values())[0]
        first_node.story_contract.character_slots[0][spoiler_key] = "Chapter 42 betrayal"

        res = CharacterGate.evaluate(graph, min_roster_count=70)
        assert res.passed is False, f"CharacterGate must fail on destiny key {spoiler_key}"
        assert res.structural_ok is False
        assert any(spoiler_key in d and "命運預言欄位" in d for d in res.defects)


# =============================================================================
# 5. LocalRepairCoordinator Adversarial Tests
# =============================================================================

class TestLocalRepairCoordinatorAdversarial:
    """Empirical adversarial stress-testing of 4-tier LocalRepairCoordinator."""

    def test_level_1_prompt_retry_diagnosis_and_execution(self, base_10vol_graph):
        """Diagnose and coordinate Level 1 (agent prompt retry) with 0 graph alterations."""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        init_rev = graph.graph_revision

        req = RepairRequest(
            agent_name="story_architect",
            defects=["Invalid markdown schema: missing closing json tag"],
            remediation_hint="Format as strict JSON object",
        )

        tier = coordinator.diagnose_repair_tier(req, graph)
        assert tier == RepairTier.LEVEL_1_AGENT_PROMPT

        plan = coordinator.create_repair_plan(graph, req)
        assert plan.tier == RepairTier.LEVEL_1_AGENT_PROMPT
        assert plan.action == "PROMPT_RETRY"

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is True
        assert result.tier == RepairTier.LEVEL_1_AGENT_PROMPT
        assert len(result.affected_nodes) == 0
        assert graph.graph_revision == init_rev
        assert "Format as strict JSON object" in result.directive["agent_prompt"]

    def test_level_2_node_slot_diagnosis_and_execution(self, base_10vol_graph):
        """Diagnose and coordinate Level 2 (node slot fix): update target slot without touching other nodes or revision."""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        target_nid = list(graph.nodes.keys())[0]
        init_rev = graph.graph_revision

        new_slot_data = {
            "faction_ids": ["F_EMPIRE", "F_REBELS"],
            "location_id": "LOC_BORDER_FORT",
            "conflict_cause": "邊境走私緝捕",
        }
        req = RepairRequest(
            node_id=target_nid,
            slot_name="worldview_slot",
            slot_data=new_slot_data,
        )

        tier = coordinator.diagnose_repair_tier(req, graph)
        assert tier == RepairTier.LEVEL_2_NODE_SLOT

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is True
        assert result.tier == RepairTier.LEVEL_2_NODE_SLOT
        assert result.affected_nodes == {target_nid}
        assert graph.graph_revision == init_rev
        assert graph.get_story_contract(target_nid).worldview_slot == new_slot_data

    def test_level_3_dynamic_subgraph_diagnosis_and_execution(self, base_10vol_graph):
        """Diagnose and coordinate Level 3 (dynamic subgraph): causal fields trigger downstream closure and bump revision."""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        target_nid = list(graph.nodes.keys())[0]
        init_rev = graph.graph_revision

        req = RepairRequest(
            node_id=target_nid,
            changed_fields=["state_mutations", "core_conflict"],
        )

        tier = coordinator.diagnose_repair_tier(req, graph)
        assert tier == RepairTier.LEVEL_3_IMPACT_SUBGRAPH

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is True
        assert result.tier == RepairTier.LEVEL_3_IMPACT_SUBGRAPH
        assert target_nid in result.affected_nodes
        assert result.new_revision == init_rev + 1
        assert graph.graph_revision == init_rev + 1

    def test_level_3_subgraph_rollback_on_causal_cycle(self, base_10vol_graph):
        """If a Level 3 repair induces a causal cycle, it must atomically roll back and report failure."""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        u, v = list(graph.nodes.keys())[0], list(graph.nodes.keys())[1]

        # Add reverse edge creating a cycle before validating
        graph.add_edge(GeometryEdge(
            edge_id="EDGE_TEMP_CYCLE",
            source=v,
            target=u,
            edge_type=EdgeType.CAUSES,
            distance=1,
        ))

        req = RepairRequest(
            node_id=u,
            changed_fields=["state_mutations"],
        )

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is False
        assert result.rolled_back is True
        assert "環狀違規" in result.message or "cycle" in result.message.lower()

    def test_level_4_structural_diagnosis_and_execution(self, base_10vol_graph):
        """Diagnose and coordinate Level 4 (structural repair): executes GeometryRepairEngine on density overload."""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        target_nid = list(graph.nodes.keys())[0]

        req = RepairRequest(
            node_id=target_nid,
            tier=RepairTier.LEVEL_4_STRUCTURAL,
            structural_proposal=RepairProposal(
                operation=RepairOperation.SPLIT,
                target_nodes=[target_nid],
                reason="密度過載",
                detail={"turning_points": 3},
            ),
            structural_condition=GeometryRepairCondition.DENSITY_OVERLOAD,
            gatekeeper_context={"turning_points_count": 3},
            metadata={"allow_canon_modification": True},
        )

        tier = coordinator.diagnose_repair_tier(req, graph)
        assert tier == RepairTier.LEVEL_4_STRUCTURAL

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is True
        assert result.tier == RepairTier.LEVEL_4_STRUCTURAL
        assert len(result.directive.get("new_nodes", [])) > 0

    def test_level_4_story_canon_locked_security_guard_rejects(self, base_10vol_graph):
        """
        STORY_CANON_LOCKED security guard:
        Attempt Level 4 structural repair on canon-locked node with allow_canon_modification=False;
        verify it is STRICTLY REJECTED without modifying the graph.
        """
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(base_10vol_graph)
        target_nid = list(graph.nodes.keys())[0]

        # Lock story canon on target node contract
        c = graph.get_story_contract(target_nid)
        c.planning_status = PlanningStatus.STORY_CANON_LOCKED

        # Request Level 4 repair with allow_canon_modification=False
        req = RepairRequest(
            node_id=target_nid,
            tier=RepairTier.LEVEL_4_STRUCTURAL,
            structural_proposal=RepairProposal(
                operation=RepairOperation.SPLIT,
                target_nodes=[target_nid],
                reason="密度過載",
                detail={"turning_points": 3},
            ),
            structural_condition=GeometryRepairCondition.DENSITY_OVERLOAD,
            gatekeeper_context={"turning_points_count": 3},
            metadata={"allow_canon_modification": False},  # Guard active
        )

        result = coordinator.coordinate_repair(graph, req)
        assert result.success is False, "Structural repair on STORY_CANON_LOCKED must be rejected"
        assert "STORY_CANON_LOCKED" in result.message
        assert "未授權禁止靜默破壞已鎖定主幹" in result.message

        # Now test with explicit authorization: allow_canon_modification=True
        req.metadata["allow_canon_modification"] = True
        auth_result = coordinator.coordinate_repair(graph, req)
        assert auth_result.success is True, "Structural repair with allow_canon_modification=True must proceed"
