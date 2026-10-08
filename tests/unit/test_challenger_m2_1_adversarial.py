# -*- coding: utf-8 -*-
"""
Adversarial Empirical Verification Suite for Milestone 2:
MasterGraphService & ImpactAnalyzer Stress Testing.
File: tests/unit/test_challenger_m2_1_adversarial.py

Role: Challenger M2_1 (Empirical Adversarial Verification)

Test Coverage:
1. TestAdversarialSpoilerWall:
   - Nested secrets, future payoffs, downstream causal shielding, character destiny stripping, volume outline masking.
   - Contrast chapter_writer vs director transparency.
2. TestAdversarialTokenPruningEngine:
   - Progressive shedding across tiers 1-5 under extreme token budgets (50, 200, 500, 1000).
   - Core scene contract integrity preservation and pathological inputs handling.
3. TestAdversarialDraftPatchAndAtomicRevisionCommit:
   - Concurrency conflict detection on apply and commit.
   - Cycle detection (2-node, 3-node, self-loop) with guaranteed atomic rollback and uncorrupted revision counter.
   - Complete discard rollback restoring nodes, edges, contracts, and revisions.
4. TestAdversarialImpactAnalyzer:
   - Cosmetic fields strictly isolated to {node_id} across 50 random nodes.
   - Character fields strictly confined to current volume boundaries with zero cross-volume leakage.
   - Causal propagation strictly traversing CAUSAL_EDGE_TYPES and clue closures while never leaking across non-causal edges.
"""

import copy
import random
import pytest
from typing import Dict, Any, List, Set

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
    NodeHierarchy,
)
from backend.geometry.generator import GeometryGenerator
from backend.generation.director.master_graph_service import (
    MasterGraphService,
    DraftGraphPatch,
    estimate_tokens,
    prune_context_by_budget,
)
from backend.generation.director.impact_analyzer import (
    ImpactAnalyzer,
    classify_field,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def standard_graph_10vol() -> GeometryGraph:
    """產生標準規格 10 卷 24 線程的 Master Graph 供壓測使用。"""
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
        seed_for_rng="challenger_m2_1_seed_2026",
    )
    generator = GeometryGenerator(params)
    return generator.generate()


# =============================================================================
# 1. Adversarial Test: Spoiler Wall in MasterGraphService.project_node_context
# =============================================================================

class TestAdversarialSpoilerWall:
    """
    對 MasterGraphService.project_node_context 實施對抗性劇透滲透測試。
    """

    def test_writer_spoiler_wall_masks_100_percent_future_secrets_and_payoffs(self, standard_graph_10vol):
        """
        對抗測試：注入深層劇透、未來回收、下游因果事件、命運劇透與後續卷大綱，
        驗證 target_agent == 'chapter_writer' 時 100% 遮蔽，下游節點 100% 被 spoiler_shield 掩護。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        nid = graph.threads["TM01"].node_sequence[0]
        node = graph.get_node(nid)
        node.chapter_window = (1, 3)

        contract = node.ensure_story_contract()
        # 注入多維伏筆任務：包含當前埋設、未來回收、中間轉折
        contract.foreshadowing_tasks = [
            {
                "clue_id": "CLUE_SECRET_REVEAL",
                "role": "PLANT",
                "summary": "在書房地磚下發現帶有血跡的皇家符印",
                "future_payoff_target": "第90章主角揭發自己為先皇私生子並引發皇城政變",
                "secret_core_truth": "先皇為魔族後裔，私生子背負滅世詛咒",
                "payoff_chapter": 90,
                "payoff_node_id": "NODE_FUTURE_90",
            },
            {
                "clue_id": "CLUE_FUTURE_PAYOFF_OUT_OF_BOUNDS",
                "role": "PAYOFF",
                "chapter_index": 75,  # 遠超當前視窗 (1, 3)
                "summary": "解開古代星圖終極秘密",
            },
            {
                "clue_id": "CLUE_FUTURE_TURN_OUT_OF_BOUNDS",
                "role": "TURN",
                "chapter_index": 45,  # 遠超當前視窗
                "summary": "盟友在邊境要塞倒戈",
            },
            {
                "clue_id": "CLUE_CURRENT_PAYOFF",
                "role": "PAYOFF",
                "chapter_index": 2,  # 落在當前視窗 (1, 3)
                "summary": "確認刺客為近衛軍所偽裝",
            },
        ]

        # 注入角色未來命運劇透
        contract.character_slots = [
            {
                "character_id": "CHAR_PRINCE",
                "name": "艾德溫皇子",
                "role_in_node": "PROTAGONIST",
                "initial_status": "NORMAL",
                "future_destiny": "在第7卷被至親背叛慘死於雪原",
                "ultimate_fate": "DEAD",
            }
        ]

        # 注入下游因果後繼節點的重大事件與轉折
        causal_succs = graph.get_causal_successors(nid)
        assert len(causal_succs) > 0, "節點必須具有下游因果後繼以測試劇透牆"
        for s_id in causal_succs:
            s_node = graph.get_node(s_id)
            s_contract = s_node.ensure_story_contract()
            s_contract.story_events = [
                StoryEventContract(
                    event_id=f"EV_SPOILER_{s_id}",
                    node_id=s_id,
                    event_summary="大主教發動血祭弒君篡位",
                    participant_entities=[{"char_id": "CHAR_BISHOP", "role": "USURPER"}],
                    action_motives=[{"char_id": "CHAR_BISHOP", "motive": "奪取聖骸"}],
                    causal_preconditions=[],
                    core_conflict="聖堂喋血奪權",
                    direct_outcome="國王駕崩，全城戒嚴",
                    state_mutations=[{"char_id": "CHAR_KING", "type": "DEATH"}],
                    downstream_impact=["帝國崩解"],
                    clue_bindings=[],
                )
            ]

        # 執行 Chapter Writer 作用域投影
        proj = MasterGraphService.project_node_context(graph, nid, target_agent="chapter_writer")

        # 1. 驗證防劇透標記
        assert proj["spoiler_wall_active"] is True
        assert proj["target_agent"] == "chapter_writer"

        # 2. 驗證後續卷大綱遮蔽
        assert proj["volume_context"]["subsequent_volumes"] == "[PROTECTED_BY_SPOILER_WALL]"
        assert "all_volumes" not in proj["volume_context"]

        # 3. 驗證伏筆任務防劇透：
        tasks = proj["current_scene_contract"]["foreshadowing_tasks"]
        plant_tasks = [t for t in tasks if t.get("role") == "PLANT"]
        assert len(plant_tasks) == 1
        pt = plant_tasks[0]
        assert pt["future_payoff_target"] == "[SPOILER_PROTECTED_FUTURE_PAYOFF]"
        assert "secret_core_truth" not in pt, "secret_core_truth 必須被完全剔除"
        assert "payoff_chapter" not in pt, "payoff_chapter 必須被完全剔除"
        assert "payoff_node_id" not in pt, "payoff_node_id 必須被完全剔除"

        # 未到期的 PAYOFF 與 TURN 任務必須 100% 遮蔽 (不得存在於列表中)
        payoff_out = [t for t in tasks if t.get("clue_id") == "CLUE_FUTURE_PAYOFF_OUT_OF_BOUNDS"]
        turn_out = [t for t in tasks if t.get("clue_id") == "CLUE_FUTURE_TURN_OUT_OF_BOUNDS"]
        assert len(payoff_out) == 0, "超出當前章節的未到期 PAYOFF 任務不得暴露給 Writer"
        assert len(turn_out) == 0, "超出當前章節的未到期 TURN 任務不得暴露給 Writer"

        # 當前章節的 PAYOFF 任務應正常放行
        payoff_in = [t for t in tasks if t.get("clue_id") == "CLUE_CURRENT_PAYOFF"]
        assert len(payoff_in) == 1, "當前章節視窗內的 PAYOFF 任務必須正常放行"

        # 4. 驗證角色去命運化
        chars = proj["current_scene_contract"]["participating_characters"]
        assert len(chars) == 1
        ch = chars[0]
        assert "future_destiny" not in ch, "future_destiny 必須被剔除"
        assert "ultimate_fate" not in ch, "ultimate_fate 必須被剔除"
        assert ch["character_id"] == "CHAR_PRINCE"

        # 5. 驗證下游因果節點 100% 具備 spoiler_shield，且絕無劇情細節洩露
        downstream = proj["downstream_trajectory"]
        assert len(downstream) == len(causal_succs)
        for succ in downstream:
            assert "spoiler_shield" in succ
            assert "SPOILER_WALL_ACTIVE" in succ["spoiler_shield"]
            assert "event_summaries" not in succ, "不得洩露下游事件摘要"
            assert "core_conflicts" not in succ, "不得洩露下游核心衝突"
            assert "outcomes" not in succ, "不得洩露下游結果"

    def test_writer_alias_and_case_insensitivity(self, standard_graph_10vol):
        """測試不同形式的 writer 調用者字串 (大小寫、空白、別名) 皆能正確啟用劇透牆。"""
        graph = standard_graph_10vol
        nid = graph.threads["TM01"].node_sequence[0]

        for writer_alias in ["chapter_writer", "CHAPTER_WRITER", "writer", "  Writer  "]:
            proj = MasterGraphService.project_node_context(graph, nid, target_agent=writer_alias)
            assert proj["spoiler_wall_active"] is True
            assert proj["volume_context"]["subsequent_volumes"] == "[PROTECTED_BY_SPOILER_WALL]"

    def test_director_full_transparency_contrast(self, standard_graph_10vol):
        """
        對照測試：相同節點注入劇透資料後，針對 target_agent == 'director'
        必須提供 100% 透明度：暴露全卷大綱、保留未來真相、暴露下游事件。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        nid = graph.threads["TM01"].node_sequence[0]
        node = graph.get_node(nid)

        contract = node.ensure_story_contract()
        contract.foreshadowing_tasks = [
            {
                "clue_id": "CLUE_SECRET_DIRECTOR",
                "role": "PLANT",
                "summary": "埋下線索",
                "future_payoff_target": "第90章終極反轉",
                "secret_core_truth": "關鍵真相保留給總監",
                "payoff_chapter": 90,
            },
            {
                "clue_id": "CLUE_FAR_PAYOFF",
                "role": "PAYOFF",
                "chapter_index": 85,
                "summary": "遠程回收",
            }
        ]
        contract.character_slots = [
            {
                "character_id": "CHAR_01",
                "future_destiny": "終局陣亡",
                "ultimate_fate": "DEAD",
            }
        ]

        causal_succs = graph.get_causal_successors(nid)
        for s_id in causal_succs:
            s_node = graph.get_node(s_id)
            s_contract = s_node.ensure_story_contract()
            s_contract.story_events = [
                StoryEventContract(
                    event_id=f"EV_DIR_{s_id}",
                    node_id=s_id,
                    event_summary="總監可見之重大劇情",
                    participant_entities=[],
                    action_motives=[],
                    causal_preconditions=[],
                    core_conflict="衝突",
                    direct_outcome="結果",
                    state_mutations=[],
                    downstream_impact=[],
                    clue_bindings=[],
                )
            ]

        # 執行 Director 投影
        proj = MasterGraphService.project_node_context(graph, nid, target_agent="director")

        assert proj["spoiler_wall_active"] is False
        assert "subsequent_volumes" not in proj["volume_context"]
        assert "all_volumes" in proj["volume_context"]
        assert len(proj["volume_context"]["all_volumes"]) == 10

        tasks = proj["current_scene_contract"]["foreshadowing_tasks"]
        pt = [t for t in tasks if t.get("role") == "PLANT"][0]
        assert pt["secret_core_truth"] == "關鍵真相保留給總監"
        assert pt["payoff_chapter"] == 90

        payoffs = [t for t in tasks if t.get("role") == "PAYOFF"]
        assert len(payoffs) == 1
        assert payoffs[0]["chapter_index"] == 85

        chars = proj["current_scene_contract"]["participating_characters"]
        assert chars[0]["future_destiny"] == "終局陣亡"
        assert chars[0]["ultimate_fate"] == "DEAD"

        for succ in proj["downstream_trajectory"]:
            assert "spoiler_shield" not in succ
            assert "event_summaries" in succ
            assert "總監可見之重大劇情" in succ["event_summaries"]


# =============================================================================
# 2. Adversarial Test: Token Pruning Engine
# =============================================================================

class TestAdversarialTokenPruningEngine:
    """
    對 Token Pruning Engine 實施極端預算與大上下文剪裁壓測。
    """

    @pytest.fixture
    def bloated_context(self) -> Dict[str, Any]:
        """建立超大膨脹上下文 (預估 3000+ tokens)。"""
        return {
            "target_agent": "chapter_writer",
            "node_id": "NODE_TEST_BLOATED",
            "remote_connections": [
                {"edge_id": f"REMOTE_EDGE_{i}", "target": f"NODE_FAR_{i}", "type": "ECHOES", "theme": "主題回響"*10}
                for i in range(30)
            ],
            "upstream_predecessors": [
                {
                    "node_id": f"PRED_NODE_{i}",
                    "outcomes": [f"詳細前置結果描寫：在要塞防禦戰中殲滅第 {i} 軍團並奪得軍旗，俘獲副將三人" * 5 for _ in range(3)],
                    "state_mutations": [{"char_id": f"C_{i}", "type": "LEVEL_UP", "detail": "突破境界"*4} for _ in range(5)],
                }
                for i in range(10)
            ],
            "current_scene_contract": {
                "participating_characters": [
                    {
                        "character_id": f"CHAR_{i:02d}",
                        "name": f"重要角色_{i}",
                        "role_in_node": "PARTICIPANT",
                        "initial_status": "NORMAL",
                        "backstory": "悠久的古老血統，傳承自上古守護者家族，經歷三次世界大戰與三次大遷徙" * 3,
                        "appearance": "身穿玄黑重鎧，手持符文長槍，面容冷峻如霜" * 2,
                        "equipment": ["符文長槍", "霜月重盾", "疾風之靴"],
                    }
                    for i in range(20)
                ],
                "story_events": [
                    {
                        "event_id": f"EV_CORE_{i}",
                        "node_id": "NODE_TEST_BLOATED",
                        "event_summary": f"核心事件 {i}：正面迎戰魔潮首領並釋放封印之力",
                        "participant_entities": [{"char_id": "CHAR_01", "role": "FIGHTER"}],
                        "action_motives": [{"char_id": "CHAR_01", "motive": "為守護後方難民營不惜燃燒生命本源" * 4}],
                        "core_conflict": "正面對抗湮滅級魔潮首領",
                        "direct_outcome": "重創首領，但護城大陣能源核心碎裂",
                        "state_mutations": [{"char_id": "CHAR_01", "type": "INJURED", "severity": "CRITICAL"}],
                        "downstream_impact": ["引發全城恐慌，邊境防線全面告急，援軍受阻於暴風峽谷" * 4],
                        "clue_bindings": ["CLUE_01"],
                    }
                    for i in range(3)
                ],
            },
        }

    def test_progressive_pruning_tiers_1_to_5_shedding(self, bloated_context):
        """
        階梯式預算壓測：
        驗證預算由寬鬆至極端緊縮時，剪裁引擎依序啟用 Tier 1 至 Tier 5，
        且每層精確剔除對應次要欄位。
        """
        initial_tokens = estimate_tokens(bloated_context)
        assert initial_tokens > 1500, f"膨脹上下文 token 應超過 1500，實際為 {initial_tokens}"

        # 1. 充足預算 -> 0 剪裁
        pruned_ample, tiers_ample = prune_context_by_budget(bloated_context, token_budget=initial_tokens + 500)
        assert len(tiers_ample) == 0
        assert "remote_connections" in pruned_ample

        # 2. 略低預算 -> Tier 1 剪裁 (移除 remote_connections)
        pruned_t1, tiers_t1 = prune_context_by_budget(bloated_context, token_budget=initial_tokens - 150)
        assert "TIER_1_PRUNE_REMOTE_LINKS" in tiers_t1
        assert "remote_connections" not in pruned_t1

        # 3. 中等預算 -> Tier 1 + Tier 2 (前置節點壓縮至最近 2 個)
        pruned_t2, tiers_t2 = prune_context_by_budget(bloated_context, token_budget=900)
        assert "TIER_2_PRUNE_DISTANT_ANCESTORS" in tiers_t2
        assert len(pruned_t2["upstream_predecessors"]) <= 2

        # 4. 緊縮預算 -> Tier 1 + Tier 2 + Tier 3 (角色精簡背景/外觀，保留 4 個核心欄位)
        pruned_t3, tiers_t3 = prune_context_by_budget(bloated_context, token_budget=500)
        assert "TIER_3_CONDENSE_CHARACTERS" in tiers_t3
        for ch in pruned_t3["current_scene_contract"]["participating_characters"]:
            assert "backstory" not in ch
            assert "appearance" not in ch
            assert "character_id" in ch
            assert "role_in_node" in ch

        # 5. 極限預算 50 tokens -> Tier 1 至 Tier 5 全面啟用
        pruned_extreme, tiers_extreme = prune_context_by_budget(bloated_context, token_budget=50)
        assert "TIER_1_PRUNE_REMOTE_LINKS" in tiers_extreme
        assert "TIER_2_PRUNE_DISTANT_ANCESTORS" in tiers_extreme
        assert "TIER_3_CONDENSE_CHARACTERS" in tiers_extreme
        assert "TIER_4_CONDENSE_PREDECESSORS" in tiers_extreme
        assert "TIER_5_CONDENSE_SECONDARY_EVENT_FIELDS" in tiers_extreme

        # 驗證 Tier 5 剔除了次要事件欄位
        for ev in pruned_extreme["current_scene_contract"]["story_events"]:
            assert "action_motives" not in ev, "action_motives 必須在 Tier 5 被剪裁"
            assert "downstream_impact" not in ev, "downstream_impact 必須在 Tier 5 被剪裁"
            # 核心衝突與結果必須保留！
            assert "core_conflict" in ev
            assert "direct_outcome" in ev
            assert "event_summary" in ev

    def test_extreme_and_pathological_token_budgets_no_crash(self, bloated_context):
        """
        病態與邊界預算壓測：
        傳入 50, 10, 1, 0, -500 等極端邊界預算，驗證系統安全降級而不拋出未處理異常。
        """
        for weird_budget in [50, 200, 500, 1000, 10, 1, 0, -100]:
            pruned, tiers = prune_context_by_budget(bloated_context, token_budget=weird_budget)
            assert isinstance(pruned, dict)
            assert isinstance(tiers, list)
            # 確保核心結構完整不損壞
            assert "current_scene_contract" in pruned
            assert "story_events" in pruned["current_scene_contract"]
            assert len(pruned["current_scene_contract"]["story_events"]) == 3

    def test_project_node_context_integration_with_extreme_budgets(self, standard_graph_10vol):
        """透過 MasterGraphService.project_node_context 端到端整合極端預算。"""
        graph = standard_graph_10vol
        nid = graph.threads["TM01"].node_sequence[0]

        for budget in [50, 150, 300, 800, 1500]:
            proj = MasterGraphService.project_node_context(
                graph, nid, target_agent="chapter_writer", token_budget=budget
            )
            assert "token_metrics" in proj
            metrics = proj["token_metrics"]
            assert metrics["token_budget"] == budget
            assert "initial_tokens" in metrics
            assert "final_tokens" in metrics
            if metrics["initial_tokens"] > budget:
                assert metrics["pruned"] is True
                assert len(metrics["pruning_tiers_applied"]) > 0


# =============================================================================
# 3. Adversarial Test: Draft Patch Staging & Atomic Revision Commit
# =============================================================================

class TestAdversarialDraftPatchAndAtomicRevisionCommit:
    """
    對 DraftGraphPatch 與 MasterGraphService 提交/回滾機制實施並發衝突、環路注入與原子回滾壓測。
    """

    def test_concurrency_conflict_on_apply_fails_cleanly(self, standard_graph_10vol):
        """
        並發衝突對抗：在 apply 時 base_revision != graph.graph_revision 必須立即失敗。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        nid = list(graph.nodes.keys())[0]

        patch = MasterGraphService.create_draft_patch(graph)
        # 人為製造主圖已被其他任務推進版本號
        graph.graph_revision = 99

        patch.stage_worldview_slot(nid, {"location_id": "LOC_CONFLICT"})

        with pytest.raises(ValueError, match="Concurrency conflict"):
            MasterGraphService.apply_draft_patch(graph, patch)

        assert patch.status == "PENDING"
        assert (graph.nodes[nid].semantic or {}).get("location_id") != "LOC_CONFLICT"

    def test_concurrency_conflict_on_commit_discards_and_rolls_back(self, standard_graph_10vol):
        """
        並發衝突對抗：在 apply 成功後、commit 之前，若主圖版本號被突變，
        commit 必須捕獲並發失敗，呼叫 discard 回滾，並維持主圖乾淨。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        nid = list(graph.nodes.keys())[0]
        orig_location = (graph.nodes[nid].semantic or {}).get("location_id")

        patch = MasterGraphService.create_draft_patch(graph)
        patch.stage_worldview_slot(nid, {"location_id": "LOC_MUTATED_BEFORE_COMMIT"})

        MasterGraphService.apply_draft_patch(graph, patch)
        assert patch.status == "APPLIED"

        # 模擬外界並發操作推進主圖版本號
        graph.graph_revision += 5

        with pytest.raises(ValueError, match="Optimistic concurrency check failed"):
            MasterGraphService.commit_draft_patch(graph, patch)

        assert patch.status == "DISCARDED"
        # 驗證主圖節點狀態已回滾至快照，無殘留改動
        assert (graph.nodes[nid].semantic or {}).get("location_id") == orig_location

    def test_cycle_detection_and_clean_rollback_2_node_cycle(self, standard_graph_10vol):
        """
        環路注入對抗 (2-Node Cycle)：
        在補丁中注入反向因果邊 (v -> u)，commit 必須偵測 Kahn DAG 缺陷，
        拋出 ValueError，並保證主圖完全回滾、版本號不遞增、邊與節點無殘留。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        initial_rev = graph.graph_revision
        initial_edge_count = len(graph.edges)

        # 尋找一條既有的因果邊 u -> v
        causal_edge = [e for e in graph.edges if e.edge_type in CAUSAL_EDGE_TYPES][0]
        u, v = causal_edge.source, causal_edge.target

        patch = MasterGraphService.create_draft_patch(graph)
        # 注入反向因果邊 v -> u
        patch.edge_additions.append(MasterGraphEdgeContract(
            edge_id="EDGE_CYC_2NODE",
            source_id=v,
            target_id=u,
            edge_type=EdgeType.CAUSES,
        ))
        # 同步注入一個槽位改動
        patch.stage_worldview_slot(u, {"conflict_cause": "受環路污染的衝突"})

        with pytest.raises(ValueError, match="Causal DAG validation failed"):
            MasterGraphService.commit_draft_patch(graph, patch)

        # 驗證完全回滾
        assert patch.status == "DISCARDED"
        assert graph.graph_revision == initial_rev, "版本號絕對不得遞增"
        assert len(graph.edges) == initial_edge_count, "污染邊絕對不得殘留在 graph.edges"
        assert not any(e.edge_id == "EDGE_CYC_2NODE" for e in graph.edges)
        assert (graph.nodes[u].semantic or {}).get("conflict_cause") != "受環路污染的衝突", "節點槽位必須完全回滾"

    def test_cycle_detection_and_clean_rollback_3_node_cycle(self, standard_graph_10vol):
        """
        環路注入對抗 (3-Node Cycle)：
        構建 u -> v -> w -> u 跨 3 節點因果環路，測試複雜環路檢測與乾淨回滾。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        initial_rev = graph.graph_revision
        initial_edges = copy.deepcopy(graph.edges)

        node_ids = list(graph.nodes.keys())[:3]
        n1, n2, n3 = node_ids[0], node_ids[1], node_ids[2]

        patch = MasterGraphService.create_draft_patch(graph)
        patch.edge_additions.extend([
            MasterGraphEdgeContract(edge_id="E_3N_1", source_id=n1, target_id=n2, edge_type=EdgeType.ENABLES),
            MasterGraphEdgeContract(edge_id="E_3N_2", source_id=n2, target_id=n3, edge_type=EdgeType.ESCALATES),
            MasterGraphEdgeContract(edge_id="E_3N_3", source_id=n3, target_id=n1, edge_type=EdgeType.CAUSES),
        ])

        with pytest.raises(ValueError, match="Causal DAG validation failed"):
            MasterGraphService.commit_draft_patch(graph, patch)

        assert patch.status == "DISCARDED"
        assert graph.graph_revision == initial_rev
        assert len(graph.edges) == len(initial_edges)
        assert not any(e.edge_id in ("E_3N_1", "E_3N_2", "E_3N_3") for e in graph.edges)

    def test_cycle_detection_and_clean_rollback_self_loop(self, standard_graph_10vol):
        """環路注入對抗：單節點自環 (Self-loop) 因果邊。"""
        graph = copy.deepcopy(standard_graph_10vol)
        initial_rev = graph.graph_revision
        nid = list(graph.nodes.keys())[0]

        patch = MasterGraphService.create_draft_patch(graph)
        patch.edge_additions.append(MasterGraphEdgeContract(
            edge_id="EDGE_SELF_LOOP",
            source_id=nid,
            target_id=nid,
            edge_type=EdgeType.CAUSES,
        ))

        with pytest.raises(ValueError, match="Causal DAG validation failed"):
            MasterGraphService.commit_draft_patch(graph, patch)

        assert patch.status == "DISCARDED"
        assert graph.graph_revision == initial_rev
        assert not any(e.edge_id == "EDGE_SELF_LOOP" for e in graph.edges)

    def test_discard_draft_patch_cleanly_restores_complete_snapshot(self, standard_graph_10vol):
        """
        全面回滾測試：
        在補丁中同時執行節點新增、節點刪除、槽位修改、邊新增、邊刪除，
        隨後調用 discard_draft_patch，驗證主圖所有字典與列表 100% 恢復初始快照。
        """
        graph = copy.deepcopy(standard_graph_10vol)
        initial_node_count = len(graph.nodes)
        initial_edge_count = len(graph.edges)
        initial_rev = graph.graph_revision

        existing_nid = list(graph.nodes.keys())[0]
        deleted_nid = list(graph.nodes.keys())[1]

        patch = MasterGraphService.create_draft_patch(graph)

        # 1. 新增節點
        new_node_contract = NodeStoryContract(
            node_id="NODE_TEMPORARY_ADDED",
            volume_index=1,
            arc_index=1,
            thread_memberships=["TM01"],
            structural_role="DEVELOP",
            node_type="CRISIS",
            foreshadowing_demand="NONE",
        )
        patch.node_additions["NODE_TEMPORARY_ADDED"] = new_node_contract

        # 2. 修改槽位
        patch.stage_worldview_slot(existing_nid, {"location_id": "LOC_TMP_STAGED"})

        # 3. 刪除節點
        patch.node_deletions.append(deleted_nid)

        # 4. 新增邊
        patch.edge_additions.append(MasterGraphEdgeContract(
            edge_id="EDGE_TMP_ADDED",
            source_id=existing_nid,
            target_id="NODE_TEMPORARY_ADDED",
            edge_type=EdgeType.ENABLES,
        ))

        # 套用補丁
        MasterGraphService.apply_draft_patch(graph, patch)
        assert patch.status == "APPLIED"
        assert "NODE_TEMPORARY_ADDED" in graph.nodes
        assert deleted_nid not in graph.nodes

        # 放棄並回滾
        MasterGraphService.discard_draft_patch(patch, graph)
        assert patch.status == "DISCARDED"

        # 驗證恢復完全一致性
        assert "NODE_TEMPORARY_ADDED" not in graph.nodes
        assert deleted_nid in graph.nodes
        assert len(graph.nodes) == initial_node_count
        assert len(graph.edges) == initial_edge_count
        assert graph.graph_revision == initial_rev
        assert not any(e.edge_id == "EDGE_TMP_ADDED" for e in graph.edges)


# =============================================================================
# 4. Adversarial Test: ImpactAnalyzer.analyze_node_impact
# =============================================================================

class TestAdversarialImpactAnalyzer:
    """
    對 ImpactAnalyzer.analyze_node_impact 實施依賴邊界滲透測試。
    """

    def test_cosmetic_fields_strictly_isolated_across_50_random_nodes(self, standard_graph_10vol):
        """
        外觀欄位隔離對抗測試：
        在全圖 10 卷隨機抽樣 50 個節點，針對 title, description, surface_text, style, tone 等外觀欄位，
        100% 驗證其受影響集合嚴格恆等於 {node_id}，絕不波及第二個節點。
        """
        analyzer = ImpactAnalyzer()
        all_node_ids = list(standard_graph_10vol.nodes.keys())
        random.seed(20261008)
        sampled_node_ids = random.sample(all_node_ids, min(50, len(all_node_ids)))

        cosmetic_combinations = [
            ["title"],
            ["description"],
            ["surface_text"],
            ["title", "description"],
            ["title", "surface_text", "atmosphere", "style", "tone"],
        ]

        for idx, nid in enumerate(sampled_node_ids):
            fields = cosmetic_combinations[idx % len(cosmetic_combinations)]
            impact = analyzer.analyze_node_impact(standard_graph_10vol, nid, fields)
            assert impact == {nid}, (
                f"節點 {nid} 在外觀欄位 {fields} 下返回了非預期受影響節點: {impact - {nid}}"
            )

    def test_character_fields_never_leak_across_volume_boundaries(self, standard_graph_10vol):
        """
        角色跨卷洩漏對抗測試：
        注入全域角色 CHAR_CROSS_VOL 到第 1 卷、第 2 卷、第 3 卷、第 5 卷的多個節點。
        當針對第 2 卷的某個節點變更 character_slots 或 appearance 時：
        1. 波及第 2 卷內所有登場同角色的場景節點。
        2. 0% 洩漏至第 1 卷、第 3 卷、第 5 卷！
        """
        graph = copy.deepcopy(standard_graph_10vol)
        analyzer = ImpactAnalyzer()

        target_char_id = "CHAR_CROSS_VOL"

        # 分配到多卷
        vol_node_map: Dict[int, List[str]] = {1: [], 2: [], 3: [], 5: []}
        for nid, node in graph.nodes.items():
            vol = node.hierarchy.volume_index if node.hierarchy else 1
            if vol in vol_node_map and len(vol_node_map[vol]) < 3:
                vol_node_map[vol].append(nid)
                contract = node.ensure_story_contract()
                contract.character_slots.append({
                    "character_id": target_char_id,
                    "name": "跨卷傳奇角色",
                    "role_in_node": "CAMEO",
                })

        # 確保每卷都注入了節點
        for v, nodes in vol_node_map.items():
            assert len(nodes) >= 2, f"第 {v} 卷必須至少注入 2 個測試節點"

        # 選定第 2 卷的第一個節點進行角色屬性修改
        target_node_id = vol_node_map[2][0]
        impact = analyzer.analyze_node_impact(
            graph, target_node_id, ["character_slots", "appearance", "voice"]
        )

        assert target_node_id in impact
        # 驗證第 2 卷內其他登場同角色的節點皆被波及
        for other_v2_node in vol_node_map[2]:
            assert other_v2_node in impact, f"第 2 卷內角色節點 {other_v2_node} 應在影響集合中"

        # 嚴格驗證：集合中所有節點的 volume_index 必須全部 == 2，絕無跨卷滲漏！
        for affected_nid in impact:
            affected_node = graph.get_node(affected_nid)
            vol_idx = affected_node.hierarchy.volume_index if affected_node.hierarchy else 1
            assert vol_idx == 2, (
                f"角色屬性變更洩漏出了卷邊界！節點 {affected_nid} 屬於第 {vol_idx} 卷，非目標第 2 卷"
            )

        # 明確反向斷言：第 1, 3, 5 卷的同角色節點絕不在 impact 中
        for cross_vol in [1, 3, 5]:
            for cross_nid in vol_node_map[cross_vol]:
                assert cross_nid not in impact, (
                    f"第 {cross_vol} 卷節點 {cross_nid} 不應被第 2 卷的角色變更波及"
                )

    def test_causal_fields_propagate_along_causal_edges_and_clues_never_non_causal(self):
        """
        因果邊與非因果邊隔離對抗測試 (Synthetic Topological Challenge)：
        構建複合拓撲網絡：
        - 因果鏈：N0 -(CAUSES)-> N1 -(ENABLES)-> N2 -(ESCALATES)-> N3
        - 非因果邊：
            N0 -(ECHOES)-> NC1
            N0 -(PARALLELS)-> NC2
            N0 -(CONTRASTS)-> NC3
            N0 -(SETS_UP)-> NC4
            N0 -(RELATIONSHIP_CHANGE)-> NC5
            N1 -(ECHOES)-> NC6
            N2 -(PARALLELS)-> NC7
        - 伏筆線索閉環：
            N2 包含線索 CLUE_ALPHA
            無因果可達之節點 CL_A 包含線索 CLUE_ALPHA
            CL_A -(CAUSES)-> CL_B (因果後繼)
            CL_A -(ECHOES)-> NC8 (非因果後繼)
        變更 N0 的因果欄位 (state_mutations, core_conflict) 時：
        1. 必須涵蓋因果下游 {N0, N1, N2, N3}
        2. 必須涵蓋伏筆閉環傳遞下游 {CL_A, CL_B}
        3. 絕不得涵蓋非因果邊節點 {NC1, NC2, NC3, NC4, NC5, NC6, NC7, NC8}！
        """
        graph = GeometryGraph(
            params=GeometryParams(volume_count=1),
        )

        all_node_names = [
            "N0", "N1", "N2", "N3",
            "NC1", "NC2", "NC3", "NC4", "NC5", "NC6", "NC7", "NC8",
            "CL_A", "CL_B"
        ]
        for name in all_node_names:
            graph.add_node(GeometryNode(
                node_id=name,
                hierarchy=NodeHierarchy(volume_index=1, arc_index=1, sequence_index=1),
                chapter_window=(1, 1),
                structural_role=StructuralRole.DEVELOP,
                primary_thread="TM01",
            ))

        # 建立因果鏈
        graph.add_edge(GeometryEdge("E_C1", "N0", "N1", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E_C2", "N1", "N2", EdgeType.ENABLES, 1))
        graph.add_edge(GeometryEdge("E_C3", "N2", "N3", EdgeType.ESCALATES, 1))

        # 建立非因果邊
        graph.add_edge(GeometryEdge("E_NC1", "N0", "NC1", EdgeType.ECHOES, 1))
        graph.add_edge(GeometryEdge("E_NC2", "N0", "NC2", EdgeType.PARALLELS, 1))
        graph.add_edge(GeometryEdge("E_NC3", "N0", "NC3", EdgeType.CONTRASTS, 1))
        graph.add_edge(GeometryEdge("E_NC4", "N0", "NC4", EdgeType.SETS_UP, 1))
        graph.add_edge(GeometryEdge("E_NC5", "N0", "NC5", EdgeType.RELATIONSHIP_CHANGE, 1))
        graph.add_edge(GeometryEdge("E_NC6", "N1", "NC6", EdgeType.ECHOES, 1))
        graph.add_edge(GeometryEdge("E_NC7", "N2", "NC7", EdgeType.PARALLELS, 1))

        # 建立伏筆綁定
        c_n2 = graph.nodes["N2"].ensure_story_contract()
        c_n2.foreshadowing_tasks.append({"clue_id": "CLUE_ALPHA", "role": "TURN"})

        c_cla = graph.nodes["CL_A"].ensure_story_contract()
        c_cla.foreshadowing_tasks.append({"clue_id": "CLUE_ALPHA", "role": "PAYOFF"})

        # CL_A 下游
        graph.add_edge(GeometryEdge("E_CL_CAUSAL", "CL_A", "CL_B", EdgeType.CAUSES, 1))
        graph.add_edge(GeometryEdge("E_CL_NONCAUSAL", "CL_A", "NC8", EdgeType.ECHOES, 1))

        analyzer = ImpactAnalyzer()
        impact = analyzer.analyze_node_impact(
            graph, "N0", ["state_mutations", "core_conflict", "direct_outcome"]
        )

        # 1. 驗證因果後繼被包含
        expected_causal = {"N0", "N1", "N2", "N3"}
        assert expected_causal.issubset(impact), f"遺漏因果後繼節點: {expected_causal - impact}"

        # 2. 驗證伏筆線索閉環被包含
        expected_clue = {"CL_A", "CL_B"}
        assert expected_clue.issubset(impact), f"遺漏伏筆閉環節點: {expected_clue - impact}"

        # 3. 嚴格驗證非因果邊 0% 滲透
        non_causal_nodes = {"NC1", "NC2", "NC3", "NC4", "NC5", "NC6", "NC7", "NC8"}
        leaked_nodes = non_causal_nodes.intersection(impact)
        assert len(leaked_nodes) == 0, (
            f"因果影響分析非法穿透非因果邊！滲漏節點: {leaked_nodes}"
        )

    def test_transitive_clue_bindings_closure(self):
        """
        傳遞性伏筆線索閉環對抗測試：
        N_START -(CAUSES)-> N_CLUE1 [CLUE_1]
        ... 跨線程遠端節點 N_REMOTE1 [CLUE_1, CLUE_2]
        ... 跨線程遠端節點 N_REMOTE2 [CLUE_2]
        驗證傳遞閉包演算法能夠透過 CLUE_1 -> N_REMOTE1 -> CLUE_2 -> N_REMOTE2 連鎖閉環。
        """
        graph = GeometryGraph(params=GeometryParams(volume_count=1))
        for nid in ["N_START", "N_CLUE1", "N_REMOTE1", "N_REMOTE2", "N_ISOLATED"]:
            graph.add_node(GeometryNode(
                node_id=nid,
                hierarchy=NodeHierarchy(volume_index=1, arc_index=1, sequence_index=1),
                chapter_window=(1, 1),
                structural_role=StructuralRole.DEVELOP,
                primary_thread="TM01",
            ))

        graph.add_edge(GeometryEdge("E_START", "N_START", "N_CLUE1", EdgeType.CAUSES, 1))

        # N_CLUE1 綁定 CLUE_1
        c1 = graph.nodes["N_CLUE1"].ensure_story_contract()
        c1.foreshadowing_tasks.append({"clue_id": "CLUE_1", "role": "PLANT"})

        # N_REMOTE1 同時綁定 CLUE_1 與 CLUE_2
        cr1 = graph.nodes["N_REMOTE1"].ensure_story_contract()
        cr1.foreshadowing_tasks.append({"clue_id": "CLUE_1", "role": "TURN"})
        cr1.foreshadowing_tasks.append({"clue_id": "CLUE_2", "role": "PLANT"})

        # N_REMOTE2 綁定 CLUE_2
        cr2 = graph.nodes["N_REMOTE2"].ensure_story_contract()
        cr2.foreshadowing_tasks.append({"clue_id": "CLUE_2", "role": "PAYOFF"})

        analyzer = ImpactAnalyzer()
        impact = analyzer.analyze_node_impact(graph, "N_START", ["state_mutations"])

        assert "N_START" in impact
        assert "N_CLUE1" in impact
        assert "N_REMOTE1" in impact, "傳遞第一層伏筆節點應被包含"
        assert "N_REMOTE2" in impact, "連鎖第二層伏筆節點應被包含"
        assert "N_ISOLATED" not in impact, "無關隔離節點不得被包含"

    def test_unknown_fields_safely_default_to_causal_protection(self, standard_graph_10vol):
        """
        未知/外來欄位防禦性歸類測試：
        任何未列於白名單的未知欄位 (如 'quantum_destiny', 'magic_system_law')，
        classify_field 必須安全降級為 'causal'，觸發下游因果保護，防止潛在故事破壞被漏檢。
        """
        assert classify_field("quantum_destiny") == "causal"
        assert classify_field("magic_system_law") == "causal"
        assert classify_field("custom_unrecognized_slot") == "causal"

        analyzer = ImpactAnalyzer()
        nid = standard_graph_10vol.threads["TM01"].node_sequence[0]
        impact = analyzer.analyze_node_impact(standard_graph_10vol, nid, ["quantum_destiny"])

        # 因歸入 causal，其影響集合必須包含其下游因果節點，而非僅限於 {nid}
        causal_succs = standard_graph_10vol.get_causal_successors(nid)
        if causal_succs:
            assert len(impact) > 1
            assert any(s in impact for s in causal_succs)

    def test_empty_fields_and_nonexistent_node_resilience(self, standard_graph_10vol):
        """邊界健壯性：空欄位清單與不存在節點的安全防護。"""
        analyzer = ImpactAnalyzer()
        nid = list(standard_graph_10vol.nodes.keys())[0]

        # 空欄位
        assert analyzer.analyze_node_impact(standard_graph_10vol, nid, []) == {nid}

        # 不存在節點
        assert analyzer.analyze_node_impact(standard_graph_10vol, "NON_EXISTENT_NODE_999", ["title"]) == {"NON_EXISTENT_NODE_999"}
        assert analyzer.analyze_node_impact(standard_graph_10vol, "NON_EXISTENT_NODE_999", ["state_mutations"]) == {"NON_EXISTENT_NODE_999"}

