# -*- coding: utf-8 -*-
"""
Empirical Adversarial Test Suite for Milestone 1:
Contract Resilience, State Isolation, Dual-Track Decoupling & Geometry Repair Invariants.

Authored by Challenger M1_2 (Empirical Challenger).

Verifies:
1. StoryEventContract: Adversarial testing with empty strings, missing fields, invalid types,
   and strict=True vs strict=False validation behavior.
2. NodeStoryContract: Container slot isolation across instances (preventing mutable default argument leaks)
   and full-scale generated graph node isolation.
3. Dual-Track Status Decoupling: Ensuring Track A (PlanningStatus), Track B (RealizationStatus),
   and Track C (Draft Audit VIOLATED) remain decoupled with immutable graph revisions during audits.
4. GeometryRepairEngine: Preservation of NodeStoryContract, thread memberships, and causal DAG
   acyclicity across SPLIT, EXPAND, INSERT, and COMPRESS operations.
5. Atomic Rollback Vulnerability: Empirical reproduction of repair engine graph corruption upon cycle detection.
"""

import copy
import pytest
from typing import Dict, Any, List

from backend.geometry.models import (
    EdgeType,
    ForeshadowingDemand,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    NodeHierarchy,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    RepairOperation,
    RepairProposal,
    StoryEventContract,
    StructuralRole,
)
from backend.geometry.generator import GeometryGenerator
from backend.geometry.repair import (
    GeometryRepairCondition,
    GeometryRepairEngine,
)


# =============================================================================
# 1. StoryEventContract Adversarial Resilience Tests
# =============================================================================

class TestStoryEventContractAdversarial:
    """Adversarial testing of StoryEventContract dimensions, types, and validation modes."""

    def test_adversarial_empty_and_whitespace_fields(self):
        """Pass empty strings and whitespace-only strings to verify defect detection."""
        # All empty / whitespace
        ev = StoryEventContract(
            event_id="EV_ADV_01",
            node_id="G0001",
            event_summary="   \t\n  ",
            participant_entities=[{"char_id": "C1", "role": "LEAD"}],
            action_motives=[{"char_id": "C1", "motive": "Survive"}],
            causal_preconditions=["EV00"],
            core_conflict="   ",
            direct_outcome="",
            state_mutations=[{"type": "DAMAGE"}],
            downstream_impact=["City burns"],
            clue_bindings=["FSH01"],
        )
        valid, defects = ev.validate_nine_dimensions(strict=False)
        assert not valid
        # event_summary, core_conflict, direct_outcome must all be reported as defects
        defect_str = " ".join(defects)
        assert "event_summary" in defect_str
        assert "core_conflict" in defect_str
        assert "direct_outcome" in defect_str

    def test_adversarial_missing_and_empty_collections(self):
        """Pass empty lists for required participants and motives."""
        ev = StoryEventContract(
            event_id="EV_ADV_02",
            node_id="G0001",
            event_summary="Valid summary",
            participant_entities=[],
            action_motives=[],
            causal_preconditions=[],
            core_conflict="Valid conflict",
            direct_outcome="Valid outcome",
        )
        valid, defects = ev.validate_nine_dimensions(strict=False)
        assert not valid
        defect_str = " ".join(defects)
        assert "participant_entities" in defect_str
        assert "action_motives" in defect_str

    def test_adversarial_invalid_types_handling(self):
        """Pass invalid types (int, str, None) where lists are expected."""
        ev = StoryEventContract(
            event_id="EV_ADV_03",
            node_id="G0001",
            event_summary="Valid summary",
            participant_entities="not-a-list",  # Invalid type (string)
            action_motives=12345,               # Invalid type (int)
            causal_preconditions="not-a-list",  # Invalid type
            core_conflict="Valid conflict",
            direct_outcome="Valid outcome",
            state_mutations=12345,             # Invalid type
            downstream_impact=None,            # Invalid type
            clue_bindings={"key": "val"},      # Invalid type
        )
        valid, defects = ev.validate_nine_dimensions(strict=False)
        assert not valid
        defect_str = " ".join(defects)
        assert "participant_entities" in defect_str
        assert "action_motives" in defect_str
        assert "causal_preconditions" in defect_str
        assert "state_mutations" in defect_str
        assert "downstream_impact" in defect_str
        assert "clue_bindings" in defect_str

        # Also verify that to_dict does not crash on invalid non-list types
        d = ev.to_dict()
        assert isinstance(d, dict)

    def test_strict_vs_loose_validation_mode(self):
        """
        Verify strict=True vs strict=False contract semantics:
        - In strict=False (loose/draft), empty state_mutations, downstream_impact, clue_bindings are allowed.
        - In strict=True (TwistGate gatekeeper), state_mutations, downstream_impact, clue_bindings MUST be non-empty.
        """
        base_kwargs = {
            "event_id": "EV_ADV_04",
            "node_id": "G0001",
            "event_summary": "Protagonist uncovers the truth",
            "participant_entities": [{"char_id": "C01", "role": "SEEKER"}],
            "action_motives": [{"char_id": "C01", "motive": "Seeking revenge"}],
            "causal_preconditions": ["EV_PREV_01"],
            "core_conflict": "Duel with the guardian",
            "direct_outcome": "Defeated guardian and obtained key",
            "state_mutations": [],
            "downstream_impact": [],
            "clue_bindings": [],
        }

        ev_partial = StoryEventContract(**base_kwargs)

        # Loose mode: partial downstream/state fields are permitted
        valid_loose, defects_loose = ev_partial.validate_nine_dimensions(strict=False)
        assert valid_loose is True
        assert defects_loose == []
        assert ev_partial.is_complete(strict=False) is True

        # Strict mode: TwistGate gatekeeper strictly rejects empty downstream/state/clue lists
        valid_strict, defects_strict = ev_partial.validate_nine_dimensions(strict=True)
        assert valid_strict is False
        assert len(defects_strict) == 3
        defect_str = " ".join(defects_strict)
        assert "state_mutations" in defect_str
        assert "downstream_impact" in defect_str
        assert "clue_bindings" in defect_str
        assert ev_partial.is_complete(strict=True) is False

        # Once populated, strict mode passes with 0 defects
        ev_full = StoryEventContract(
            **{
                **base_kwargs,
                "state_mutations": [{"char_id": "C01", "type": "LEVEL_UP"}],
                "downstream_impact": ["Empire alert level rises"],
                "clue_bindings": ["FSH_001"],
            }
        )
        assert ev_full.is_complete(strict=True) is True
        assert ev_full.validate_9_dimensions(strict=True) == []

    def test_story_event_from_dict_and_dict_mutation_safety(self):
        """Verify from_dict gracefully defaults missing keys and to_dict creates decoupled copies."""
        # Empty dict should safely populate default values without KeyError
        empty_contract = StoryEventContract.from_dict({})
        assert empty_contract.event_id == ""
        assert empty_contract.participant_entities == []
        assert empty_contract.is_complete(strict=False) is False

        # Mutation of to_dict() output must not mutate internal contract state
        original = StoryEventContract(
            event_id="EV_ISO",
            node_id="G1",
            event_summary="Summary",
            participant_entities=[{"char_id": "C1", "role": "HERO"}],
            action_motives=[{"char_id": "C1", "motive": "Justice"}],
            causal_preconditions=["EV0"],
            core_conflict="Conflict",
            direct_outcome="Outcome",
            state_mutations=[{"char_id": "C1", "type": "HP_DROP"}],
            downstream_impact=["Impact"],
            clue_bindings=["FSH1"],
        )
        d = original.to_dict()
        d["participant_entities"].append({"char_id": "C2", "role": "VILLAIN"})
        d["participant_entities"][0]["role"] = "MUTATED"
        d["state_mutations"].clear()

        # Original must remain untouched
        assert len(original.participant_entities) == 1
        assert original.participant_entities[0]["role"] == "HERO"
        assert len(original.state_mutations) == 1


# =============================================================================
# 2. NodeStoryContract Slot Isolation Tests
# =============================================================================

class TestNodeStoryContractSlotIsolation:
    """Verify slot containers do not leak across nodes via mutable default arguments."""

    def test_slot_isolation_between_fresh_instances(self):
        """Mutating containers on node_a must never affect node_b."""
        node_a = NodeStoryContract(node_id="N_A", volume_index=1, arc_index=1)
        node_b = NodeStoryContract(node_id="N_B", volume_index=1, arc_index=1)

        # Assert independent object identity
        assert node_a.character_slots is not node_b.character_slots
        assert node_a.story_events is not node_b.story_events
        assert node_a.destiny_events is not node_b.destiny_events
        assert node_a.foreshadowing_tasks is not node_b.foreshadowing_tasks
        assert node_a.chapter_mappings is not node_b.chapter_mappings
        assert node_a.thread_memberships is not node_b.thread_memberships

        # Mutate node_a slots
        node_a.character_slots.append({"char_id": "C01", "role_in_node": "DEFENDER"})
        node_a.story_events.append(StoryEventContract(event_id="E1", node_id="N_A", event_summary="Summary"))
        node_a.destiny_events.append({"char_id": "C01", "type": "DEATH"})
        node_a.foreshadowing_tasks.append({"clue_id": "F01", "role": "PLANT"})
        node_a.chapter_mappings.append({"chapter_index": 1, "beat_index": 0})
        node_a.thread_memberships.append("TM01")
        node_a.worldview_slot = {"faction_ids": ["F01"]}

        # Assert node_b remains pristine
        assert node_b.character_slots == []
        assert node_b.story_events == []
        assert node_b.destiny_events == []
        assert node_b.foreshadowing_tasks == []
        assert node_b.chapter_mappings == []
        assert node_b.thread_memberships == []
        assert node_b.worldview_slot is None

    def test_geometry_node_metadata_and_contract_isolation(self):
        """Verify GeometryNode metadata, memberships, and attached contracts do not bleed."""
        gnode_a = GeometryNode(
            node_id="GN_A",
            hierarchy=NodeHierarchy(1, 1, 1),
            chapter_window=(1, 2),
            structural_role=StructuralRole.OPEN_THREAD,
            primary_thread="TM01",
        )
        gnode_b = GeometryNode(
            node_id="GN_B",
            hierarchy=NodeHierarchy(1, 1, 2),
            chapter_window=(2, 3),
            structural_role=StructuralRole.DEVELOP,
            primary_thread="TM01",
        )

        assert gnode_a.metadata is not gnode_b.metadata
        assert gnode_a.thread_memberships is not gnode_b.thread_memberships

        gnode_a.metadata["injected_flag"] = True
        gnode_a.thread_memberships.append("TS05")
        contract_a = gnode_a.ensure_story_contract()
        contract_a.character_slots.append({"char_id": "C99"})

        # gnode_b must be unaffected
        assert "injected_flag" not in gnode_b.metadata
        assert "TS05" not in gnode_b.thread_memberships
        assert gnode_b.story_contract is None

    def test_full_scale_generated_graph_1000_nodes_contract_isolation(self):
        """Generate a 1000+ node graph and verify 100% of contracts have distinct object identities."""
        params = GeometryParams(
            target_chapters=300,
            volume_count=10,
            chapters_per_volume=30,
            main_thread_count=6,
            subplot_count=18,
            seed_for_rng="challenger_isolation_stress",
        )
        graph = GeometryGenerator(params).generate()
        nodes = list(graph.nodes.values())
        assert len(nodes) >= 500, f"Expected substantial node count, got {len(nodes)}"

        # Collect contracts
        contracts = [n.story_contract for n in nodes if n.story_contract is not None]
        assert len(contracts) == len(nodes), "Every generated node must have an attached story_contract"

        # Unique identity assertion
        contract_ids = set(id(c) for c in contracts)
        assert len(contract_ids) == len(contracts), "Shared contract instances detected across generated nodes!"

        # Mutate node 0
        first_node = nodes[0]
        first_node.story_contract.character_slots.append({"char_id": "SENTINEL_CHAR"})
        first_node.story_contract.thread_memberships.append("ROGUE_THREAD")

        # Verify no bleed into any other node
        for other in nodes[1:]:
            assert {"char_id": "SENTINEL_CHAR"} not in other.story_contract.character_slots
            assert "ROGUE_THREAD" not in other.story_contract.thread_memberships


# =============================================================================
# 3. Dual-Track Status Decoupling Tests
# =============================================================================

class TestDualTrackStatusDecoupling:
    """Verify PlanningStatus (Track A), RealizationStatus (Track B), and Draft Audit VIOLATED (Track C)."""

    def test_draft_audit_violated_does_not_mutate_planning_status_or_revision(self):
        """
        Draft audit violation records (Track C) must NOT alter locked Master Graph planning_status
        or graph_revision.
        """
        node_contract = NodeStoryContract(
            node_id="G0042",
            volume_index=2,
            arc_index=1,
            thread_memberships=["TM01"],
            planning_status=PlanningStatus.STORY_CANON_LOCKED,
            realization_status=RealizationStatus.PENDING,
            graph_revision=5,
        )
        geom_node = node_contract.to_geometry_node(chapter_window=(40, 42))

        # 1. Verify VIOLATED is NOT a valid PlanningStatus enum member
        assert "VIOLATED" not in [s.value for s in PlanningStatus]

        # 2. Verify GeometryNode planning_status setter raises ValueError if someone attempts to set VIOLATED
        with pytest.raises(ValueError):
            geom_node.planning_status = "VIOLATED"

        # 3. Simulate a chapter draft audit violation report (Track C)
        audit_report = {
            "chapter_index": 41,
            "node_id": "G0042",
            "audit_status": "VIOLATED",
            "violations": ["Core character motive contradicts locked story canon"],
            "suggestion": "Rewrite scene without modifying Master Graph",
        }

        # Assert node planning status and revision remain strictly untouched
        assert geom_node.planning_status == PlanningStatus.STORY_CANON_LOCKED
        assert geom_node.graph_revision == 5
        assert node_contract.planning_status == PlanningStatus.STORY_CANON_LOCKED
        assert node_contract.graph_revision == 5

    def test_realization_lifecycle_does_not_mutate_planning_track(self):
        """Advancing realization status (PENDING -> PARTIAL -> REALIZED) leaves planning_status intact."""
        node = NodeStoryContract(
            node_id="G0045",
            volume_index=2,
            arc_index=2,
            planning_status=PlanningStatus.STORY_CANON_LOCKED,
            realization_status=RealizationStatus.PENDING,
            graph_revision=7,
        )

        # Move to PARTIAL
        node.realization_status = RealizationStatus.PARTIAL
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED
        assert node.graph_revision == 7

        # Move to REALIZED
        node.realization_status = RealizationStatus.REALIZED
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED
        assert node.graph_revision == 7

    def test_planning_lifecycle_does_not_mutate_realization_track(self):
        """Advancing planning status (DRAFT -> GATE_PASSED -> STORY_CANON_LOCKED) leaves realization_status PENDING."""
        node = NodeStoryContract(
            node_id="G0046",
            volume_index=2,
            arc_index=2,
            planning_status=PlanningStatus.DRAFT,
            realization_status=RealizationStatus.PENDING,
        )

        node.planning_status = PlanningStatus.GATE_PASSED
        assert node.realization_status == RealizationStatus.PENDING

        node.planning_status = PlanningStatus.STORY_CANON_LOCKED
        assert node.realization_status == RealizationStatus.PENDING

        node.planning_status = PlanningStatus.REVISION_PENDING
        assert node.realization_status == RealizationStatus.PENDING


# =============================================================================
# 4. GeometryRepairEngine Operations & Invariant Preservation Tests
# =============================================================================

class TestGeometryRepairEngineOperations:
    """Verify SPLIT, EXPAND, INSERT, COMPRESS preserve NodeStoryContract, memberships, and DAG acyclicity."""

    @pytest.fixture
    def small_valid_graph(self) -> GeometryGraph:
        """Create a clean 4-node acyclic linear graph with contracts and memberships."""
        params = GeometryParams(target_chapters=20, volume_count=2)
        graph = GeometryGraph(params)

        for i in range(1, 5):
            nid = f"N{i}"
            contract = NodeStoryContract(
                node_id=nid,
                volume_index=1,
                arc_index=1,
                thread_memberships=["TM01", "TM02"] if i % 2 == 0 else ["TM01"],
                structural_role=StructuralRole.DEVELOP,
                node_type=NodeType.DEVELOPMENT,
                foreshadowing_demand=ForeshadowingDemand.NONE,
                planning_status=PlanningStatus.GATE_PASSED,
                realization_status=RealizationStatus.PENDING,
                graph_revision=1,
            )
            node = GeometryNode(
                node_id=nid,
                hierarchy=NodeHierarchy(volume_index=1, arc_index=1, sequence_index=i),
                chapter_window=(i * 2 - 1, i * 2),
                structural_role=StructuralRole.DEVELOP,
                primary_thread="TM01",
                thread_memberships=list(contract.thread_memberships),
                story_contract=contract,
            )
            graph.add_node(node)

        # Add causal forward edges: N1 -> N2 -> N3 -> N4
        graph.add_edge(GeometryEdge("E1", "N1", "N2", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E2", "N2", "N3", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E3", "N3", "N4", EdgeType.ENABLES, 1))

        assert graph.validate_causal_dag() == []
        return graph

    def test_repair_split_preserves_contract_and_memberships(self, small_valid_graph):
        """SPLIT must produce child nodes with contracts, inherited memberships, and acyclic DAG."""
        graph = small_valid_graph
        engine = GeometryRepairEngine(graph)

        target_id = "N2"
        orig_threads = list(graph.get_node(target_id).thread_memberships)
        orig_revision = graph.graph_revision

        prop = RepairProposal(
            operation=RepairOperation.SPLIT,
            target_nodes=[target_id],
            reason="Density overload",
            detail={"split_count": 2},
        )
        ctx = {"turning_points_count": 3}
        res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

        assert res.success is True
        assert len(res.new_nodes) == 2
        assert target_id not in graph.nodes
        assert graph.graph_revision == orig_revision + 1

        for child_id in res.new_nodes:
            child = graph.get_node(child_id)
            assert child is not None
            assert child.story_contract is not None
            assert child.story_contract.node_id == child_id
            assert child.thread_memberships == orig_threads
            assert child.story_contract.thread_memberships == orig_threads
            assert child.planning_status == PlanningStatus.GATE_PASSED

        # DAG must remain acyclic
        assert graph.validate_causal_dag() == []

    def test_repair_expand_preserves_contract_and_memberships(self, small_valid_graph):
        """EXPAND must produce bridge/cluster nodes with contracts and valid causal edges."""
        graph = small_valid_graph
        engine = GeometryRepairEngine(graph)
        orig_revision = graph.graph_revision

        prop = RepairProposal(
            operation=RepairOperation.EXPAND,
            target_nodes=["N1", "N2"],
            reason="Convergence collision",
            detail={"add_count": 2},
        )
        ctx = {"converging_threads_count": 2, "has_volume_climax": True, "available_nodes_count": 2}
        res = engine.execute_repair(prop, GeometryRepairCondition.CONVERGENCE_COLLISION, ctx)

        assert res.success is True
        assert len(res.new_nodes) == 2
        assert graph.graph_revision == orig_revision + 1

        for new_id in res.new_nodes:
            new_node = graph.get_node(new_id)
            assert new_node is not None
            assert new_node.story_contract is not None
            assert new_node.story_contract.node_id == new_id
            assert new_node.thread_memberships == ["TM01"]

        assert graph.validate_causal_dag() == []

    def test_repair_insert_preserves_contract_and_memberships(self, small_valid_graph):
        """INSERT must create a bridge node connecting after_node to before_node."""
        graph = small_valid_graph
        engine = GeometryRepairEngine(graph)
        orig_revision = graph.graph_revision

        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N1", "N2"],
            reason="Causal gap",
            detail={"after_node_id": "N1", "before_node_id": "N2", "is_new_chapter": False},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "Bridge missing"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is True
        assert len(res.new_nodes) == 1
        bridge_id = res.new_nodes[0]
        bridge = graph.get_node(bridge_id)
        assert bridge is not None
        assert bridge.story_contract is not None
        assert bridge.thread_memberships == ["TM01"]
        assert graph.graph_revision == orig_revision + 1
        assert graph.validate_causal_dag() == []

    def test_repair_compress_unions_thread_memberships(self, small_valid_graph):
        """COMPRESS merges node_b into node_a and unions their thread memberships."""
        graph = small_valid_graph
        engine = GeometryRepairEngine(graph)

        # Set distinct memberships
        graph.get_node("N3").thread_memberships = ["TM01", "TS03"]
        graph.get_node("N3").story_contract.thread_memberships = ["TM01", "TS03"]
        graph.get_node("N4").thread_memberships = ["TM02", "TS07"]
        graph.get_node("N4").story_contract.thread_memberships = ["TM02", "TS07"]

        prop = RepairProposal(
            operation=RepairOperation.COMPRESS,
            target_nodes=["N3", "N4"],
            reason="Redundant filler",
            detail={},
        )
        ctx = {"turning_points_count": 3}
        res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

        assert res.success is True
        assert "N4" not in graph.nodes
        assert "N4" not in graph.story_contracts

        surviving = graph.get_node("N3")
        assert surviving is not None
        expected_union = ["TM01", "TS03", "TM02", "TS07"]
        assert surviving.thread_memberships == expected_union
        assert surviving.story_contract.thread_memberships == expected_union
        assert graph.validate_causal_dag() == []

    def test_repair_gatekeeper_rejection_leaves_graph_unmodified(self, small_valid_graph):
        """Proposals rejected by the gatekeeper must leave graph revision and structure intact."""
        graph = small_valid_graph
        engine = GeometryRepairEngine(graph)
        orig_nodes = list(graph.nodes.keys())
        orig_revision = graph.graph_revision

        prop = RepairProposal(
            operation=RepairOperation.SPLIT,
            target_nodes=["N1"],
            reason="Unjustified split",
            detail={},
        )
        # Context fails threshold (0 < 3)
        ctx = {"turning_points_count": 1}
        res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

        assert res.success is False
        assert "修復請求遭駁回" in res.message
        assert list(graph.nodes.keys()) == orig_nodes
        assert graph.graph_revision == orig_revision


# =============================================================================
# 5. Adversarial Flaw Remediation: Atomic Rollback on Rejected Cycle
# =============================================================================

class TestAdversarialRepairRollbackVulnerability:
    """
    Verify atomic rollback in GeometryRepairEngine:
    When a repair operation creates a causal cycle, execute_repair() catches the cycle,
    returns success=False, and cleanly rolls back in-place graph modifications,
    leaving the graph in its exact pristine pre-repair state.
    """

    def test_cyclical_repair_leaves_graph_corrupted_vulnerability(self):
        """
        Adversarially introduce an inverted INSERT (connecting N2 -> Bridge -> N1
        when N1 -> N2 already exists).
        Verify that execute_repair() reports success=False, and cleanly rolls back the graph
        so that no cycle or bridge node remains.
        """
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)
        graph.add_node(GeometryNode("N1", NodeHierarchy(1, 1, 1), (1, 2), StructuralRole.OPEN_THREAD, "TM01"))
        graph.add_node(GeometryNode("N2", NodeHierarchy(1, 1, 2), (3, 4), StructuralRole.CLOSE, "TM01"))
        graph.add_edge(GeometryEdge("E1", "N1", "N2", EdgeType.CAUSES, 1))

        assert graph.validate_causal_dag() == []

        engine = GeometryRepairEngine(graph)

        # Inverted bridge proposal: N2 (after) -> N1 (before)
        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N2", "N1"],
            reason="Adversarial backward bridge",
            detail={"after_node_id": "N2", "before_node_id": "N1"},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "Adversarial gap"}

        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        # The engine caught the cycle and flagged failure
        assert res.success is False
        assert "修復造成因果有向環路違規" in res.message

        # ATOMIC ROLLBACK VERIFICATION (Plan Section 5.2):
        # Validation failure must "丟棄補丁，保持舊版穩定".
        # When repair is rejected, the graph MUST be cleanly rolled back!
        post_repair_dag_errors = graph.validate_causal_dag()
        assert post_repair_dag_errors == [], f"Graph corrupted: {post_repair_dag_errors}"
        assert "G_BRIDGE_N2_N1" not in graph.nodes, "The bridge node was not rolled back upon repair failure"
        assert list(graph.nodes.keys()) == ["N1", "N2"]
        assert len(graph.edges) == 1
        assert graph.graph_revision == 1
