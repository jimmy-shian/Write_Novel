# -*- coding: utf-8 -*-
"""
Empirical Adversarial Retest Suite for Milestone 1 Iteration 2:
Atomic Rollback in GeometryRepairEngine and Type Safety in StoryEventContract.

Authored by Challenger M1 Retest.
"""

import copy
import pytest
from unittest.mock import patch
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


class TestAdversarialAtomicRollback:
    """Adversarial stress testing of GeometryRepairEngine.execute_repair() rollback semantics."""

    @pytest.fixture
    def chain_graph(self) -> GeometryGraph:
        """Constructs a deterministic 3-node causal chain N1 -> N2 -> N3."""
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)
        n1 = GeometryNode("N1", NodeHierarchy(1, 1, 1), (1, 2), StructuralRole.OPEN_THREAD, "TM01")
        n2 = GeometryNode("N2", NodeHierarchy(1, 1, 2), (3, 4), StructuralRole.DEVELOP, "TM01")
        n3 = GeometryNode("N3", NodeHierarchy(1, 1, 3), (5, 6), StructuralRole.CLOSE, "TM01")
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(n3)
        graph.add_edge(GeometryEdge("E1", "N1", "N2", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E2", "N2", "N3", EdgeType.CAUSES, 1))
        return graph

    def test_rollback_on_gatekeeper_rejection(self, chain_graph):
        """When gatekeeper rejects repair, graph is untouched."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        prop = RepairProposal(
            operation=RepairOperation.SPLIT,
            target_nodes=["N1"],
            reason="Unwarranted split",
            detail={"split_count": 2},
        )
        ctx = {"turning_points_count": 0}  # Fails threshold (needs >= 3)
        res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

        assert res.success is False
        assert "修復請求遭駁回" in res.message
        assert list(chain_graph.nodes.keys()) == list(oracle.nodes.keys())
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_operation_failure(self, chain_graph):
        """When operation itself reports failure, all mutations are rolled back."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["NON_EXISTENT_A", "NON_EXISTENT_B"],
            reason="Invalid anchors",
            detail={"after_node_id": "NON_EXISTENT_A", "before_node_id": "NON_EXISTENT_B"},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is False
        assert list(chain_graph.nodes.keys()) == list(oracle.nodes.keys())
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_2node_cycle(self, chain_graph):
        """Direct backward bridge N2 -> N1 creating 2-node cycle must be rolled back."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N2", "N1"],
            reason="Backwards bridge",
            detail={"after_node_id": "N2", "before_node_id": "N1"},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is False
        assert "修復造成因果有向環路違規" in res.message
        assert "G_BRIDGE_N2_N1" not in chain_graph.nodes
        assert "G_BRIDGE_N2_N1" not in chain_graph.story_contracts
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.validate_causal_dag() == []
        assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_multinode_cycle(self, chain_graph):
        """Backward bridge N3 -> N1 creating 3-node cycle N1->N2->N3->Bridge->N1."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N3", "N1"],
            reason="Adversarial long loop",
            detail={"after_node_id": "N3", "before_node_id": "N1"},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is False
        assert "修復造成因果有向環路違規" in res.message
        assert "G_BRIDGE_N3_N1" not in chain_graph.nodes
        assert chain_graph.validate_causal_dag() == []
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_cycle_with_downstream_chapter_shift(self, chain_graph):
        """
        Adversarial INSERT with is_new_chapter=True that induces a cycle.
        Validates that shift_downstream_chapters mutations are completely reverted.
        """
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)
        initial_target_chapters = chain_graph.params.target_chapters
        initial_n3_window = chain_graph.get_node("N3").chapter_window

        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N3", "N1"],
            reason="Backwards bridge with chapter extension",
            detail={"after_node_id": "N3", "before_node_id": "N1", "is_new_chapter": True},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is False
        assert chain_graph.params.target_chapters == initial_target_chapters
        assert chain_graph.get_node("N3").chapter_window == initial_n3_window
        assert "G_BRIDGE_N3_N1" not in chain_graph.nodes
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.validate_causal_dag() == []
        assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_unexpected_exception(self, chain_graph):
        """Simulate unexpected crash during repair operation."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        with patch.object(engine, "_op_split", side_effect=RuntimeError("Hardware fault / Memory error")):
            prop = RepairProposal(
                operation=RepairOperation.SPLIT,
                target_nodes=["N1"],
                reason="Split test",
                detail={"split_count": 2},
            )
            ctx = {"turning_points_count": 5}
            res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

            assert res.success is False
            assert "已原子回滾" in res.message
            assert "Hardware fault" in res.message
            assert list(chain_graph.nodes.keys()) == list(oracle.nodes.keys())
            assert len(chain_graph.edges) == len(oracle.edges)
            assert chain_graph.graph_revision == oracle.graph_revision

    def test_rollback_on_partial_mutation_exception(self, chain_graph):
        """Simulate partial graph mutations occurred prior to an exception."""
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        def leaky_op(proposal, condition):
            # Rogue mutation: corrupt graph state then explode
            chain_graph.nodes["LEAKED_NODE"] = GeometryNode(
                "LEAKED_NODE", NodeHierarchy(1, 1, 1), (1, 2), StructuralRole.DEVELOP, "TM01"
            )
            chain_graph.graph_revision = 999
            del chain_graph.nodes["N1"]
            raise ZeroDivisionError("Aborted halfway!")

        engine._op_split = leaky_op

        prop = RepairProposal(
            operation=RepairOperation.SPLIT,
            target_nodes=["N1"],
            reason="Corrupting split",
            detail={"split_count": 2},
        )
        ctx = {"turning_points_count": 5}
        res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, ctx)

        assert res.success is False
        assert "LEAKED_NODE" not in chain_graph.nodes
        assert "N1" in chain_graph.nodes
        assert chain_graph.graph_revision == oracle.graph_revision
        assert len(chain_graph.nodes) == len(oracle.nodes)
        assert chain_graph.validate_causal_dag() == []

    def test_sequential_rollback_torture_50_iterations(self, chain_graph):
        """
        Stress test: 50 consecutive failed operations interspersed with valid checks.
        Ensures that repeated rollbacks do not leak memory, mutate attributes, or drift revision.
        """
        engine = GeometryRepairEngine(chain_graph)
        oracle = copy.deepcopy(chain_graph)

        ctx_gap = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        ctx_split = {"turning_points_count": 5}

        for i in range(50):
            if i % 3 == 0:
                # Cyclical insert
                prop = RepairProposal(
                    operation=RepairOperation.INSERT,
                    target_nodes=["N3", "N1"],
                    reason=f"Cycle {i}",
                    detail={"after_node_id": "N3", "before_node_id": "N1"},
                )
                res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx_gap)
            elif i % 3 == 1:
                # Invalid node IDs
                prop = RepairProposal(
                    operation=RepairOperation.INSERT,
                    target_nodes=[f"FAKE_{i}_A", f"FAKE_{i}_B"],
                    reason=f"Fake {i}",
                    detail={"after_node_id": f"FAKE_{i}_A", "before_node_id": f"FAKE_{i}_B"},
                )
                res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx_gap)
            else:
                # Gatekeeper rejection
                prop = RepairProposal(
                    operation=RepairOperation.SPLIT,
                    target_nodes=["N1"],
                    reason=f"Gate reject {i}",
                    detail={"split_count": 2},
                )
                res = engine.execute_repair(prop, GeometryRepairCondition.DENSITY_OVERLOAD, {"turning_points_count": 0})

            assert res.success is False
            assert chain_graph.graph_revision == 1

        # Final verification: Graph is completely intact
        assert list(chain_graph.nodes.keys()) == list(oracle.nodes.keys())
        assert len(chain_graph.edges) == len(oracle.edges)
        assert chain_graph.validate_causal_dag() == []

    def test_full_scale_10_volume_graph_adversarial_rollback(self):
        """
        Full-scale stress test: 10 volumes, 500 chapters, ~1400 nodes.
        Attempts cross-volume backwards bridge from Vol 10 to Vol 1.
        Verifies 100% clean restoration of massive graph topology.
        """
        params = GeometryParams(target_chapters=500, volume_count=10, chapters_per_volume=50)
        graph = GeometryGenerator(params).generate()
        oracle = copy.deepcopy(graph)
        engine = GeometryRepairEngine(graph)

        v1_nodes = [nid for nid, n in graph.nodes.items() if n.hierarchy and n.hierarchy.volume_index == 1]
        v10_nodes = [nid for nid, n in graph.nodes.items() if n.hierarchy and n.hierarchy.volume_index == 10]
        v1_first = v1_nodes[0]
        v10_last = v10_nodes[-1]

        # Adversarial reverse bridge spanning 10 volumes
        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=[v10_last, v1_first],
            reason="Massive cross-volume cycle",
            detail={"after_node_id": v10_last, "before_node_id": v1_first, "is_new_chapter": True},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "gap"}
        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        assert res.success is False
        assert "因果有向環路違規" in res.message
        assert len(graph.nodes) == len(oracle.nodes)
        assert len(graph.edges) == len(oracle.edges)
        assert graph.graph_revision == oracle.graph_revision
        assert graph.params.target_chapters == oracle.params.target_chapters
        assert graph.validate_causal_dag() == []


class TestAdversarialTypeSafetyStoryEventContract:
    """Adversarial stress testing of StoryEventContract type enforcement and to_dict() safety."""

    NON_LIST_VALUES = [
        12345,
        3.14159,
        "not-a-list",
        {"dict_key": "val"},
        None,
        True,
        False,
        (1, 2, 3),
        {1, 2, 3},
        object(),
        lambda x: x,
        (x for x in range(5)),
    ]

    def test_validate_nine_dimensions_rejects_non_list_participant_entities(self):
        """Passing non-list types to participant_entities must be cleanly rejected in defects."""
        for val in self.NON_LIST_VALUES:
            ev = StoryEventContract(
                event_id="EV_ADV_T1",
                node_id="G0001",
                event_summary="Valid summary text",
                participant_entities=val,
                action_motives=[{"char_id": "C1", "motive": "Survive"}],
                causal_preconditions=["EV00"],
                core_conflict="Battle at the gate",
                direct_outcome="Protagonist breached gate",
            )
            valid, defects = ev.validate_nine_dimensions(strict=False)
            assert valid is False, f"Expected invalid for participant_entities={type(val)}"
            assert any("participant_entities 必須為清單" in d for d in defects), (
                f"Defects did not mention list type requirement for {type(val)}: {defects}"
            )

    def test_validate_nine_dimensions_rejects_non_list_action_motives(self):
        """Passing non-list types to action_motives must be cleanly rejected in defects."""
        for val in self.NON_LIST_VALUES:
            ev = StoryEventContract(
                event_id="EV_ADV_T2",
                node_id="G0001",
                event_summary="Valid summary text",
                participant_entities=[{"char_id": "C1", "role": "FIGHTER"}],
                action_motives=val,
                causal_preconditions=["EV00"],
                core_conflict="Battle at the gate",
                direct_outcome="Protagonist breached gate",
            )
            valid, defects = ev.validate_nine_dimensions(strict=False)
            assert valid is False, f"Expected invalid for action_motives={type(val)}"
            assert any("action_motives 必須為清單" in d for d in defects), (
                f"Defects did not mention list type requirement for {type(val)}: {defects}"
            )

    def test_to_dict_never_crashes_on_non_list_fields(self):
        """StoryEventContract.to_dict() must never crash even when non-list types are present."""
        for val in self.NON_LIST_VALUES:
            ev = StoryEventContract(
                event_id="EV_ADV_T3",
                node_id="G0001",
                event_summary="Valid summary text",
                participant_entities=val,
                action_motives=val,
                causal_preconditions=val,
                core_conflict="Conflict",
                direct_outcome="Outcome",
                state_mutations=val,
                downstream_impact=val,
                clue_bindings=val,
            )
            d = ev.to_dict()
            assert isinstance(d, dict)
            assert d["event_id"] == "EV_ADV_T3"
            assert d["participant_entities"] == val
            assert d["action_motives"] == val

    def test_to_dict_handles_mixed_and_nested_element_types(self):
        """StoryEventContract.to_dict() safely formats list items whether they are dicts or primitives."""
        mixed_list = [
            {"char_id": "C1", "role": "LEAD"},
            "raw_string",
            123,
            None,
            {"nested": {"level": 2}},
        ]
        ev = StoryEventContract(
            event_id="EV_ADV_T4",
            node_id="G0001",
            event_summary="Summary",
            participant_entities=mixed_list,
            action_motives=mixed_list,
            core_conflict="Conflict",
            direct_outcome="Outcome",
        )
        d = ev.to_dict()
        assert len(d["participant_entities"]) == len(mixed_list)
        assert d["participant_entities"][0] == {"char_id": "C1", "role": "LEAD"}
        assert d["participant_entities"][1] == "raw_string"
        assert d["participant_entities"][2] == 123
        assert d["participant_entities"][3] is None
