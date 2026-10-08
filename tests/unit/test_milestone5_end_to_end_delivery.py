# -*- coding: utf-8 -*-
"""
Milestone 5 Verification: End-to-End Simulation & Delivery.

Verifies the complete 10-stage Master Graph Single-Source-of-Truth pipeline:
01. User Synopsis -> db.create_novel
02. Pure Algorithmic Topology -> GeometryGenerator (10 volumes, 6 main threads, 18 sub-branches, DAG)
03. Worldview Agent -> story_architect backfill -> WorldviewGate
04. Character Agent -> character_designer backfill (70+ characters) -> CharacterGate
05. Twist & Foreshadowing -> foreshadowing_orchestrator backfill (9-dim events, temporal validity) -> TwistGate & ForeshadowingGate
06. Volume Planner -> volumes_planner backfill -> graph.volumes populated
07. Chapter Planner -> volume_skeleton backfill -> NODE_CHAPTER_BEATS mapping
08. Story Completion Gate -> 100% thread convergence, 100% clue closure, 100% beat coverage -> STORY_CANON_LOCKED
09. Chapter Writer -> Strict Spoiler Wall (masks future turns & payoffs) -> Draft generation
10. Editor & Director Audit -> Fact Diff Guard -> Node Realization -> Commit to SQLite
"""

import json
import pytest

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    GeometryGraph,
    GeometryParams,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    StructuralRole,
)
from backend.generation.director.master_graph_service import MasterGraphService
from backend.generation.director.completion_gates import (
    TopologyGate,
    WorldviewGate,
    CharacterGate,
    TwistGate,
    ForeshadowingGate,
    StoryCompletionGate,
)
from backend.generation.director.impact_analyzer import (
    LocalRepairCoordinator,
    RepairRequest,
    RepairTier,
)
from backend.persistence.repositories.master_graph_repository import (
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
from backend.agents.story_architect.runner import backfill_worldview_to_master_graph
from backend.agents.character_designer.runner import backfill_characters_to_master_graph
from backend.agents.foreshadowing_orchestrator.runner import backfill_foreshadowing_and_twists_to_master_graph
from backend.agents.volumes_planner.runner import backfill_volume_outlines_to_master_graph
from backend.agents.volume_skeleton.runner import backfill_chapter_beats_to_master_graph
from backend.agents.editor.runner import audit_fact_diff_guard


@pytest.fixture
def e2e_novel_id():
    novel_id = "test_novel_e2e_m5_final"
    init_master_graph_tables()
    try:
        db.delete_novel(novel_id)
    except Exception:
        pass
    db.create_novel(novel_id, "星河天尊：終極萬界戰", "修仙", "東方玄幻")
    yield novel_id
    try:
        db.delete_novel(novel_id)
    except Exception:
        pass


def test_milestone5_complete_ten_stage_pipeline_simulation(e2e_novel_id):
    """
    完整的 10 階段端到端模擬測試：
    驗證從作品創建、純演算法 Master Graph 生成、各 Agent 回填、
    Story Completion Gate 剛性鎖定、Writer 防劇透牆隔離，到 Editor 質檢提交通行。
    """
    # =========================================================================
    # Stage 01: User Synopsis
    # =========================================================================
    novel = db.get_novel(e2e_novel_id)
    assert novel is not None
    assert novel["title"] == "星河天尊：終極萬界戰"

    # =========================================================================
    # Stage 02: Pure Algorithmic Topology (GeometryGenerator)
    # =========================================================================
    gen = GeometryGenerator(GeometryParams(volume_count=10, chapters_per_volume=30, seed_for_rng=100))
    graph = gen.generate()
    save_master_graph(e2e_novel_id, graph)

    topo_gate = TopologyGate.evaluate(graph)
    for tm in TopologyGate.EXPECTED_MAIN_THREADS:
        assert tm in graph.threads
    for ts in TopologyGate.EXPECTED_SUB_THREADS:
        assert ts in graph.threads
    assert len(graph.volumes) == 10
    assert len(graph.nodes) >= 300

    # =========================================================================
    # Stage 03: Worldview Agent Backfill
    # =========================================================================
    worldview_data = {
        "theme": "太古天道碎裂與諸天仙神爭奪永生之門",
        "main_conflict": "北冥仙宗與混沌血殿的大道爭鋒與天地源氣爭奪",
        "worldview": "九幽星域與大千仙界分為九大靈域，仙魔並起，每一次動用太古仙術必損耗百年壽元或引動天劫反噬。",
        "macro_outline": "主角自南嶺落霞山崛起，勘破天道枷鎖，團結北冥仙宗勢力，最終平定九幽星域戰火，踏入永生之門。",
        "factions": [
            {"name": "北冥仙宗", "type": "古老仙門"},
            {"name": "混沌血殿", "type": "魔道巨擘"},
        ],
        "progressive_character_plan": [
            {"name": "角色_01", "faction": "北冥仙宗"},
            {"name": "角色_02", "faction": "混沌血殿"},
        ],
    }
    db.save_worldbuilding(e2e_novel_id, json.dumps(worldview_data, ensure_ascii=False))
    wv_res = backfill_worldview_to_master_graph(e2e_novel_id, worldview_data)
    assert wv_res is True or (isinstance(wv_res, dict) and wv_res.get("success") is True)

    graph_wv = load_master_graph(e2e_novel_id)
    wv_gate = WorldviewGate.evaluate(graph_wv)
    assert wv_gate.passed is True, f"WorldviewGate failed: {wv_gate.defects}"

    # =========================================================================
    # Stage 04: Character Agent Backfill (去命運化名冊)
    # =========================================================================
    roster = []
    factions = ["北冥仙宗", "太虛神朝", "混沌血殿", "萬妖古盟", "天機閣"]
    for i in range(1, 85):
        fac = factions[i % len(factions)]
        roster.append({
            "name": f"角色_{i:02d}",
            "gender": "男" if i % 2 == 0 else "女",
            "personality": "果敢堅毅" if i <= 10 else "謹慎沉著",
            "faction": fac,
            "role": "核心主角" if i == 1 else ("主要反派" if i == 2 else "宗門長老"),
            "power_level": "元嬰初期",
        })
    db.save_characters(e2e_novel_id, json.dumps({"characters": roster}, ensure_ascii=False))
    char_res = backfill_characters_to_master_graph(e2e_novel_id, roster)
    assert char_res is True

    graph_char = load_master_graph(e2e_novel_id)
    char_gate = CharacterGate.evaluate(graph_char)
    assert char_gate.passed is True, f"CharacterGate failed: {char_gate.defects}"

    # =========================================================================
    # Stage 05: Twist & Foreshadowing Agent Backfill (九維合約與伏筆閉環)
    # =========================================================================
    seeds = [
        {"clue_id": f"CLUE_0{i}", "name": f"太古星紋殘片_{i}", "description": f"記錄永生之門碎片真相_{i}"}
        for i in range(1, 9)
    ]
    turning_points = [
        {"turn_id": f"TURN_0{i}", "summary": f"第{i}卷核心仙魔大戰與暗流湧動"}
        for i in range(1, 11)
    ]

    twist_res = backfill_foreshadowing_and_twists_to_master_graph(
        novel_id=e2e_novel_id,
        seeds=seeds,
        turning_points=turning_points,
    )
    assert twist_res is True

    graph_twist = load_master_graph(e2e_novel_id)
    t_gate = TwistGate.evaluate(graph_twist)
    f_gate = ForeshadowingGate.evaluate(graph_twist)
    assert t_gate.passed is True, f"TwistGate failed: {t_gate.defects}"
    assert f_gate.passed is True, f"ForeshadowingGate failed: {f_gate.defects}"

    # =========================================================================
    # Stage 06: Volume Planner Backfill
    # =========================================================================
    vol_outlines = []
    for v_idx in range(1, 11):
        vol_outlines.append({
            "volume_index": v_idx,
            "title": f"第{v_idx}卷：諸天風雲起",
            "summary": f"講述主角在第{v_idx}卷經歷考驗並平定星域戰火",
            "core_conflict": "宗門內外激化博弈",
            "start_chapter": (v_idx - 1) * 30 + 1,
            "end_chapter": v_idx * 30,
        })
    v_res = backfill_volume_outlines_to_master_graph(e2e_novel_id, vol_outlines)
    assert v_res.get("status") == "success"

    graph_vols = load_master_graph(e2e_novel_id)
    assert len(graph_vols.volumes) == 10
    assert graph_vols.volumes["V01"].title == "第1卷：諸天風雲起"

    # =========================================================================
    # Stage 07: Chapter Planner Backfill (Beats Mapping across all 10 volumes)
    # =========================================================================
    sorted_node_ids = sorted(graph_vols.nodes.keys())
    for vol_idx in range(1, 11):
        chapters = [
            {
                "chapter_index": (vol_idx - 1) * 30 + c,
                "title": f"第 {(vol_idx - 1) * 30 + c} 章",
                "scene_goal": "推進章節情節",
                "conflict": "宗門內外矛盾",
                "characters_active": ["角色_01", "角色_02"],
            }
            for c in range(1, 31)
        ]
        skel_res = backfill_chapter_beats_to_master_graph(e2e_novel_id, vol_idx, chapters)
        assert skel_res.get("status") == "success"
        assert skel_res.get("mapped_beats", 0) > 0

    # 驗證 SQLite NODE_CHAPTER_BEATS 正確寫入
    node_beats_1 = get_node_beats(e2e_novel_id, sorted_node_ids[0])
    assert len(node_beats_1) >= 1
    assert node_beats_1[0]["chapter_index"] == 1

    # =========================================================================
    # Stage 08: Story Completion Gate (鎖定全書 Story Canon)
    # =========================================================================
    graph_ready = load_master_graph(e2e_novel_id)
    gate_res = StoryCompletionGate.evaluate(graph_ready, auto_lock=True, strict_twist=False)
    assert gate_res.passed is True
    assert gate_res.metrics["canon_locked"] is True

    # 驗證 Master Graph 節點狀態已轉為 STORY_CANON_LOCKED
    assert graph_ready.planning_status == PlanningStatus.STORY_CANON_LOCKED
    for node in graph_ready.nodes.values():
        assert node.planning_status == PlanningStatus.STORY_CANON_LOCKED

    # 持久化並確認資料庫狀態
    save_master_graph(e2e_novel_id, graph_ready)

    # =========================================================================
    # Stage 09: Chapter Writer (Strict Spoiler Wall Isolation)
    # =========================================================================
    node_id_ch1 = sorted_node_ids[0]
    writer_proj = MasterGraphService.project_node_context(
        graph_ready, node_id_ch1, target_agent="chapter_writer"
    )
    assert writer_proj["spoiler_wall_active"] is True
    assert "downstream_trajectory" in writer_proj
    for item in writer_proj["downstream_trajectory"]:
        assert "SPOILER_WALL_ACTIVE" in item["spoiler_shield"]

    # 驗證埋設伏筆的未來回收真相已被遮蔽
    for task in writer_proj.get("current_scene_contract", {}).get("foreshadowing_tasks", []):
        if str(task.get("role", "")).upper() == "PLANT":
            assert task.get("future_payoff_target") == "[SPOILER_PROTECTED_FUTURE_PAYOFF]"

    # 模擬 Writer 產出第 1 章正文
    ch1_prose = """
    落霞山晨霧未散，青石道上的露水透著刺骨的寒意。
    角色_01 按住劍柄，目光掃過林間微動的枯枝。
    一枚雕刻著太古星紋的殘片靜靜躺在石縫深處，散發出極淡的靈氣波動。
    身旁角色_02 低聲提醒：「魔宗探子就在附近，萬事小心。」
    角色_01 默然點頭，將殘片收入囊中，隨即仗劍向前。
    """ * 10
    db.save_chapter(e2e_novel_id, 1, ch1_prose)
    saved_ch1 = db.get_latest_chapter(e2e_novel_id, 1)
    assert saved_ch1 is not None

    # =========================================================================
    # Stage 10: Editor & Director Audit (Fact Diff Guard & Node Realization)
    # =========================================================================
    ok, defects, report = audit_fact_diff_guard(
        novel_id=e2e_novel_id,
        chapter_index=1,
        original_prose=ch1_prose,
        final_prose=ch1_prose,
    )
    assert ok is True
    assert len(defects) == 0

    # 驗證節點實現狀態更新至 REALIZED
    update_node_realization_status(e2e_novel_id, node_id_ch1, RealizationStatus.REALIZED)
    beats_ch1 = get_beat_nodes(e2e_novel_id, chapter_index=1)
    if beats_ch1:
        matching = [b for b in beats_ch1 if b["node_id"] == node_id_ch1]
        if matching:
            assert matching[0]["realization_status"] == RealizationStatus.REALIZED.value

    # 記錄審計稽核日誌
    audit_id = record_draft_audit(
        novel_id=e2e_novel_id,
        chapter_index=1,
        audit_status="PASSED",
        defects=[],
        audit_report={"passed_gates": ["FactDiffGuard", "SpoilerWallCheck"]},
    )
    assert audit_id > 0

    audits = get_draft_audits(e2e_novel_id, chapter_index=1)
    assert len(audits) >= 1
    assert audits[0]["audit_status"] == "PASSED"


def test_milestone5_local_repair_coordinator_resilience(e2e_novel_id):
    """
    測試總監四級局部修復政策診斷（Local Repair Priority）：
    驗證不同級別的缺陷被精確路由至相應修復層級，避免全圖重寫。
    """
    coordinator = LocalRepairCoordinator()

    # Level 1: 格式與提示詞層級
    req_l1 = RepairRequest(
        novel_id=e2e_novel_id,
        defects=["JSON syntax error: unmatched brackets in agent output"],
    )
    assert coordinator.diagnose_repair_tier(req_l1) == RepairTier.LEVEL_1_AGENT_PROMPT

    # Level 2: 節點單槽位定點手術
    req_l2 = RepairRequest(
        novel_id=e2e_novel_id,
        node_id="N_V01_A01_01",
        slot_name="worldview_slot",
        defects=["Missing geographic coordinates in worldview_slot"],
    )
    assert coordinator.diagnose_repair_tier(req_l2) == RepairTier.LEVEL_2_NODE_SLOT

    # Level 3: 因果變更影響子圖
    req_l3 = RepairRequest(
        novel_id=e2e_novel_id,
        node_id="N_V01_A01_01",
        changed_fields=["direct_outcome", "driving_motive"],
        defects=["Protagonist motive reversed"],
    )
    assert coordinator.diagnose_repair_tier(req_l3) == RepairTier.LEVEL_3_IMPACT_SUBGRAPH
