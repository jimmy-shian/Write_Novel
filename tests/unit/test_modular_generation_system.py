# -*- coding: utf-8 -*-
"""
Unit tests for the Modular Generation Subsystem:
1. Flow Spec & Dynamic Acts (eradicating 3-act limitation)
2. Planning Blueprint Generation & DB Persistence before Volumes
3. Entity & Foreshadowing ID Lifecycle Binding
4. Geometry Materialization
5. Four-Tier Rigid Gate Framework
6. Director DB-Factual Decision Arbiter & Anti-Loop Self-Healing
"""

import pytest
from unittest.mock import patch, MagicMock
from backend.generation.core.flow_spec import (
    TOPO_STAGE_ORDER,
    normalize_stage_name,
    compute_dynamic_acts,
    get_stage_prerequisites,
)
from backend.generation.modules.scale_architect import build_narrative_scale_spec
from backend.generation.modules.blueprint_planner import generate_planning_blueprint
from backend.generation.modules.entity_binder import bind_entities_and_foreshadowings
from backend.generation.modules.geometry_materializer import materialize_formal_geometry
from backend.generation.core.gates import evaluate_stage_rigid_gate
from backend.generation.director.arbiter import arbitrate_director_decision


def test_dynamic_acts_calculation():
    """Verify dynamic act scaling replaces rigid 3-act structure."""
    assert compute_dynamic_acts(1) == 5
    assert compute_dynamic_acts(2) == 5
    assert compute_dynamic_acts(4) == 8
    assert compute_dynamic_acts(9) == 12
    assert compute_dynamic_acts(16) == 16
    assert compute_dynamic_acts(24) >= 24


def test_stage_prerequisites():
    """Verify strict predecessor requirements."""
    assert get_stage_prerequisites("worldview") == []
    assert "worldview" in get_stage_prerequisites("planning_blueprint")
    assert "planning_blueprint" in get_stage_prerequisites("characters")
    assert "volumes" in get_stage_prerequisites("geometry")


def test_scale_architect_spec_generation():
    """Verify narrative scale spec constructs proper multi-act metadata."""
    novel_id = "test_scale_novel"
    with patch("backend.persistence.get_novel", return_value={"genre": "general_fiction", "target_volumes": 9}):
        with patch("backend.persistence.get_volumes", return_value=[]):
            spec = build_narrative_scale_spec(novel_id, target_volumes=9)
            assert spec.novel_id == novel_id
            assert spec.total_volumes == 9
            assert spec.act_count == 12
            assert len(spec.acts) == 12
            assert spec.acts[0].act_id == "ACT-01"
            assert spec.acts[-1].act_id == "ACT-12"
            assert spec.acts[-1].tension_target >= 0.9


def test_blueprint_planner_supports_short_scale_without_invalid_complexity():
    """Short works must use an enum value that exists in GeometryComplexity."""
    novel_id = "test_short_bp_novel"
    with patch("backend.persistence.get_novel", return_value={"genre": "general_fiction"}):
        with patch("backend.persistence.get_volumes", return_value=[]):
            with patch("backend.persistence.save_planning_blueprint"):
                blueprint = generate_planning_blueprint(novel_id, target_volumes=2)
    assert blueprint.state == "planning_blueprint"
    assert blueprint.scale_spec.act_count == 5


def test_blueprint_planner_persists_planning_blueprint():
    """Verify planning data is persisted separately from formal geometry."""
    novel_id = "test_bp_novel"
    saved_blueprints = []

    def mock_save(nid, blueprint):
        saved_blueprints.append(blueprint)

    with patch("backend.persistence.get_novel", return_value={"genre": "general_fiction"}):
        with patch("backend.persistence.get_volumes", return_value=[]):
            with patch("backend.persistence.save_planning_blueprint", side_effect=mock_save):
                bp = generate_planning_blueprint(novel_id, target_volumes=6)
                assert bp.state == "planning_blueprint"
                assert len(bp.nodes) > 0
                assert len(bp.edges) > 0
                assert len(bp.threads) >= 4
                assert len(saved_blueprints) == 1
                assert len(saved_blueprints[0].nodes) == len(bp.nodes)
                assert len(saved_blueprints[0].edges) == len(bp.edges)


def test_entity_and_foreshadowing_binding():
    """Verify seeds and turning points are bound with explicit IDs and coordinates."""
    novel_id = "test_binding_novel"
    mock_wb = {
        "content": '{"foreshadowing_seeds": [{"title": "古玉秘辛", "clue": "玉佩發熱", "truth": "詛咒之鎖"}]}'
    }
    mock_chars = {
        "json_data": '{"characters": [{"id": "CHAR-001", "name": "沈凌", "role": "主角"}]}'
    }

    with patch("backend.persistence.get_latest_worldbuilding", return_value=mock_wb):
        with patch("backend.persistence.get_latest_characters", return_value=mock_chars):
            with patch("backend.persistence.parse_worldview_to_json", return_value={"foreshadowing_seeds": [{"title": "古玉秘辛", "clue": "玉佩發熱", "truth": "詛咒之鎖"}]}):
                with patch("backend.persistence.get_geometry_stats", return_value={"node_count": 5}):
                    with patch("backend.persistence.load_geometry_graph", return_value=None):
                        bindings = bind_entities_and_foreshadowings(novel_id)
                        assert len(bindings) == 1
                        b = bindings[0]
                        assert b.foreshadowing_id == "FS-001"
                        assert b.title == "古玉秘辛"
                        assert b.carrier_character_ids == ["CHAR-001"]
                        assert b.planned_plant_act_id is not None
                        assert b.planned_payoff_act_id is not None


def test_four_tier_gate_evaluation():
    """Verify rigid four-tier gate intercepts missing physical DB data."""
    novel_id = "test_gate_novel"

    # 1. Empty worldview fails gate
    with patch("backend.persistence.get_latest_worldbuilding", return_value=None):
        gate = evaluate_stage_rigid_gate("worldview", novel_id)
        assert gate.passed is False
        assert "世界觀尚未持久化" in gate.defects[0]

    # 2. Empty geometry fails gate
    with patch("backend.persistence.get_geometry_stats", return_value={"node_count": 0, "edge_count": 0}):
        geom_gate = evaluate_stage_rigid_gate("geometry", novel_id)
        assert geom_gate.passed is False
        assert geom_gate.substantive_ok is False
        assert any("節點數為 0" in d for d in geom_gate.defects)

    # 3. Complete geometry passes gate
    with patch("backend.persistence.get_geometry_stats", return_value={"node_count": 10, "edge_count": 12, "thread_count": 4}):
        geom_gate_pass = evaluate_stage_rigid_gate("geometry", novel_id)
        assert geom_gate_pass.passed is True
        assert geom_gate_pass.substantive_ok is True


def test_director_arbiter_decisions():
    """Verify Director makes factual DB decisions and redirects to missing prerequisites."""
    novel_id = "test_dir_novel"

    # If characters are missing when evaluating foreshadowing, should REDIRECT to characters
    with patch("backend.generation.director.arbiter.evaluate_stage_rigid_gate") as mock_gate:
        # Mock worldview passed, blueprint passed, characters failed
        def gate_side_effect(stage, nid, ctx=None):
            if stage in ("worldview", "planning_blueprint"):
                from backend.generation.core.contracts import GateResult
                return GateResult(stage, True, True, True, True, True)
            else:
                from backend.generation.core.contracts import GateResult
                return GateResult(stage, False, False, False, False, False, ["缺失角色聖經"])
        mock_gate.side_effect = gate_side_effect

        dec = arbitrate_director_decision(novel_id, current_stage="foreshadowing", loop_count=0)
        assert dec.action == "REDIRECT"
        assert dec.target == "characters"


def test_director_arbiter_anti_loop_self_healing():
    """Verify Director triggers deterministic self-healing when loop count >= 3."""
    novel_id = "test_loop_novel"

    with patch("backend.generation.director.arbiter.heal_geometry_stalemate", return_value={"healed": True}):
        dec = arbitrate_director_decision(novel_id, current_stage="geometry", loop_count=3)
        assert dec.action == "CONTINUE"
        assert dec.target == "macro_semantic"
        assert "自愈修復" in dec.rationale["factual_db_state"]
