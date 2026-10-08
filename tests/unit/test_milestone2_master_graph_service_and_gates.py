# -*- coding: utf-8 -*-
"""
單元測試套件：Milestone 2 - Master Graph Service Layer, Impact Analyzer & Completion Gates
File: tests/unit/test_milestone2_master_graph_service_and_gates.py

全量覆蓋 Milestone 2 核心架構規範：
1. TopologyGate (因果無環、端點放行、非因果邊隔離、24線程有效通路)
2. ForeshadowingGate (Plant < Turn < Payoff 時序嚴格性、因果邊解耦、100% 閉環)
3. TwistGate (核心節點 100% 九維故事事件完備性驗證)
4. WorldviewGate & CharacterGate (世界觀槽位回填、角色去命運化 De-destined 無劇透準則)
5. StoryCompletionGate (動筆前全域終極審計、24線程收束、拍點全覆蓋、STORY_CANON_LOCKED 正典鎖定)
6. MasterGraphService (槽位原子回填、嚴格防劇透牆 Spoiler Wall、Token剪裁、草稿補丁暫存與原子提交、正典鎖定)
7. ImpactAnalyzer & LocalRepairCoordinator (動態欄位依賴分析、四級局部修復協調與回滾保護)
"""

import copy
import pytest
from typing import Dict, Any, List

from backend.geometry.models import (
    GeometryGraph,
    GeometryNode,
    GeometryEdge,
    GeometryParams,
    GeometryComplexity,
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
    make_gate_result,
)
from backend.generation.director.master_graph_service import (
    MasterGraphService,
    DraftGraphPatch,
    estimate_tokens,
    prune_context_by_budget,
)
from backend.generation.director.impact_analyzer import (
    ImpactAnalyzer,
    LocalRepairCoordinator,
    RepairTier,
    RepairRequest,
    classify_field,
    analyze_node_impact,
)
from backend.geometry.repair import (
    GeometryRepairCondition,
    RepairOperation,
    RepairProposal,
)


# =============================================================================
# Helper Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def generated_test_graph() -> GeometryGraph:
    """提供標準規格 10 卷 24 線程的 Master Graph 實例。"""
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
        seed_for_rng="m2_master_gate_seed_2026",
    )
    generator = GeometryGenerator(params)
    return generator.generate()


@pytest.fixture
def populated_story_graph(generated_test_graph) -> GeometryGraph:
    """提供已回填完備故事要素之 Master Graph 供終極門禁測試。"""
    graph = copy.deepcopy(generated_test_graph)

    # 1. 回填世界觀槽位
    for node in graph.nodes.values():
        if WorldviewGate._is_collision_node(node):
            node.story_contract.worldview_slot = {
                "faction_ids": ["F01", "F02"],
                "location_id": "LOC_ROYAL_CITY",
                "conflict_cause": "古神封印核心裂解與邊境開採權衝突",
            }

    # 2. 回填去命運化客觀角色槽位 (35 位獨立角色)
    for idx, node in enumerate(graph.nodes.values()):
        node.story_contract.character_slots = [
            {
                "character_id": f"C{idx % 35:03d}",
                "role_in_node": "OPERATIVE",
                "initial_status": "NORMAL",
            }
        ]

    # 3. 回填核心節點九維故事事件
    for idx, node in enumerate(graph.nodes.values()):
        if TwistGate.is_core_node(node):
            node.story_contract.story_events = [
                StoryEventContract(
                    event_id=f"EV_M2_{idx:03d}",
                    node_id=node.node_id,
                    event_summary=f"重大轉折事件 {idx}",
                    participant_entities=[{"char_id": "C001", "role": "HERO"}],
                    action_motives=[{"char_id": "C001", "motive": "守護誓約"}],
                    causal_preconditions=[],
                    core_conflict="要塞圍困戰正面突破",
                    direct_outcome="突圍成功並取得信物",
                    state_mutations=[{"char_id": "C001", "type": "RESOLVE_BOOST"}],
                    downstream_impact=["引發大軍全域搜捕"],
                    clue_bindings=["FSH_TEST_001"],
                )
            ]

    # 4. 回填一組有效伏筆 (Plant < Payoff)
    plant_node = graph.get_node(graph.threads["TM01"].node_sequence[0])
    payoff_node = graph.get_node(graph.threads["TM01"].node_sequence[-1])
    plant_node.story_contract.foreshadowing_tasks.append({
        "clue_id": "FSH_TEST_001",
        "role": "PLANT",
        "summary": "密室密函種下懷疑種子",
    })
    payoff_node.story_contract.foreshadowing_tasks.append({
        "clue_id": "FSH_TEST_001",
        "role": "PAYOFF",
        "summary": "密函揭露大主教叛變真相",
    })

    # 5. 確保全節點章節視窗有效
    for node in graph.nodes.values():
        if not node.chapter_window or node.chapter_window[0] <= 0:
            node.chapter_window = (1, 1)

    return graph


# =============================================================================
# 1. TopologyGate Unit Tests
# =============================================================================

class TestTopologyGate:
    """驗證 TopologyGate 因果無環、邊界入出度與 24 線程可達性。"""

    def test_topology_gate_standard_graph_passes(self, generated_test_graph):
        """標準幾何圖譜應 100% 通過拓撲門禁。"""
        graph = copy.deepcopy(generated_test_graph)
        res = TopologyGate.evaluate(graph)
        assert res.passed is True
        assert res.metrics["cycle_errors_count"] == 0
        assert res.metrics["expected_24_threads_count"] == 24
        assert res.metrics["verified_24_threads_count"] == 24

    def test_topology_gate_allows_in_degree_zero_and_out_degree_zero(self, generated_test_graph):
        """驗證起點入度 0 與終點出度 0 不被視為缺陷。"""
        graph = copy.deepcopy(generated_test_graph)
        res = TopologyGate.evaluate(graph)
        assert res.passed is True
        assert res.metrics["start_nodes_count"] >= 1
        assert res.metrics["end_nodes_count"] >= 1
        assert not any("in-degree" in d.lower() for d in res.defects)
        assert not any("out-degree" in d.lower() for d in res.defects)

    def test_topology_gate_detects_causal_cycle(self, generated_test_graph):
        """注入因果邊環路應被嚴格捕獲並標記失敗。"""
        graph = copy.deepcopy(generated_test_graph)
        u, v = list(graph.nodes.keys())[0], list(graph.nodes.keys())[1]
        graph.add_edge(GeometryEdge(
            edge_id="EDGE_CYCLE_FAIL",
            source=v,
            target=u,
            edge_type=EdgeType.CAUSES,
            distance=1,
        ))
        res = TopologyGate.evaluate(graph)
        assert res.passed is False
        assert res.structural_ok is False
        assert any("cycle" in d.lower() or "loop" in d.lower() for d in res.defects)

    def test_topology_gate_isolates_non_causal_edges(self, generated_test_graph):
        """非因果雙向邊 (如 ECHOES) 不應污染因果 DAG。"""
        graph = copy.deepcopy(generated_test_graph)
        u, v = list(graph.nodes.keys())[0], list(graph.nodes.keys())[1]
        graph.add_edge(GeometryEdge(
            edge_id="EDGE_ECHO_1",
            source=u,
            target=v,
            edge_type=EdgeType.ECHOES,
            distance=1,
        ))
        graph.add_edge(GeometryEdge(
            edge_id="EDGE_ECHO_2",
            source=v,
            target=u,
            edge_type=EdgeType.ECHOES,
            distance=1,
        ))
        res = TopologyGate.evaluate(graph)
        assert res.passed is True
        assert res.metrics["cycle_errors_count"] == 0

    def test_topology_gate_detects_broken_thread_pathway(self, generated_test_graph):
        """線程通路斷裂時應精確報警。"""
        graph = copy.deepcopy(generated_test_graph)
        thread = graph.threads["TM01"]
        u = thread.node_sequence[0]
        # 刪除從 u 出發的所有邊，造成通路斷裂
        graph.edges = [e for e in graph.edges if e.source != u]
        res = TopologyGate.evaluate(graph)
        assert res.passed is False
        assert any("TM01" in d for d in res.defects)


# =============================================================================
# 2. ForeshadowingGate Unit Tests
# =============================================================================

class TestForeshadowingGate:
    """驗證 ForeshadowingGate 敘事時序、伏筆閉環與因果邊解耦特性。"""

    def test_foreshadowing_gate_valid_closure_passes(self, generated_test_graph):
        """成對伏筆且時序正確應通過門禁。"""
        graph = copy.deepcopy(generated_test_graph)
        p_node = graph.get_node(graph.threads["TM01"].node_sequence[0])
        y_node = graph.get_node(graph.threads["TM01"].node_sequence[-1])

        p_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_TEST_PAIR",
            "role": "PLANT",
            "summary": "埋下伏筆",
        })
        y_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_TEST_PAIR",
            "role": "PAYOFF",
            "summary": "回收伏筆",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is True
        assert res.metrics["closure_rate"] == 1.0

    def test_foreshadowing_gate_decoupled_from_causal_reachability(self, generated_test_graph):
        """跨主支線且因果圖無路徑可達之伏筆配對應合法通過。"""
        graph = copy.deepcopy(generated_test_graph)
        # 於支線 TS02 首節點埋設，於主線 TM01 尾節點回收
        p_node = graph.get_node(graph.threads["TS02"].node_sequence[0])
        y_node = graph.get_node(graph.threads["TM01"].node_sequence[-1])

        p_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_DECOUPLED_01",
            "role": "PLANT",
            "summary": "支線隨手埋設神秘硬幣",
        })
        y_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_DECOUPLED_01",
            "role": "PAYOFF",
            "summary": "主線決戰關鍵使用硬幣開啟機關",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is True
        assert res.metrics["closed_clues"] >= 1

    def test_foreshadowing_gate_detects_temporal_reversal(self, generated_test_graph):
        """時序倒置（回收早於埋設）應判定違規。"""
        graph = copy.deepcopy(generated_test_graph)
        late_node = graph.get_node(graph.threads["TM01"].node_sequence[-1])
        early_node = graph.get_node(graph.threads["TM01"].node_sequence[0])

        late_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_TIME_WARP",
            "role": "PLANT",
            "summary": "晚期埋設",
        })
        early_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_TIME_WARP",
            "role": "PAYOFF",
            "summary": "早期回收",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert any("時序倒置" in d or "早於" in d for d in res.defects)

    def test_foreshadowing_gate_detects_unclosed_clue(self, generated_test_graph):
        """未閉環伏筆（有埋設無回收）應失敗。"""
        graph = copy.deepcopy(generated_test_graph)
        early_node = graph.get_node(graph.threads["TM01"].node_sequence[0])
        early_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_FORGOTTEN",
            "role": "PLANT",
            "summary": "被遺忘的伏筆",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert any("未閉環" in d or "FSH_FORGOTTEN" in d for d in res.defects)

    def test_foreshadowing_gate_detects_orphan_payoff(self, generated_test_graph):
        """孤立回收伏筆（有回收無埋設）應失敗。"""
        graph = copy.deepcopy(generated_test_graph)
        late_node = graph.get_node(graph.threads["TM01"].node_sequence[-1])
        late_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_ORPHAN",
            "role": "PAYOFF",
            "summary": "無中生有的揭示",
        })

        res = ForeshadowingGate.evaluate(graph)
        assert res.passed is False
        assert any("缺少埋設" in d or "孤立回收" in d for d in res.defects)


# =============================================================================
# 3. TwistGate Unit Tests
# =============================================================================

class TestTwistGate:
    """驗證 TwistGate 核心劇情九維故事事件完備性。"""

    def test_twist_gate_complete_core_nodes_pass(self, populated_story_graph):
        """核心節點 100% 填滿九維事件時通過。"""
        res = TwistGate.evaluate(populated_story_graph, strict=True)
        assert res.passed is True
        assert res.metrics["core_completion_rate"] == 1.0

    def test_twist_gate_detects_missing_events_on_core_node(self, populated_story_graph):
        """核心節點缺少 story_events 時應標記失敗。"""
        graph = copy.deepcopy(populated_story_graph)
        core_node = [n for n in graph.nodes.values() if TwistGate.is_core_node(n)][0]
        core_node.story_contract.story_events = []

        res = TwistGate.evaluate(graph, strict=True)
        assert res.passed is False
        assert any("story_events 為空" in d for d in res.defects)

    def test_twist_gate_detects_defective_nine_dimensions(self, populated_story_graph):
        """九維合約關鍵欄位（如 core_conflict, direct_outcome）缺失時應標記失敗。"""
        graph = copy.deepcopy(populated_story_graph)
        core_node = [n for n in graph.nodes.values() if TwistGate.is_core_node(n)][0]
        core_node.story_contract.story_events[0].direct_outcome = ""

        res = TwistGate.evaluate(graph, strict=True)
        assert res.passed is False
        assert any("direct_outcome" in d for d in res.defects)


# =============================================================================
# 4. WorldviewGate & CharacterGate Unit Tests
# =============================================================================

class TestWorldviewAndCharacterGates:
    """驗證世界觀槽位回填完備性與角色去命運化客觀屬性準則。"""

    def test_worldview_gate_collision_nodes_pass(self, populated_story_graph):
        """碰撞節點皆回填勢力、地點與衝突誘因時通過。"""
        res = WorldviewGate.evaluate(populated_story_graph)
        assert res.passed is True
        assert res.metrics["worldview_backfill_rate"] == 1.0

    def test_worldview_gate_fails_when_slot_missing(self, populated_story_graph):
        """碰撞節點遺漏 worldview_slot 時失敗。"""
        graph = copy.deepcopy(populated_story_graph)
        collision_node = [n for n in graph.nodes.values() if WorldviewGate._is_collision_node(n)][0]
        collision_node.story_contract.worldview_slot = None

        res = WorldviewGate.evaluate(graph)
        assert res.passed is False
        assert any("尚未回填 worldview_slot" in d for d in res.defects)

    def test_character_gate_de_destined_verification(self, populated_story_graph):
        """角色客觀屬性正常且規模充足時通過。"""
        res = CharacterGate.evaluate(populated_story_graph, min_roster_count=20)
        assert res.passed is True
        assert res.metrics["de_destined_compliance"] is True

    def test_character_gate_rejects_premature_destiny_spoilers(self, populated_story_graph):
        """角色初始狀態填入 DEAD 或劇透欄位時，違反去命運化原則，必須失敗。"""
        graph = copy.deepcopy(populated_story_graph)
        first_node = list(graph.nodes.values())[0]
        first_node.story_contract.character_slots[0]["initial_status"] = "DEAD"

        res = CharacterGate.evaluate(graph, min_roster_count=20)
        assert res.passed is False
        assert any("去命運化" in d or "DEAD" in d for d in res.defects)


# =============================================================================
# 5. StoryCompletionGate Unit Tests
# =============================================================================

class TestStoryCompletionGate:
    """驗證 StoryCompletionGate 全局完備性審計與 STORY_CANON_LOCKED 鎖定。"""

    def test_story_completion_gate_success_locks_story_canon(self, populated_story_graph):
        """全項指標合規時，門禁通過並將 Master Graph 與所有節點原子鎖定為 STORY_CANON_LOCKED。"""
        graph = copy.deepcopy(populated_story_graph)
        res = StoryCompletionGate.evaluate(graph, min_roster_count=30, auto_lock=True)

        assert res.passed is True
        assert res.metrics["canon_locked"] is True
        assert graph.planning_status == PlanningStatus.STORY_CANON_LOCKED
        for node in graph.nodes.values():
            assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED
            assert node.metadata.get("planning_status") == "STORY_CANON_LOCKED"

    def test_story_completion_gate_fails_when_clues_unclosed(self, populated_story_graph):
        """存在未閉環伏筆時，禁止鎖定故事 Canon。"""
        graph = copy.deepcopy(populated_story_graph)
        early_node = graph.get_node(graph.threads["TM01"].node_sequence[0])
        early_node.story_contract.foreshadowing_tasks.append({
            "clue_id": "FSH_DANGLING_END",
            "role": "PLANT",
            "summary": "未收伏筆",
        })

        res = StoryCompletionGate.evaluate(graph, min_roster_count=30, auto_lock=True)
        assert res.passed is False
        assert res.metrics["canon_locked"] is False
        assert getattr(graph, "planning_status", None) != PlanningStatus.STORY_CANON_LOCKED

    def test_story_completion_gate_fails_when_node_unmapped_to_chapter(self, populated_story_graph):
        """節點未映射至任何章節拍點時判定不完備。"""
        graph = copy.deepcopy(populated_story_graph)
        first_node = list(graph.nodes.values())[0]
        first_node.chapter_window = (0, 0)
        first_node.story_contract.chapter_mappings = []

        res = StoryCompletionGate.evaluate(graph, min_roster_count=30, auto_lock=True)
        assert res.passed is False
        assert any("NODE_CHAPTER_BEATS" in d for d in res.defects)


# =============================================================================
# 6. MasterGraphService Unit Tests
# =============================================================================

class TestMasterGraphService:
    """驗證 MasterGraphService 槽位回填、防劇透上下文投影、草稿暫存與原子提交。"""

    def test_slot_backfill_all_types(self, generated_test_graph):
        """驗證所有 6 種故事要素槽位的原子回填及雙向同步。"""
        graph = copy.deepcopy(generated_test_graph)
        nid = list(graph.nodes.keys())[0]

        # 1. Worldview slot
        c1 = MasterGraphService.backfill_worldview_slot(graph, nid, {
            "faction_ids": ["F1", "F2"],
            "location_id": "LOC_VALLEY",
            "conflict_cause": "邊境衝突",
        })
        assert graph.nodes[nid].semantic["location_id"] == "LOC_VALLEY"
        assert c1.worldview_slot["location_id"] == "LOC_VALLEY"

        # 2. Character slots
        c2 = MasterGraphService.backfill_character_slots(graph, nid, [
            {"character_id": "C001", "role_in_node": "LEADER", "initial_status": "NORMAL"}
        ])
        assert len(c2.character_slots) == 1
        assert c2.character_slots[0]["character_id"] == "C001"

        # 3. Story events
        ev = StoryEventContract(
            event_id="EV_TEST_01",
            node_id=nid,
            event_summary="突襲成功",
            participant_entities=[{"char_id": "C001"}],
            action_motives=[{"char_id": "C001", "motive": "救援"}],
            causal_preconditions=[],
            core_conflict="要塞防禦戰",
            direct_outcome="破門而入",
            state_mutations=[{"char_id": "C001", "type": "MORALE_UP"}],
            downstream_impact=["引發支援大軍警戒"],
            clue_bindings=["CLUE_01"],
        )
        c3 = MasterGraphService.backfill_story_events(graph, nid, [ev], validate=True, strict=True)
        assert len(c3.story_events) == 1
        assert c3.story_events[0].core_conflict == "要塞防禦戰"

        # 4. Destiny events
        c4 = MasterGraphService.backfill_destiny_events(graph, nid, [
            {"char_id": "C001", "type": "AWAKENING", "summary": "獲得古神傳承"}
        ])
        assert len(c4.destiny_events) == 1

        # 5. Foreshadowing tasks
        c5 = MasterGraphService.backfill_foreshadowing_tasks(graph, nid, [
            {"clue_id": "CLUE_01", "role": "PLANT", "summary": "留下破裂信物"}
        ])
        assert len(c5.foreshadowing_tasks) == 1

        # 6. Chapter mappings (驗證 chapter_window 同步)
        c6 = MasterGraphService.backfill_chapter_mappings(graph, nid, [
            {"chapter_index": 5, "beat_index": 1, "coverage_ratio": 0.5},
            {"chapter_index": 6, "beat_index": 2, "coverage_ratio": 0.5},
        ])
        assert len(c6.chapter_mappings) == 2
        assert graph.nodes[nid].chapter_window == (5, 6)

        # 7. Generic backfill_slot dispatcher
        c7 = MasterGraphService.backfill_slot(graph, nid, "worldview", {
            "faction_ids": ["F1", "F3"],
            "location_id": "LOC_NEW",
            "conflict_cause": "擴大衝突",
        })
        assert c7.worldview_slot["location_id"] == "LOC_NEW"

    def test_scoped_context_projection_strict_spoiler_wall_for_writer(self, populated_story_graph):
        """針對 chapter_writer 啟用嚴格防劇透牆：遮蔽未來卷次、下游轉折、未到期伏筆與角色未來命運。"""
        graph = copy.deepcopy(populated_story_graph)
        nid = graph.threads["TM01"].node_sequence[0]

        proj = MasterGraphService.project_node_context(graph, nid, target_agent="chapter_writer")

        # 1. 驗證防劇透狀態啟用
        assert proj["spoiler_wall_active"] is True
        assert proj["target_agent"] == "chapter_writer"

        # 2. 驗證後續卷大綱被遮蔽
        assert proj["volume_context"]["subsequent_volumes"] == "[PROTECTED_BY_SPOILER_WALL]"

        # 3. 驗證下游因果節點被 spoiler_shield 掩護
        for succ in proj["downstream_trajectory"]:
            assert "spoiler_shield" in succ
            assert "SPOILER_WALL_ACTIVE" in succ["spoiler_shield"]
            assert "event_summaries" not in succ

        # 4. 驗證伏筆任務中 PLANT 的未來結局被遮蔽
        for task in proj["current_scene_contract"]["foreshadowing_tasks"]:
            if task.get("role") == "PLANT":
                assert task.get("future_payoff_target") == "[SPOILER_PROTECTED_FUTURE_PAYOFF]"
                assert "secret_core_truth" not in task

    def test_scoped_context_projection_transparency_for_director(self, populated_story_graph):
        """針對 director 投影應保持全域透明無遮蔽。"""
        graph = copy.deepcopy(populated_story_graph)
        nid = graph.threads["TM01"].node_sequence[0]

        proj = MasterGraphService.project_node_context(graph, nid, target_agent="director")

        assert proj["spoiler_wall_active"] is False
        assert "subsequent_volumes" not in proj["volume_context"]
        assert "all_volumes" in proj["volume_context"]
        for succ in proj["downstream_trajectory"]:
            assert "spoiler_shield" not in succ

    def test_scoped_context_projection_fact_baseline_for_editor(self, populated_story_graph):
        """針對 editor 提供事實保全基準線 (Fact Diff Guard Baseline)。"""
        graph = copy.deepcopy(populated_story_graph)
        nid = [n for n in graph.nodes.values() if TwistGate.is_core_node(n)][0].node_id

        proj = MasterGraphService.project_node_context(graph, nid, target_agent="editor")

        assert "fact_preservation_baseline" in proj
        baseline = proj["fact_preservation_baseline"]
        assert "required_participants" in baseline
        assert "required_core_conflicts" in baseline
        assert "required_outcomes" in baseline

    def test_scoped_context_projection_token_pruning(self, populated_story_graph):
        """當上下文超出 token_budget 時，五級剪裁引擎應介入執行修剪。"""
        graph = copy.deepcopy(populated_story_graph)
        nid = graph.threads["TM01"].node_sequence[1]

        # 設置極低的 Token 預算
        proj = MasterGraphService.project_node_context(
            graph, nid, target_agent="chapter_writer", token_budget=150
        )
        assert proj["token_metrics"]["pruned"] is True
        assert len(proj["token_metrics"]["pruning_tiers_applied"]) > 0

    def test_draft_patch_lifecycle_apply_and_commit(self, generated_test_graph):
        """驗證 DraftGraphPatch 建立、套用、原子提交與版本號單調遞增。"""
        graph = copy.deepcopy(generated_test_graph)
        initial_rev = graph.graph_revision
        nid = list(graph.nodes.keys())[0]

        # 1. 建立補丁
        patch = MasterGraphService.create_draft_patch(graph)
        assert patch.status == "PENDING"
        assert patch.base_revision == initial_rev

        # 2. 暫存更新
        patch.stage_worldview_slot(nid, {
            "faction_ids": ["F_PATCH"],
            "location_id": "LOC_PATCH",
            "conflict_cause": "補丁注入衝突",
        })

        # 3. 套用補丁 (版本號尚不應遞增)
        MasterGraphService.apply_draft_patch(graph, patch)
        assert patch.status == "APPLIED"
        assert graph.graph_revision == initial_rev
        assert graph.nodes[nid].semantic["location_id"] == "LOC_PATCH"

        # 4. 原子提交 (版本號應單調遞增)
        new_rev = MasterGraphService.commit_draft_patch(graph, patch)
        assert new_rev == initial_rev + 1
        assert graph.graph_revision == initial_rev + 1
        assert graph.nodes[nid].graph_revision == new_rev
        assert patch.status == "COMMITTED"

    def test_draft_patch_discard_and_rollback(self, generated_test_graph):
        """驗證丟棄補丁時圖譜原子回滾至初始快照。"""
        graph = copy.deepcopy(generated_test_graph)
        nid = list(graph.nodes.keys())[0]
        original_semantic = copy.deepcopy(graph.nodes[nid].semantic)

        patch = MasterGraphService.create_draft_patch(graph)
        patch.stage_worldview_slot(nid, {"location_id": "LOC_TEMP_MODIFIED"})
        MasterGraphService.apply_draft_patch(graph, patch)
        assert graph.nodes[nid].semantic["location_id"] == "LOC_TEMP_MODIFIED"

        # 丟棄補丁
        MasterGraphService.discard_draft_patch(patch, graph)
        assert patch.status == "DISCARDED"
        assert graph.nodes[nid].semantic == original_semantic

    def test_draft_patch_rejects_causal_cycle_on_commit(self, generated_test_graph):
        """若補丁引進因果環路，commit 必須拒絕並回滾。"""
        graph = copy.deepcopy(generated_test_graph)
        u, v = list(graph.nodes.keys())[0], list(graph.nodes.keys())[1]

        patch = MasterGraphService.create_draft_patch(graph)
        # 增加一條反向因果邊製造環路
        patch.edge_additions.append(MasterGraphEdgeContract(
            edge_id="EDGE_PATCH_CYCLE",
            source_id=v,
            target_id=u,
            edge_type=EdgeType.CAUSES,
        ))

        with pytest.raises(ValueError, match="Causal DAG validation failed"):
            MasterGraphService.commit_draft_patch(graph, patch)

        assert patch.status == "DISCARDED"


# =============================================================================
# 7. ImpactAnalyzer Unit Tests
# =============================================================================

class TestImpactAnalyzer:
    """驗證 ImpactAnalyzer 動態欄位依賴分析：修辭欄位最小化、角色同卷傳播、因果鏈與伏筆閉環。"""

    def test_cosmetic_fields_isolated_to_target_node(self, generated_test_graph):
        """純外觀/修辭欄位變更時，影響集合嚴格局限於 {node_id}。"""
        analyzer = ImpactAnalyzer()
        nid = list(generated_test_graph.nodes.keys())[0]

        impact = analyzer.analyze_node_impact(
            generated_test_graph, nid, ["title", "description", "surface_text"]
        )
        assert impact == {nid}

    def test_character_attribute_changes_propagate_in_volume_only(self, populated_story_graph):
        """角色屬性變更時，波及當前卷內登場同角色的所有場景節點，不跨卷擴散。"""
        analyzer = ImpactAnalyzer()
        node = list(populated_story_graph.nodes.values())[0]
        nid = node.node_id
        current_vol = node.hierarchy.volume_index

        impact = analyzer.analyze_node_impact(
            populated_story_graph, nid, ["character_slots", "appearance"]
        )
        assert nid in impact
        # 確保所有被波及的節點皆在同一個 volume
        for affected_id in impact:
            affected_node = populated_story_graph.get_node(affected_id)
            assert affected_node.hierarchy.volume_index == current_vol

    def test_causal_changes_propagate_downstream_and_close_clues(self, generated_test_graph):
        """因果核心欄位變更時，沿因果邊遍歷下游影響鏈 + 伏筆線索閉環。"""
        graph = copy.deepcopy(generated_test_graph)
        analyzer = ImpactAnalyzer()

        t_nodes = graph.threads["TM01"].node_sequence
        n0, n1, n2 = t_nodes[0], t_nodes[1], t_nodes[2]

        # 綁定伏筆
        graph.nodes[n1].metadata["clue_bindings"] = ["FSH_LINKED"]
        other_node = t_nodes[-1]
        graph.nodes[other_node].metadata["clue_bindings"] = ["FSH_LINKED"]

        impact = analyzer.analyze_node_impact(
            graph, n0, ["state_mutations", "core_conflict"]
        )

        assert n0 in impact
        assert n1 in impact
        # 下游因果後繼節點應被包含
        assert n2 in impact
        # 伏筆閉環關聯節點應被包含
        assert other_node in impact

    def test_non_causal_edges_isolated_from_causal_impact(self, generated_test_graph):
        """非因果邊 (如 ECHOES, CONTRASTS) 不得被因果傳播穿透。"""
        graph = copy.deepcopy(generated_test_graph)
        analyzer = ImpactAnalyzer()

        u, v = list(graph.nodes.keys())[0], list(graph.nodes.keys())[1]
        # 移除 u 的其他出邊
        graph.edges = [e for e in graph.edges if e.source != u]
        # 僅加入一條 ECHOES 邊
        graph.add_edge(GeometryEdge(
            edge_id="EDGE_ECHO_ONLY",
            source=u,
            target=v,
            edge_type=EdgeType.ECHOES,
            distance=1,
        ))

        impact = analyzer.analyze_node_impact(graph, u, ["state_mutations"])
        assert u in impact
        assert v not in impact


# =============================================================================
# 8. LocalRepairCoordinator Unit Tests
# =============================================================================

class TestLocalRepairCoordinator:
    """驗證總監四級局部修復政策協調機制與安全回滾。"""

    def test_level_1_prompt_retry_keeps_graph_untouched(self, generated_test_graph):
        """Level 1 修復僅產生負反饋指令，Master Graph 保持零變更。"""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(generated_test_graph)
        initial_rev = graph.graph_revision

        req = RepairRequest(
            node_id="G0001",
            defects=["JSON parse failed: missing closing bracket"],
            retry_count=0,
        )
        res = coordinator.coordinate_repair(graph, req)

        assert res.success is True
        assert res.tier == RepairTier.LEVEL_1_AGENT_PROMPT
        assert len(res.affected_nodes) == 0
        assert graph.graph_revision == initial_rev
        assert "agent_prompt" in res.directive

    def test_level_2_slot_repair_updates_slot_only(self, generated_test_graph):
        """Level 2 修復僅局部重設目標節點 Slot，凍結其餘節點。"""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(generated_test_graph)
        nid = list(graph.nodes.keys())[0]

        req = RepairRequest(
            node_id=nid,
            slot_name="worldview_slot",
            slot_data={"location_id": "LOC_REPAIRED"},
            changed_fields=["title"],  # cosmetic
        )
        res = coordinator.coordinate_repair(graph, req)

        assert res.success is True
        assert res.tier == RepairTier.LEVEL_2_NODE_SLOT
        assert res.affected_nodes == {nid}
        assert graph.get_story_contract(nid).worldview_slot["location_id"] == "LOC_REPAIRED"

    def test_level_3_dynamic_subgraph_commit(self, generated_test_graph):
        """Level 3 修復動態分析受波及子圖，通過 DAG 驗收並原子推進版本號。"""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(generated_test_graph)
        initial_rev = graph.graph_revision
        nid = list(graph.nodes.keys())[0]

        req = RepairRequest(
            node_id=nid,
            changed_fields=["state_mutations", "core_conflict"],
        )
        res = coordinator.coordinate_repair(graph, req)

        assert res.success is True
        assert res.tier == RepairTier.LEVEL_3_IMPACT_SUBGRAPH
        assert res.new_revision == initial_rev + 1
        assert graph.graph_revision == initial_rev + 1
        assert nid in res.affected_nodes

    def test_level_4_structural_canon_lock_guard(self, populated_story_graph):
        """Level 4 結構重構遇到已鎖定正典 STORY_CANON_LOCKED 且未授權時，必須拒絕。"""
        coordinator = LocalRepairCoordinator()
        graph = copy.deepcopy(populated_story_graph)
        # 先鎖定正典
        MasterGraphService.lock_story_canon(graph)

        nid = list(graph.nodes.keys())[0]
        req = RepairRequest(
            node_id=nid,
            tier=RepairTier.LEVEL_4_STRUCTURAL,
            structural_proposal=RepairProposal(
                operation=RepairOperation.SPLIT,
                target_nodes=[nid],
                reason="密度過載",
                detail={"turning_points": 3},
            ),
            structural_condition=GeometryRepairCondition.DENSITY_OVERLOAD,
            metadata={"allow_canon_modification": False},
        )
        res = coordinator.coordinate_repair(graph, req)

        assert res.success is False
        assert "STORY_CANON_LOCKED" in res.message
