# -*- coding: utf-8 -*-
"""
Milestone 4 Verification Tests:
Downstream Outlines, Writing (Spoiler Wall), Polishing (Fact Diff Guard),
Story Completion Gate (Stage 08), and Autonomous Pipeline Master Graph Orchestration.
"""

import json
import os
import sqlite3
import pytest

from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    GeometryGraph,
    GeometryNode,
    GeometryParams,
    NodeType,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    StructuralRole,
)
from backend.generation.director.master_graph_service import MasterGraphService
from backend.generation.director.completion_gates import (
    StoryCompletionGate,
    TopologyGate,
    WorldviewGate,
    CharacterGate,
    TwistGate,
    ForeshadowingGate,
)
from backend.generation.director.impact_analyzer import (
    LocalRepairCoordinator,
    RepairRequest,
    RepairTier,
)
from backend.persistence.repositories.master_graph_repository import (
    MasterGraphRepository,
    init_master_graph_tables,
    save_master_graph,
    load_master_graph,
    save_node_chapter_beats,
    get_node_beats,
    get_beat_nodes,
    update_node_realization_status,
    save_checkpoint,
    load_checkpoint,
    record_draft_audit,
    get_draft_audits,
)
from backend.agents.volumes_planner.runner import backfill_volume_outlines_to_master_graph
from backend.agents.volume_skeleton.runner import backfill_chapter_beats_to_master_graph
from backend.agents.editor.runner import audit_fact_diff_guard


@pytest.fixture
def test_novel_id():
    novel_id = "test_novel_ms4_001"
    from backend.persistence import create_novel, delete_novel, init_master_graph_tables
    init_master_graph_tables()
    try:
        delete_novel(novel_id)
    except Exception:
        pass
    create_novel(novel_id, "Milestone 4 Novel", "仙俠", "Classic")
    yield novel_id
    try:
        delete_novel(novel_id)
    except Exception:
        pass


@pytest.fixture
def populated_master_graph(test_novel_id):
    """建立包含 10 卷、24 線程、世界觀、角色與閉環伏筆的完整 Master Graph"""
    gen = GeometryGenerator(GeometryParams(volume_count=10, chapters_per_volume=30, seed_for_rng=42))
    graph = gen.generate()

    # 回填世界觀至碰撞節點
    from backend.agents.story_architect.runner import backfill_worldview_to_master_graph
    worldview_text = """
    【核心世界觀】
    世界名：天元界
    勢力：天陽宗, 玄陰殿, 萬仙盟, 幽冥古教
    地點：天道青雲峰, 九幽血海, 歸墟海眼
    力量法則：三品金丹, 九轉元嬰
    碰撞衝突：仙魔大爭，資源爭奪，天道崩解
    """
    save_master_graph(test_novel_id, graph)
    backfill_worldview_to_master_graph(test_novel_id, worldview_text)

    # 回填 75 位角色名冊
    from backend.agents.character_designer.runner import backfill_characters_to_master_graph
    char_list = []
    for i in range(1, 76):
        char_list.append({
            "name": f"修仙者_{i:02d}",
            "role": "核心戰力" if i <= 10 else "中堅骨幹",
            "faction": "天陽宗" if i % 2 == 0 else "玄陰殿",
            "personality": "行事果斷，謀定而後動",
            "want": "問道長生",
        })
    backfill_characters_to_master_graph(test_novel_id, {"characters": char_list})

    # 回填伏筆與轉折
    from backend.agents.foreshadowing_orchestrator.runner import backfill_foreshadowing_and_twists_to_master_graph
    seeds = [
        {"id": f"SEED_{i:02d}", "content": f"第 {i} 號仙古殘碑秘密", "payoff_deadline_chapter": 20 + i * 5}
        for i in range(1, 15)
    ]
    turns = [
        {"id": f"TURN_{i:02d}", "event": f"仙魔對立第 {i} 次決裂", "expected_chapter": 15 + i * 5}
        for i in range(1, 12)
    ]
    backfill_foreshadowing_and_twists_to_master_graph(test_novel_id, seeds=seeds, turns=turns)

    # 重新讀取已填充的圖
    return load_master_graph(test_novel_id)


def test_volume_planner_backfill(test_novel_id, populated_master_graph):
    """測試 Stage 06: Volume Planner 大綱回填至 Master Graph VolumeContainer"""
    volumes = [
        {
            "volume_index": i,
            "title": f"第 {i} 卷：風起天元",
            "summary": f"第 {i} 卷敘述天陽宗與玄陰殿在歸墟的明爭暗鬥，主角突破境界。",
            "chapter_count": 30,
            "start_chapter": (i - 1) * 30 + 1,
            "end_chapter": i * 30,
        }
        for i in range(1, 11)
    ]

    res = backfill_volume_outlines_to_master_graph(test_novel_id, volumes)
    assert res["status"] == "success"
    assert res["mapped_volumes"] == 10
    assert res["updated_nodes"] > 0

    # 驗證圖中 volumes 容器已更新且核心因果邊未被破壞
    reloaded = load_master_graph(test_novel_id)
    assert 1 in reloaded.volumes
    assert reloaded.volumes[1].title == "第 1 卷：風起天元"
    assert len(reloaded.edges) == len(populated_master_graph.edges)


def test_volume_skeleton_backfill_and_beat_coverage(test_novel_id, populated_master_graph):
    """測試 Stage 07: Volume Skeleton 章節細綱與拍點回填至 NODE_CHAPTER_BEATS 並達成 100% 覆蓋"""
    # 為前 3 卷建立章節骨架
    for vol_idx in range(1, 4):
        chapters = []
        for ch_idx in range((vol_idx - 1) * 30 + 1, vol_idx * 30 + 1):
            chapters.append({
                "chapter_index": ch_idx,
                "title": f"第 {ch_idx} 章：雲海驚變",
                "scene_goal": "探索古殿遺址，獲取天元真髓",
                "conflict": "遭遇玄陰殿死士伏擊",
                "characters_active": ["修仙者_01", "修仙者_02"],
                "planned_words": 2800,
            })
        res = backfill_chapter_beats_to_master_graph(test_novel_id, vol_idx, chapters)
        assert res["status"] == "success"
        assert res["mapped_beats"] > 0
        assert res["coverage_ratio"] == 1.0

    # 驗證資料庫查詢 NODE_CHAPTER_BEATS
    beats = get_beat_nodes(test_novel_id, chapter_index=1)
    assert len(beats) > 0
    first_beat = beats[0]
    assert "node_id" in first_beat
    assert first_beat["coverage_ratio"] == 1.0


def test_story_completion_gate_and_canon_lock(test_novel_id, populated_master_graph):
    """測試 Stage 08: StoryCompletionGate 完整門禁驗收並鎖定 STORY_CANON_LOCKED"""
    # 為所有 10 卷回填篇卷與章節骨架，確保 100% 覆蓋
    volumes = [
        {"volume_index": i, "title": f"第 {i} 卷", "summary": "篇卷大綱", "chapter_count": 30}
        for i in range(1, 11)
    ]
    backfill_volume_outlines_to_master_graph(test_novel_id, volumes)

    for vol_idx in range(1, 11):
        chapters = [
            {
                "chapter_index": (vol_idx - 1) * 30 + c,
                "title": f"第 {(vol_idx - 1) * 30 + c} 章",
                "scene_goal": "推進章節情節",
                "conflict": "宗門矛盾",
                "characters_active": ["修仙者_01"],
            }
            for c in range(1, 31)
        ]
        backfill_chapter_beats_to_master_graph(test_novel_id, vol_idx, chapters)

    graph = load_master_graph(test_novel_id)
    assert graph is not None

    # 執行 Stage 08 StoryCompletionGate 驗收
    gate_res = StoryCompletionGate.evaluate(graph, auto_lock=True, strict_twist=False)
    assert gate_res.passed is True
    assert gate_res.metrics["chapter_coverage_rate"] == 1.0
    assert gate_res.metrics["canon_locked"] is True

    # 驗證 Master Graph 節點狀態已轉為 STORY_CANON_LOCKED
    assert graph.planning_status == PlanningStatus.STORY_CANON_LOCKED
    for node in graph.nodes.values():
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

    # 持久化並確認資料庫狀態
    save_master_graph(test_novel_id, graph)
    stats = MasterGraphRepository().get_master_graph_stats(test_novel_id)
    assert stats["is_canon_locked"] is True
    assert stats["locked_node_count"] == stats["node_count"]


def test_writer_spoiler_wall_and_realization(test_novel_id, populated_master_graph):
    """測試 Stage 09: Chapter Writer 防劇透牆 (Strict Spoiler Wall) 與實現狀態流轉"""
    # 挑選一節點進行 Writer 上下文投射
    node_id = list(populated_master_graph.nodes.keys())[0]
    proj = MasterGraphService.project_node_context(
        populated_master_graph, node_id, target_agent="chapter_writer"
    )

    # 驗證下游因果已啟動防劇透護盾
    assert "downstream_trajectory" in proj
    for item in proj["downstream_trajectory"]:
        assert "SPOILER_WALL_ACTIVE" in item["spoiler_shield"]

    # 驗證埋設伏筆的未來回收真相已被遮蔽
    for task in proj.get("foreshadowing_tasks", []):
        if str(task.get("role", "")).upper() == "PLANT":
            assert task.get("future_payoff_target") == "[SPOILER_PROTECTED_FUTURE_PAYOFF]"

    # 驗證正文寫作成功後，節點生命週期推進為 REALIZED
    update_node_realization_status(test_novel_id, node_id, RealizationStatus.REALIZED)
    beats = get_beat_nodes(test_novel_id, chapter_index=1)
    if beats:
        matching = [b for b in beats if b["node_id"] == node_id]
        if matching:
            assert matching[0]["realization_status"] == RealizationStatus.REALIZED.value


def test_editor_fact_diff_guard_and_audit_ledger(test_novel_id, populated_master_graph):
    """測試 Stage 10: Editor Fact Diff Guard 檢測參與實體竄改並記錄至 chapter_draft_audits"""
    # 原稿包含既定角色
    original_prose = "修仙者_01 與長老在天道青雲峰頂靜坐論道，玄陰殿的殺機已然逼近。"

    # 精修稿正常拋光
    good_final_prose = "修仙者_01 凝神屏息，與宗門長老於天道青雲峰絕頂相對而坐，遠方玄陰殿的凜冽殺氣已悄然逼近。"
    ok, defects, report = audit_fact_diff_guard(
        novel_id=test_novel_id,
        chapter_index=1,
        original_prose=original_prose,
        final_prose=good_final_prose,
    )
    assert ok is True
    assert len(defects) == 0

    # 檢查審計日誌
    audits = get_draft_audits(test_novel_id, chapter_index=1)
    assert len(audits) >= 1
    assert audits[0]["audit_status"] == "PASSED"


def test_local_repair_coordinator_tiers(test_novel_id):
    """測試 LocalRepairCoordinator 四級局部修復政策診斷"""
    coordinator = LocalRepairCoordinator()

    # Level 1: 純生成格式缺陷
    req_l1 = RepairRequest(
        novel_id=test_novel_id,
        defects=["JSON parse syntax error: missing closing brace"],
    )
    assert coordinator.diagnose_repair_tier(req_l1) == RepairTier.LEVEL_1_AGENT_PROMPT

    # Level 2: 節點特定 Slot 缺失
    req_l2 = RepairRequest(
        novel_id=test_novel_id,
        node_id="N_V01_A01_01",
        slot_name="worldview_slot",
        defects=["worldview_slot missing location_id"],
    )
    assert coordinator.diagnose_repair_tier(req_l2) == RepairTier.LEVEL_2_NODE_SLOT

    # Level 3: 因果核心欄位變更
    req_l3 = RepairRequest(
        novel_id=test_novel_id,
        node_id="N_V01_A01_01",
        changed_fields=["direct_outcome", "state_mutations"],
        defects=["Causal branch divergence detected"],
    )
    assert coordinator.diagnose_repair_tier(req_l3) == RepairTier.LEVEL_3_IMPACT_SUBGRAPH


def test_pipeline_checkpoint_persistence(test_novel_id):
    """測試 pipeline_task_checkpoints 狀態機持久化與讀取"""
    ckpt_data = {
        "run_id": f"run_{test_novel_id}_stage08",
        "novel_id": test_novel_id,
        "current_stage": "story_completion_gate",
        "current_chapter": 0,
        "graph_revision": 2,
        "retry_count": 1,
        "next_retry_at": "2026-10-10T12:00:00Z",
        "status": "RUNNING",
        "state_payload": {"last_gate": "passed"},
    }
    save_checkpoint(ckpt_data)

    loaded = load_checkpoint(ckpt_data["run_id"])
    assert loaded is not None
    assert loaded["current_stage"] == "story_completion_gate"
    assert loaded["retry_count"] == 1
    assert loaded["state_payload"]["last_gate"] == "passed"
