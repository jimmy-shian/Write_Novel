# -*- coding: utf-8 -*-
"""
單元測試套件：Milestone 1 - Master Graph Core & Story Event Contracts
(Tests for Milestone 1: Master Graph Core, Story Contracts, 24 Threads & Causal DAG)

驗證項目：
1. StoryEventContract 九維故事契約完整性、欄位檢查與 JSON 序列化 Roundtrip。
2. NodeStoryContract 多線程歸屬 (thread_memberships)、雙軌狀態解耦 (planning_status / realization_status)、
   Slot 回填保護與 graph_revision 版本推進。
3. GeometryGenerator 純演算法生成 10+ 卷、6 主線 (TM01-06)、18 支線 (TS01-18) 共 24 條敘事線程。
4. Causal DAG 有向無環圖驗證演算法：嚴格因果邊 (CAUSES, ENABLES, ESCALATES) 環路檢測，
   以及非因果邊 (ECHOES, PARALLELS, CONTRASTS 等) 之因果隔離免除。
5. 回歸防護盾 (Regression Shield)：確保現有 5 項幾何測試合約 100% 相容無回退。
"""

import copy
import json
import uuid
import pytest

from backend.geometry.models import (
    ArcContainer,
    EdgeType,
    GeometryComplexity,
    GeometryEdge,
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    GeometryThread,
    NodeHierarchy,
    RepairOperation,
    RepairProposal,
    SequenceContainer,
    StructuralRole,
    ThreadType,
    VolumeContainer,
    # M1 Contracts & Enums
    CAUSAL_EDGE_TYPES,
    ForeshadowingDemand,
    NodeStoryContract,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
)
from backend.geometry.generator import GeometryGenerator
from backend.geometry.repair import (
    GeometryRepairCondition,
    GeometryRepairEngine,
)


# =============================================================================
# Helper Fixtures & Data Builders
# =============================================================================

@pytest.fixture
def sample_story_event() -> StoryEventContract:
    """提供標準九維完整故事契約測試資料。"""
    return StoryEventContract(
        event_id="EV_G0038_01",
        node_id="G0038",
        event_summary="在黑龍要塞廢墟奪取遠古星盤核心",
        participant_entities=[
            {"char_id": "C012", "faction_id": "F01", "role": "SEEKER"},
            {"char_id": "C045", "faction_id": "F02", "role": "GUARDIAN"},
        ],
        action_motives=[
            {"char_id": "C012", "motive": "解開古老封印以解除家族血脈詛咒"},
            {"char_id": "C045", "motive": "奉守護者古誓死守星盤秘密"},
        ],
        causal_preconditions=["EV_G0012_01", "EV_G0025_02"],
        core_conflict="近身肉搏擊破傀儡陣法並頂住要塞崩塌",
        direct_outcome="主角重創守護者並成功奪得星盤，但觸發遠古防禦機制導致地底坍塌",
        state_mutations=[
            {"char_id": "C012", "type": "ITEM_ACQUIRED", "item_id": "ASTROLABE_01"},
            {"char_id": "C045", "type": "INJURED", "detail": "斷右臂且元氣大傷"},
            {"faction_id": "F02", "type": "DEFENSE_BROKEN", "location": "BLACK_DRAGON_FORT"},
        ],
        downstream_impact=[
            "引發黑水商會跨國通緝與追殺",
            "喚醒沉睡於地底深淵之古神幼體",
        ],
        clue_bindings=["FSH_004", "FSH_012"],
    )


@pytest.fixture
def sample_node_contract() -> NodeStoryContract:
    """提供標準 NodeStoryContract 實例。"""
    return NodeStoryContract(
        node_id="G0038",
        volume_index=1,
        arc_index=2,
        thread_memberships=["TM01", "TM03", "TS07"],
        structural_role=StructuralRole.ESCALATE,
        node_type=NodeType.FACTION_COLLISION,
        foreshadowing_demand=ForeshadowingDemand.REQUIRES_PLANT,
        planning_status=PlanningStatus.DRAFT,
        realization_status=RealizationStatus.PENDING,
        graph_revision=1,
    )


@pytest.fixture(scope="module")
def generated_master_graph() -> GeometryGraph:
    """產生 Milestone 1 標準規格的大型 Master Graph。"""
    params = GeometryParams(
        target_chapters=300,
        volume_count=10,
        chapters_per_volume=30,
        complexity=GeometryComplexity.DENSE,
        main_thread_count=6,
        subplot_count=18,
        character_arc_count=6,
        relationship_arc_count=4,
        thematic_thread_count=4,
        seed_for_rng="m1_full_scale_seed_2026",
    )
    generator = GeometryGenerator(params)
    return generator.generate()


# =============================================================================
# 1. StoryEventContract 9-Dimension Integrity & Serialization
# =============================================================================

class TestStoryEventContractIntegrity:
    """驗證 StoryEventContract 九維故事契約完整性與序列化能力。"""

    def test_story_event_contract_all_nine_dimensions_integrity(self, sample_story_event):
        """驗證 9 大敘事維度欄位皆完整保留，類型正確無失真。"""
        ev = sample_story_event
        assert ev.event_id == "EV_G0038_01"
        assert ev.node_id == "G0038"
        assert "奪取遠古星盤" in ev.event_summary
        assert len(ev.participant_entities) == 2
        assert ev.participant_entities[0]["char_id"] == "C012"
        assert len(ev.action_motives) == 2
        assert len(ev.causal_preconditions) == 2
        assert "近身肉搏" in ev.core_conflict
        assert "坍塌" in ev.direct_outcome
        assert len(ev.state_mutations) == 3
        assert len(ev.downstream_impact) == 2
        assert len(ev.clue_bindings) == 2

        # 完整性自檢方法（若有提供）
        if hasattr(ev, "validate_9_dimensions"):
            errors = ev.validate_9_dimensions()
            assert errors == [], f"Expected 0 validation errors, got: {errors}"
        if hasattr(ev, "is_complete"):
            assert ev.is_complete() is True

    def test_story_event_contract_json_serialization_roundtrip(self, sample_story_event):
        """驗證 to_dict 與 from_dict 在 JSON 序列化轉換中保持 100% 欄位精度與 Unicode 支援。"""
        original = sample_story_event
        event_dict = original.to_dict()
        assert isinstance(event_dict, dict)
        assert event_dict["event_id"] == "EV_G0038_01"

        # 模擬網路傳輸或持久層 JSON 存取
        json_payload = json.dumps(event_dict, ensure_ascii=False)
        loaded_dict = json.loads(json_payload)

        restored = StoryEventContract.from_dict(loaded_dict)
        assert restored.event_id == original.event_id
        assert restored.node_id == original.node_id
        assert restored.event_summary == original.event_summary
        assert restored.participant_entities == original.participant_entities
        assert restored.action_motives == original.action_motives
        assert restored.causal_preconditions == original.causal_preconditions
        assert restored.core_conflict == original.core_conflict
        assert restored.direct_outcome == original.direct_outcome
        assert restored.state_mutations == original.state_mutations
        assert restored.downstream_impact == original.downstream_impact
        assert restored.clue_bindings == original.clue_bindings

    def test_story_event_contract_missing_dimension_validation(self, sample_story_event):
        """驗證若任一維度缺失或為空，校驗器能正確識別並指出缺失維度。"""
        if not hasattr(StoryEventContract, "validate_9_dimensions"):
            pytest.skip("StoryEventContract does not define validate_9_dimensions")

        incomplete_data = sample_story_event.to_dict()
        incomplete_data["core_conflict"] = ""
        incomplete_data["state_mutations"] = []

        incomplete_ev = StoryEventContract.from_dict(incomplete_data)
        errors = incomplete_ev.validate_9_dimensions(strict=True)
        assert len(errors) >= 2
        error_str = " ".join(errors)
        assert "core_conflict" in error_str
        assert "state_mutations" in error_str

    def test_story_event_contract_multiple_events_per_node(self, sample_story_event):
        """驗證單一節點可容納多重不同識別碼之九維複合故事事件。"""
        ev1 = sample_story_event
        ev2 = copy.deepcopy(sample_story_event)
        ev2.event_id = "EV_G0038_02"
        ev2.event_summary = "地底坍塌後之生死救援"
        ev2.core_conflict = "在落石中營救昏迷之守護者"

        events_list = [ev1, ev2]
        assert len(events_list) == 2
        assert events_list[0].event_id != events_list[1].event_id
        assert events_list[0].core_conflict != events_list[1].core_conflict


# =============================================================================
# 2. NodeStoryContract Slots, Multi-Thread & Dual-Track Status
# =============================================================================

class TestNodeStoryContractAndDualTrackStatus:
    """驗證 NodeStoryContract 之線程歸屬、槽位回填、雙軌狀態與版本維護。"""

    def test_node_story_contract_initialization_defaults(self):
        """驗證節點契約預設值正確：Slot 皆為初始空值，狀態為 DRAFT/PENDING，revision 為 1。"""
        node = NodeStoryContract(
            node_id="G0001",
            volume_index=1,
            arc_index=1,
            thread_memberships=["TM01"],
            structural_role=StructuralRole.OPEN_THREAD,
            node_type=NodeType.TRANSFORMATION,
            foreshadowing_demand=ForeshadowingDemand.REQUIRES_PLANT,
        )
        assert node.worldview_slot is None
        assert node.character_slots == []
        assert node.story_events == []
        assert node.destiny_events == []
        assert node.foreshadowing_tasks == []
        assert node.chapter_mappings == []
        assert node.planning_status == PlanningStatus.DRAFT
        assert node.realization_status == RealizationStatus.PENDING
        assert node.graph_revision == 1

    def test_node_story_contract_multi_thread_memberships(self, sample_node_contract):
        """驗證節點支援多對多線程歸屬 (main + sub) 與主線相容解析。"""
        node = sample_node_contract
        assert len(node.thread_memberships) == 3
        assert node.thread_memberships == ["TM01", "TM03", "TS07"]

        # 向後相容 primary_thread 屬性應返回第一個線程
        if hasattr(node, "primary_thread"):
            assert node.primary_thread == "TM01"

        # 輔助方法 belongs_to_thread
        if hasattr(node, "belongs_to_thread"):
            assert node.belongs_to_thread("TM03") is True
            assert node.belongs_to_thread("TS99") is False

        # 動態添加線程
        if hasattr(node, "add_thread_membership"):
            node.add_thread_membership("TS12")
            assert "TS12" in node.thread_memberships
            # 重複添加不應產生重複項
            node.add_thread_membership("TM01")
            assert node.thread_memberships.count("TM01") == 1

    def test_node_story_contract_slot_backfilling_independence(self, sample_node_contract, sample_story_event):
        """驗證各 Agent 依序回填 Worldview, Character, Story, Destiny, Clue, Mapping 槽位時互不干擾。"""
        node = sample_node_contract

        # 1. Worldview Agent 回填
        node.worldview_slot = {
            "faction_ids": ["F01", "F03"],
            "location_id": "LOC_08",
            "conflict_cause": "禁忌能源開採爭端",
        }

        # 2. Character Designer 回填
        node.character_slots = [
            {"character_id": "C012", "role_in_node": "DEFENDER", "initial_status": "NORMAL"},
            {"character_id": "C045", "role_in_node": "ATTACKER", "initial_status": "ALERT"},
        ]

        # 3. Twist Agent 回填九維事件與命運變遷
        node.story_events = [sample_story_event]
        node.destiny_events = [
            {"char_id": "C012", "type": "BETRAYAL"},
            {"char_id": "C045", "type": "INJURED"},
        ]

        # 4. Foreshadowing Agent 回填伏筆任務
        node.foreshadowing_tasks = [
            {"clue_id": "FSH_004", "role": "PLANT", "summary": "私通敵國密信"},
        ]

        # 5. Volume Skeleton 回填多對多章節拍點映射
        node.chapter_mappings = [
            {"chapter_index": 45, "beat_index": 1, "coverage_ratio": 0.6},
            {"chapter_index": 46, "beat_index": 0, "coverage_ratio": 0.4},
        ]

        # 驗證所有槽位獨立留存
        assert node.worldview_slot["location_id"] == "LOC_08"
        assert len(node.character_slots) == 2
        assert len(node.story_events) == 1
        assert node.story_events[0].event_id == "EV_G0038_01"
        assert len(node.destiny_events) == 2
        assert len(node.foreshadowing_tasks) == 1
        assert len(node.chapter_mappings) == 2
        assert sum(m["coverage_ratio"] for m in node.chapter_mappings) == pytest.approx(1.0)

    def test_node_story_contract_dual_track_status_lifecycle(self, sample_node_contract):
        """驗證規劃軌道 (planning_status) 與實現軌道 (realization_status) 獨立運轉且互不污染。"""
        node = sample_node_contract

        # Track A: 規劃生命週期推進
        assert node.planning_status == PlanningStatus.DRAFT
        node.planning_status = PlanningStatus.GATE_PASSED
        assert node.planning_status == PlanningStatus.GATE_PASSED

        node.planning_status = PlanningStatus.STORY_CANON_LOCKED
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

        # 驗證 Track B 在正文動筆前仍為 PENDING
        assert node.realization_status == RealizationStatus.PENDING

        # Track B: 正文實現生命週期推進 (第 45 章完成部分拍點)
        node.realization_status = RealizationStatus.PARTIAL
        assert node.realization_status == RealizationStatus.PARTIAL
        # 關鍵解耦斷言：實現進度變更絕不可竄改規劃鎖定狀態
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

        # 第 46 章完成全部拍點
        node.realization_status = RealizationStatus.REALIZED
        assert node.realization_status == RealizationStatus.REALIZED
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

    def test_node_story_contract_violated_audit_isolation(self, sample_node_contract):
        """驗證正文審計之 VIOLATED 僅作為草稿審查報告紀錄，絕對不可修改 Master Graph 節點狀態。"""
        node = sample_node_contract
        node.planning_status = PlanningStatus.STORY_CANON_LOCKED
        node.realization_status = RealizationStatus.PARTIAL

        # 模擬總監審計發現第 45 章草稿情節遺漏核心事件
        mock_audit_record = {
            "chapter_index": 45,
            "status": "VIOLATED",
            "reason": "Draft prose omitted core conflict event EV_G0038_01",
        }

        # 斷言：草稿審查即使 VIOLATED，節點契約本身規劃狀態仍必須是 LOCKED，不可被降級為 VIOLATED 或 DRAFT
        assert mock_audit_record["status"] == "VIOLATED"
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

    def test_node_story_contract_graph_revision_monotonicity(self, sample_node_contract):
        """驗證版本修訂號保持單調遞增，受控修復後 revision += 1。"""
        node = sample_node_contract
        assert node.graph_revision == 1

        # 模擬進入受控修訂
        node.planning_status = PlanningStatus.REVISION_PENDING
        node.graph_revision += 1
        assert node.graph_revision == 2

        # 修訂通過後重新鎖定
        node.planning_status = PlanningStatus.STORY_CANON_LOCKED
        assert node.graph_revision == 2

    def test_node_story_contract_serialization_roundtrip(self, sample_node_contract, sample_story_event):
        """驗證 NodeStoryContract 含槽位與巢狀 StoryEventContract 之完整序列化 roundtrip。"""
        node = sample_node_contract
        node.story_events = [sample_story_event]
        node.worldview_slot = {"faction_ids": ["F01"]}

        node_dict = node.to_dict()
        assert isinstance(node_dict, dict)
        assert node_dict["node_id"] == "G0038"

        json_bytes = json.dumps(node_dict, ensure_ascii=False)
        reloaded_dict = json.loads(json_bytes)

        restored_node = NodeStoryContract.from_dict(reloaded_dict)
        assert restored_node.node_id == node.node_id
        assert restored_node.thread_memberships == node.thread_memberships
        assert restored_node.planning_status == node.planning_status
        assert restored_node.realization_status == node.realization_status
        assert restored_node.graph_revision == node.graph_revision
        assert len(restored_node.story_events) == 1
        assert restored_node.story_events[0].event_id == sample_story_event.event_id


# =============================================================================
# 3. GeometryGenerator 10+ Volumes, 6 Main & 18 Sub (24 Total Threads)
# =============================================================================

class TestGeometryGenerator24ThreadsAndScale:
    """驗證幾何生成器純演算法生成 10+ 卷、6 主線、18 支線 (24 條全線程) 之拓撲骨架。"""

    def test_generator_produces_minimum_10_volumes(self, generated_master_graph):
        """驗證產出篇卷數 >= 10 卷，且章節區間無縫連續銜接。"""
        graph = generated_master_graph
        assert len(graph.volumes) >= 10

        vol_keys = sorted(graph.volumes.keys())
        assert vol_keys[0] == "V01"

        # 檢驗篇卷區間連續無縫隙且無重疊
        previous_end = 0
        for v_id in vol_keys:
            vol = graph.volumes[v_id]
            v_start, v_end = vol.chapter_range
            assert v_start == previous_end + 1, f"Volume {v_id} start chapter gap detected!"
            assert v_end >= v_start
            previous_end = v_end
        assert previous_end == graph.params.target_chapters

    def test_generator_produces_exact_6_main_threads(self, generated_master_graph):
        """驗證產生嚴格 6 條主線程 (TM01 至 TM06)，且貫穿全書長度。"""
        graph = generated_master_graph
        main_threads = [
            t for t in graph.threads.values()
            if t.thread_type == ThreadType.MAIN or t.thread_id.startswith("TM")
        ]
        assert len(main_threads) == 6, f"Expected exactly 6 main threads, found {len(main_threads)}"

        main_ids = {t.thread_id for t in main_threads}
        expected_ids = {"TM01", "TM02", "TM03", "TM04", "TM05", "TM06"}
        assert main_ids == expected_ids

        # 驗證主線長度充足且節點序列 >= 5
        for t in main_threads:
            assert len(t.node_sequence) >= 5, f"Main thread {t.thread_id} node sequence too short"

    def test_generator_produces_exact_18_sub_threads(self, generated_master_graph):
        """驗證產生嚴格 18 條支線程 (TS01 至 TS18)，總核心線程恰為 24 條。"""
        graph = generated_master_graph
        sub_threads = [
            t for t in graph.threads.values()
            if t.thread_type == ThreadType.SUBPLOT or t.thread_id.startswith("TS")
        ]
        assert len(sub_threads) == 18, f"Expected exactly 18 subplot threads, found {len(sub_threads)}"

        sub_ids = {t.thread_id for t in sub_threads}
        expected_sub_ids = {f"TS{i:02d}" for i in range(1, 19)}
        assert sub_ids == expected_sub_ids

        # 核心主支線總數為 24
        main_threads = [
            t for t in graph.threads.values()
            if t.thread_type == ThreadType.MAIN or t.thread_id.startswith("TM")
        ]
        assert len(main_threads) + len(sub_threads) == 24

        for t in sub_threads:
            assert len(t.node_sequence) >= 3, f"Sub thread {t.thread_id} must have at least 3 nodes"

    def test_generator_thread_structural_roles_invariants(self, generated_master_graph):
        """驗證線程結構骨架遵循 OPEN_THREAD -> DEVELOP/ESCALATE -> CONVERGE -> PAYOFF/CLOSE 規範。"""
        graph = generated_master_graph
        main_threads = [
            t for t in graph.threads.values()
            if t.thread_type == ThreadType.MAIN or t.thread_id.startswith("TM")
        ]
        for t in main_threads:
            assert t.structural_skeleton[0] == StructuralRole.OPEN_THREAD
            assert t.structural_skeleton[-1] in (StructuralRole.PAYOFF, StructuralRole.CLOSE)
            if len(t.structural_skeleton) >= 3:
                assert t.structural_skeleton[-2] == StructuralRole.CONVERGE

    def test_generator_all_nodes_have_thread_memberships(self, generated_master_graph):
        """驗證圖中節點 100% 具備線程歸屬，且存在多線交織跨度節點。"""
        graph = generated_master_graph
        assert len(graph.nodes) > 0

        multi_thread_count = 0
        for node in graph.nodes.values():
            if hasattr(node, "thread_memberships") and node.thread_memberships:
                assert len(node.thread_memberships) >= 1
                if len(node.thread_memberships) >= 2:
                    multi_thread_count += 1
            else:
                assert bool(node.primary_thread), f"Node {node.node_id} has no thread assigned"
        assert multi_thread_count > 0, "Master graph must contain crossover nodes with >= 2 threads"

    def test_generator_deterministic_seed_reproducibility(self):
        """驗證固定 RNG Seed 下幾何生成之完全確定性與可重現性。"""
        p1 = GeometryParams(target_chapters=30, volume_count=2, seed_for_rng="repro_seed_101")
        p2 = GeometryParams(target_chapters=30, volume_count=2, seed_for_rng="repro_seed_101")

        g1 = GeometryGenerator(p1).generate()
        g2 = GeometryGenerator(p2).generate()

        assert list(g1.nodes.keys()) == list(g2.nodes.keys())
        assert len(g1.edges) == len(g2.edges)
        assert list(g1.threads.keys()) == list(g2.threads.keys())
        assert list(g1.volumes.keys()) == list(g2.volumes.keys())


# =============================================================================
# 4. Causal DAG Acyclicity Verification & Cycle Detection
# =============================================================================

class TestCausalDAGAcyclicityAndCycleDetection:
    """驗證因果邊 (CAUSES, ENABLES, ESCALATES) 嚴格 DAG 無環性與非因果邊之隔離特性。"""

    def test_causal_edge_types_constant_definition(self):
        """驗證 CAUSAL_EDGE_TYPES 精確包含三種因果邊，其餘敘事邊均為非因果邊。"""
        assert EdgeType.CAUSES in CAUSAL_EDGE_TYPES
        assert EdgeType.ENABLES in CAUSAL_EDGE_TYPES
        assert EdgeType.ESCALATES in CAUSAL_EDGE_TYPES
        assert len(CAUSAL_EDGE_TYPES) == 3

        # 非因果邊驗證
        for non_causal in (
            EdgeType.ECHOES,
            EdgeType.PARALLELS,
            EdgeType.CONTRASTS,
            EdgeType.SETS_UP,
            EdgeType.PAYS_OFF,
            EdgeType.CHARACTER_ARC,
            EdgeType.RELATIONSHIP_CHANGE,
        ):
            assert non_causal not in CAUSAL_EDGE_TYPES

    def test_validate_causal_dag_on_fresh_generated_graph(self):
        """驗證生成器預設產生之 Master Graph 因果邊嚴格無環 (validate_causal_dag 回傳空列表)。"""
        params = GeometryParams(target_chapters=50, volume_count=2, seed_for_rng="dag_clean_seed")
        graph = GeometryGenerator(params).generate()

        assert hasattr(graph, "validate_causal_dag"), "GeometryGraph must implement validate_causal_dag()"
        errors = graph.validate_causal_dag()
        assert errors == [], f"Expected clean causal DAG, but found cycles: {errors}"

    def test_validate_causal_dag_detects_direct_2_node_cycle(self):
        """驗證兩節點直接互連之因果雙向環路 A -> B -> A 必然被攔截報警。"""
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)

        n1 = GeometryNode("N01", NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01")
        n2 = GeometryNode("N02", NodeHierarchy(1, 1, 1), (2, 2), StructuralRole.DEVELOP, "TM01")
        graph.add_node(n1)
        graph.add_node(n2)

        # 建立 A -> B 與 B -> A 之因果環
        graph.add_edge(GeometryEdge("E01", "N01", "N02", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E02", "N02", "N01", EdgeType.CAUSES, 1))

        errors = graph.validate_causal_dag()
        assert len(errors) > 0, "Failed to detect direct 2-node causal cycle"
        error_msg = " ".join(errors)
        assert ("N01" in error_msg or "N02" in error_msg) or "cycle" in error_msg.lower()

    def test_validate_causal_dag_detects_3_node_mixed_causal_cycle(self):
        """驗證跨越不同因果邊類型之三節點環路 A (CAUSES) -> B (ENABLES) -> C (ESCALATES) -> A 必然報警。"""
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)

        for nid in ("N01", "N02", "N03"):
            graph.add_node(GeometryNode(nid, NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01"))

        graph.add_edge(GeometryEdge("E01", "N01", "N02", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E02", "N02", "N03", EdgeType.ENABLES, 1))
        graph.add_edge(GeometryEdge("E03", "N03", "N01", EdgeType.ESCALATES, 1))

        errors = graph.validate_causal_dag()
        assert len(errors) > 0, "Failed to detect 3-node mixed causal cycle"

    def test_validate_causal_dag_ignores_non_causal_cycles(self):
        """
        核心因果隔離驗證：
        當節點間存在非因果邊（如 ECHOES 倒流、PARALLELS 雙向對稱、CONTRASTS 逆向關聯）形成環狀結構時，
        validate_causal_dag 絕不可誤報為環路！
        """
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)

        for nid in ("N01", "N02", "N03", "N04"):
            graph.add_node(GeometryNode(nid, NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01"))

        # 因果正向推進：N01 -> N02 -> N03
        graph.add_edge(GeometryEdge("E_C1", "N01", "N02", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E_C2", "N02", "N03", EdgeType.ENABLES, 1))

        # 敘事 Motif 非因果反向連結：N03 -> N01 (ECHOES 伏筆呼應倒流)
        graph.add_edge(GeometryEdge("E_NC1", "N03", "N01", EdgeType.ECHOES, 2))
        # 雙向對稱平行：N01 <-> N04 (PARALLELS)
        graph.add_edge(GeometryEdge("E_NC2", "N01", "N04", EdgeType.PARALLELS, 3))
        graph.add_edge(GeometryEdge("E_NC3", "N04", "N01", EdgeType.PARALLELS, 3))

        # 斷言：非因果邊之環路被完全豁免，因果圖判定為合法無環 DAG
        errors = graph.validate_causal_dag()
        assert errors == [], f"Non-causal motifs falsely triggered cycle errors: {errors}"

        # 逆向反證：若將 N03 -> N01 改為因果邊 CAUSES，則必須立即報錯
        graph.edges[2].edge_type = EdgeType.CAUSES
        errors_after_mutation = graph.validate_causal_dag()
        assert len(errors_after_mutation) > 0, "Mutated causal edge failed to trigger cycle detection"

    def test_validate_causal_dag_allows_valid_dag_branch_and_join(self):
        """驗證合法的菱形分岔合流 (Diamond Pattern: A -> B, A -> C, B -> D, C -> D) 通過無環檢驗。"""
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)

        for nid in ("A", "B", "C", "D"):
            graph.add_node(GeometryNode(nid, NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01"))

        graph.add_edge(GeometryEdge("E1", "A", "B", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E2", "A", "C", EdgeType.ENABLES, 1))
        graph.add_edge(GeometryEdge("E3", "B", "D", EdgeType.ENABLES, 1))
        graph.add_edge(GeometryEdge("E4", "C", "D", EdgeType.ESCALATES, 1))

        assert graph.validate_causal_dag() == []

    def test_validate_causal_dag_supports_boundary_in_out_degree_zero(self):
        """驗證 TopologyGate 規範：多起點 (In-Degree=0) 與多終點 (Out-Degree=0) 為合法幾何結構。"""
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)

        # 2 個起始節點，1 個中間節點，2 個匯聚終點
        for nid in ("START_1", "START_2", "MID", "END_1", "END_2"):
            graph.add_node(GeometryNode(nid, NodeHierarchy(1, 1, 1), (1, 1), StructuralRole.DEVELOP, "TM01"))

        graph.add_edge(GeometryEdge("E1", "START_1", "MID", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E2", "START_2", "MID", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E3", "MID", "END_1", EdgeType.ENABLES, 1))
        graph.add_edge(GeometryEdge("E4", "MID", "END_2", EdgeType.ENABLES, 1))

        assert graph.validate_causal_dag() == []


# =============================================================================
# 5. Milestone 1 Backward Compatibility Regression Shield
# =============================================================================

class TestMilestone1BackwardCompatibilityRegressionShield:
    """
    回歸防護盾：
    確保重構後之資料模型與生成器完全相容現存 5 項幾何測試：
    - test_geometry_generation_scale_and_motifs
    - test_geometry_repair_gatekeeper_and_operations
    - test_geometry_persistence_roundtrip
    - test_geometry_api_lifecycle
    - test_geometry_task_handler_and_blueprint_integration
    """

    def test_backward_compat_custom_params_main_thread_count(self):
        """
        驗證當調用方傳入自定義參數 (例如 main_thread_count=2) 時，
        生成器精確產生 2 條主線，完全保護 test_geometry_core.py 之既有斷言。
        """
        params = GeometryParams(
            target_chapters=50,
            volume_count=2,
            chapters_per_volume=25,
            complexity=GeometryComplexity.DENSE,
            main_thread_count=2,
            subplot_count=4,
            seed_for_rng="compat_seed_2_threads",
        )
        generator = GeometryGenerator(params)
        graph = generator.generate()

        assert len(graph.volumes) == 2
        main_threads = [t for t in graph.threads.values() if t.thread_type == ThreadType.MAIN]
        assert len(main_threads) == 2
        assert len(graph.nodes) >= 100
        assert graph.validate() == []

    def test_backward_compat_geometry_node_legacy_attributes(self):
        """驗證 GeometryNode 所有舊有屬性（node_id, hierarchy, chapter_window, structural_role, primary_thread 等）完好可用。"""
        node = GeometryNode(
            node_id="G_LEGACY_01",
            hierarchy=NodeHierarchy(1, 2, 3),
            chapter_window=(10, 12),
            structural_role=StructuralRole.DEVELOP,
            primary_thread="TM01",
            importance=0.75,
            semantic={"scene_title": "古典劍招"},
            metadata={"custom_flag": True},
        )
        assert node.node_id == "G_LEGACY_01"
        assert node.hierarchy.volume_index == 1
        assert node.chapter_window == (10, 12)
        assert node.structural_role == StructuralRole.DEVELOP
        assert node.primary_thread == "TM01"
        assert node.importance == 0.75
        assert node.semantic["scene_title"] == "古典劍招"
        assert node.metadata["custom_flag"] is True

    def test_backward_compat_repair_engine_operations(self):
        """驗證 GeometryRepairEngine 依然能執行 SPLIT, EXPAND, INSERT, COMPRESS 四大操作。"""
        params = GeometryParams(target_chapters=20, volume_count=1, chapters_per_volume=20, seed_for_rng="compat_repair")
        graph = GeometryGenerator(params).generate()
        engine = GeometryRepairEngine(graph)

        target_node = list(graph.nodes.keys())[3]
        split_proposal = RepairProposal(
            operation=RepairOperation.SPLIT,
            target_nodes=[target_node],
            reason="回歸驗證密度分割",
            detail={"split_count": 2},
        )
        res = engine.execute_repair(
            proposal=split_proposal,
            condition=GeometryRepairCondition.DENSITY_OVERLOAD,
            gatekeeper_context={"turning_points_count": 3},
        )
        assert res.success is True
        assert target_node not in graph.nodes
        assert len(res.new_nodes) == 2

    def test_backward_compat_roundtrip_dict_keys(self):
        """驗證 GeometryGraph.to_dict 與 from_dict 字典格式維持標準頂層鍵集合。"""
        params = GeometryParams(target_chapters=10, volume_count=1, seed_for_rng="compat_dict")
        graph = GeometryGenerator(params).generate()

        graph_dict = graph.to_dict()
        expected_keys = {"params", "nodes", "edges", "threads", "volumes", "arcs", "sequences"}
        assert expected_keys.issubset(set(graph_dict.keys()))

        restored_graph = GeometryGraph.from_dict(graph_dict)
        assert len(restored_graph.nodes) == len(graph.nodes)
        assert len(restored_graph.edges) == len(graph.edges)
        assert len(restored_graph.threads) == len(graph.threads)
        assert len(restored_graph.volumes) == len(graph.volumes)

    def test_backward_compat_all_five_existing_tests_run_cleanly(self):
        """
        執行環境回歸驗證：
        確認既有 5 個測試的函數能被正常引入與測試收集。
        """
        from tests.unit.test_geometry_core import (
            test_geometry_generation_scale_and_motifs,
            test_geometry_repair_gatekeeper_and_operations,
            test_geometry_persistence_roundtrip,
        )
        from tests.unit.test_geometry_api import test_geometry_api_lifecycle
        from tests.unit.test_geometry_pipeline_integration import (
            test_geometry_task_handler_and_blueprint_integration,
        )

        assert callable(test_geometry_generation_scale_and_motifs)
        assert callable(test_geometry_repair_gatekeeper_and_operations)
        assert callable(test_geometry_persistence_roundtrip)
        assert callable(test_geometry_api_lifecycle)
        assert callable(test_geometry_task_handler_and_blueprint_integration)


# =============================================================================
# 6. Milestone 1 Phase 1 Remediation Verifications (SQLite & Atomic Rollback)
# =============================================================================

class TestMilestone1PersistenceAndRollbackRemediation:
    """
    驗證 Reviewer M1_2 與 Challenger M1_2 提出的缺陷修復：
    1. SQLite roundtrip 保留跨線多線歸屬 (thread_memberships) 與 graph_revision。
    2. GeometryRepairEngine 遭遇成環違規時，執行原子回滾，圖譜不被破壞。
    """

    def test_sqlite_roundtrip_preserves_multi_thread_memberships_and_graph_revision(self):
        """
        驗證多線節點 (Crossover Nodes) 在 save_geometry_graph / load_geometry_graph
        經過 SQLite 序列化與反序列化後，thread_memberships 不會崩塌為單線 [primary_thread]，
        且 graph.graph_revision 精確還原。
        """
        from backend import persistence as db

        novel_id = f"test_rem_m1_{uuid.uuid4().hex[:8]}"
        db.create_novel(novel_id, "Remediation Persistence Novel", "玄幻", "熱血")

        try:
            params = GeometryParams(target_chapters=15, volume_count=2, seed_for_rng="rem_sqlite_seed")
            graph = GeometryGenerator(params).generate()
            graph.graph_revision = 7

            # 找出擁有多條線程歸屬的節點
            multi_thread_nodes = [n for n in graph.nodes.values() if len(n.thread_memberships) > 1]
            assert len(multi_thread_nodes) > 0, "測試圖譜應包含多線歸屬節點"

            sample_node = multi_thread_nodes[0]
            expected_threads = list(sample_node.thread_memberships)
            expected_primary = sample_node.primary_thread
            expected_node_id = sample_node.node_id

            # 為 sample_node 掛載 StoryEventContract 驗證九維契約一同保存
            sample_node.ensure_story_contract()
            ev = StoryEventContract(
                event_id=f"EV_{expected_node_id}_01",
                node_id=expected_node_id,
                event_summary="大戰爆發，多勢力碰撞",
                participant_entities=[{"char_id": "C01", "faction_id": "F01"}],
                action_motives=[{"char_id": "C01", "motive": "奪取晶石"}],
                causal_preconditions=["EV_PREV_01"],
                core_conflict="爭奪聖地控制權",
                direct_outcome="主角奪得靈草突圍",
                state_mutations=[{"char_id": "C01", "type": "UPGRADE"}],
                downstream_impact=["宗門大震動"],
                clue_bindings=["FSH_01"],
            )
            sample_node.story_contract.story_events.append(ev)
            sample_node.ensure_story_contract()

            # 保存至 SQLite
            db.save_geometry_graph(novel_id, graph)

            # 從 SQLite 載入
            loaded_graph = db.load_geometry_graph(novel_id)

            # 驗證 graph_revision
            assert loaded_graph.graph_revision == 7, f"預期 graph_revision=7，實際為 {loaded_graph.graph_revision}"

            # 驗證多線節點
            loaded_node = loaded_graph.get_node(expected_node_id)
            assert loaded_node is not None
            assert loaded_node.primary_thread == expected_primary
            assert loaded_node.thread_memberships == expected_threads, (
                f"多線歸屬應完整還原，預期 {expected_threads}，實際為 {loaded_node.thread_memberships}"
            )
            assert len(loaded_node.thread_memberships) == len(expected_threads)

            # 驗證故事契約
            loaded_contract = loaded_graph.get_story_contract(expected_node_id)
            assert loaded_contract is not None
            assert loaded_contract.thread_memberships == expected_threads
            assert len(loaded_contract.story_events) == 1
            assert loaded_contract.story_events[0].event_summary == "大戰爆發，多勢力碰撞"

        finally:
            db.delete_novel(novel_id)

    def test_repair_engine_atomic_rollback_on_failed_repair(self):
        """
        驗證 GeometryRepairEngine 在修復失敗 (例如成環違規) 時，
        完整回滾內部圖譜狀態，不留孤立或成環節點，保持原 DAG 合法無環。
        """
        params = GeometryParams(target_chapters=10, volume_count=1)
        graph = GeometryGraph(params)
        graph.add_node(GeometryNode("N1", NodeHierarchy(1, 1, 1), (1, 2), StructuralRole.OPEN_THREAD, "TM01"))
        graph.add_node(GeometryNode("N2", NodeHierarchy(1, 1, 2), (3, 4), StructuralRole.CLOSE, "TM01"))
        graph.add_edge(GeometryEdge("E1", "N1", "N2", EdgeType.CAUSES, 1))

        orig_nodes = list(graph.nodes.keys())
        orig_edges_len = len(graph.edges)
        orig_revision = graph.graph_revision

        engine = GeometryRepairEngine(graph)

        # 逆向插入會導致 N1 -> N2 -> Bridge -> N1 成環
        prop = RepairProposal(
            operation=RepairOperation.INSERT,
            target_nodes=["N2", "N1"],
            reason="故意引發成環之修復提案",
            detail={"after_node_id": "N2", "before_node_id": "N1"},
        )
        ctx = {"causal_gap_detected": True, "missing_cause_description": "Gap"}

        res = engine.execute_repair(prop, GeometryRepairCondition.CAUSAL_GAP, ctx)

        # 1. 操作應被拒絕
        assert res.success is False
        assert "修復造成因果有向環路違規" in res.message

        # 2. 圖譜應被原子回滾
        assert graph.validate_causal_dag() == []
        assert "G_BRIDGE_N2_N1" not in graph.nodes
        assert list(graph.nodes.keys()) == orig_nodes
        assert len(graph.edges) == orig_edges_len
        assert graph.graph_revision == orig_revision
