# -*- coding: utf-8 -*-
"""
Milestone 3 單元測試套件: 上游 Agent 適配與 Master Graph SQLite 持久化倉儲層.

驗證範疇:
1. MasterGraphRepository: 7 張資料表初始化、GeometryGraph 雙向無損反序列化、節點/邊/事件/拍點關聯查詢。
2. Checkpoints & Audits: 斷點續傳狀態機、防退化冷卻時序、草稿事實違規日誌隔離。
3. Story Architect (世界觀): 碰撞節點 worldview_slot 回填與 WorldviewGate 驗收。
4. Character Designer (角色): 70–120+ 群像名冊、嚴格去命運化 (De-destined) 與 CharacterGate 驗收。
5. Foreshadowing Orchestrator (伏筆與轉折): 九維具體故事事件契約、Plant < Turn < Payoff 時序閉環與 TwistGate / ForeshadowingGate 驗收。
6. 全流程循序串聯整合測試 (Sequential Integration Pipeline)。
"""

import json
import sqlite3
import pytest
import uuid
from typing import Dict, Any, List

from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    GeometryParams,
    GeometryComplexity,
    NodeType,
    StructuralRole,
    PlanningStatus,
    RealizationStatus,
    StoryEventContract,
    NodeStoryContract,
    EdgeType,
)
from backend.persistence.repositories.master_graph_repository import (
    MasterGraphRepository,
    init_master_graph_tables,
    save_master_graph,
    load_master_graph,
    save_checkpoint,
    load_checkpoint,
    get_latest_checkpoint,
    record_draft_audit,
    get_draft_audits,
    get_node_beats,
    get_beat_nodes,
    get_story_events_for_node,
    get_master_graph_stats,
    has_master_graph,
    delete_master_graph,
)
from backend.generation.director.completion_gates import (
    WorldviewGate,
    CharacterGate,
    TwistGate,
    ForeshadowingGate,
    TopologyGate,
)
from backend.agents.story_architect.runner import backfill_worldview_to_master_graph
from backend.agents.character_designer.runner import backfill_characters_to_master_graph
from backend.agents.foreshadowing_orchestrator.runner import backfill_foreshadowing_and_twists_to_master_graph


@pytest.fixture
def memory_db_repo(monkeypatch):
    """建立共用之記憶體 SQLite 資料庫連線並綁定至 master_graph_repository。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # 初始化小說基底表與幾何表
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS novels (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS geometry_metadata (
        novel_id TEXT PRIMARY KEY,
        params_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS geometry_threads (
        thread_id TEXT NOT NULL,
        novel_id TEXT NOT NULL,
        thread_type TEXT NOT NULL,
        node_sequence_json TEXT,
        structural_skeleton_json TEXT,
        semantic_json TEXT,
        metadata_json TEXT,
        PRIMARY KEY (novel_id, thread_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS geometry_volumes (
        volume_id TEXT NOT NULL,
        novel_id TEXT NOT NULL,
        volume_index INTEGER NOT NULL,
        chapter_start INTEGER NOT NULL,
        chapter_end INTEGER NOT NULL,
        arc_ids_json TEXT,
        semantic_json TEXT,
        PRIMARY KEY (novel_id, volume_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS geometry_arcs (
        arc_id TEXT NOT NULL,
        novel_id TEXT NOT NULL,
        volume_index INTEGER NOT NULL,
        arc_index INTEGER NOT NULL,
        chapter_start INTEGER NOT NULL,
        chapter_end INTEGER NOT NULL,
        thread_ids_json TEXT,
        semantic_json TEXT,
        PRIMARY KEY (novel_id, arc_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worldbuilding (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    repo = MasterGraphRepository(connection_provider=lambda: conn)
    repo.init_tables(conn)

    # 模擬全域 get_db_connection
    monkeypatch.setattr("backend.persistence.connection.get_db_connection", lambda: conn)
    monkeypatch.setattr("backend.persistence.repositories.master_graph_repository.get_db_connection", lambda: conn)
    import backend.persistence.repositories.master_graph_repository as mgr_mod
    monkeypatch.setattr(mgr_mod, "master_graph_repository", repo)
    monkeypatch.setattr("backend.persistence.master_graph_repository", repo)

    return repo, conn


@pytest.fixture
def sample_graph():
    """生成包含 10 卷、6 主線、18 支線的幾何圖骨架。"""
    params = GeometryParams(
        target_chapters=300,
        volume_count=10,
        chapters_per_volume=30,
        complexity=GeometryComplexity.DENSE,
        main_thread_count=6,
        subplot_count=18,
        seed_for_rng=42,
    )
    generator = GeometryGenerator(params)
    graph = generator.generate()
    return graph


class TestMasterGraphRepositoryPersistence:
    """測試 Master Graph 7 張資料表初始化與資料庫 CRUD 持久化。"""

    def test_init_tables_creates_all_seven_tables(self, memory_db_repo):
        repo, conn = memory_db_repo
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

        expected_tables = [
            "MASTER_GRAPH_NODES",
            "MASTER_GRAPH_EDGES",
            "STORY_EVENT_ENTITIES",
            "NODE_CHAPTER_BEATS",
            "NODE_THREAD_MEMBERSHIPS",
            "pipeline_task_checkpoints",
            "chapter_draft_audits",
        ]
        for tbl in expected_tables:
            assert tbl in tables, f"缺少資料表: {tbl}"

    def test_save_and_load_master_graph_roundtrip(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "test_novel_001"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "測試小說一"))
        conn.commit()

        # 儲存圖
        repo.save_master_graph(novel_id, sample_graph, revision=1)
        assert repo.has_master_graph(novel_id) is True

        # 讀取圖
        loaded_graph = repo.load_master_graph(novel_id)
        assert loaded_graph is not None
        assert len(loaded_graph.nodes) == len(sample_graph.nodes)
        assert len(loaded_graph.edges) == len(sample_graph.edges)
        assert len(loaded_graph.threads) == len(sample_graph.threads)
        assert len(loaded_graph.volumes) == len(sample_graph.volumes)
        assert loaded_graph.graph_revision == 1

        # 驗證因果無環性
        errors = loaded_graph.validate_causal_dag()
        assert len(errors) == 0

    def test_beat_mapping_and_event_queries(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "test_novel_002"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "測試小說二"))
        conn.commit()

        # 挑選第一個節點增加九維事件與拍點映射
        target_node = next(iter(sample_graph.nodes.values()))
        contract = target_node.ensure_story_contract()
        ev = StoryEventContract(
            event_id=f"EV_{target_node.node_id}_test",
            node_id=target_node.node_id,
            event_summary="核心宗門試煉衝突事件",
            participant_entities=[{"name": "林辰", "role": "PROTAGONIST"}],
            action_motives=[{"entity": "林辰", "motive": "奪取造化"}],
            causal_preconditions=["前置宗門大比開啟"],
            core_conflict="擂台生死博弈",
            direct_outcome="林辰強勢獲勝",
            state_mutations=[{"entity": "林辰", "mutation": "境界突破至築基中期"}],
            downstream_impact=["引動長老院關注"],
            clue_bindings=["CLUE_TEST_01"],
        )
        contract.story_events.append(ev)
        contract.chapter_mappings = [
            {"chapter_index": 5, "beat_index": 1, "coverage_ratio": 0.8},
            {"chapter_index": 5, "beat_index": 2, "coverage_ratio": 0.2},
        ]

        repo.save_master_graph(novel_id, sample_graph, revision=2)

        # 測試節點拍點查詢
        beats = repo.get_node_beats(novel_id, target_node.node_id)
        assert len(beats) == 2
        assert beats[0]["chapter_index"] == 5
        assert beats[0]["beat_index"] == 1

        # 測試章節拍點查詢
        beat_nodes = repo.get_beat_nodes(novel_id, 5)
        assert len(beat_nodes) >= 2
        assert any(b["node_id"] == target_node.node_id for b in beat_nodes)

        # 測試事件查詢
        events = repo.get_story_events_for_node(novel_id, target_node.node_id)
        assert len(events) == 1
        assert events[0].event_summary == "核心宗門試煉衝突事件"
        assert events[0].clue_bindings == ["CLUE_TEST_01"]

    def test_checkpoint_state_machine(self, memory_db_repo):
        repo, conn = memory_db_repo
        novel_id = "test_novel_chk"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "檢查點測試小說"))
        conn.commit()

        run_id = str(uuid.uuid4())
        checkpoint_data = {
            "run_id": run_id,
            "novel_id": novel_id,
            "current_stage": "stage_03_worldview",
            "current_node_id": "G0001",
            "current_chapter": 1,
            "graph_revision": 2,
            "retry_count": 1,
            "next_retry_at": "2026-10-09T00:00:00Z",
            "status": "COOLDOWN",
            "state_payload": {"last_action": "waiting_cooldown"},
        }

        repo.save_checkpoint(checkpoint_data)
        loaded = repo.load_checkpoint(run_id)
        assert loaded is not None
        assert loaded["status"] == "COOLDOWN"
        assert loaded["retry_count"] == 1
        assert loaded["state_payload"]["last_action"] == "waiting_cooldown"

        # 更新狀態
        repo.update_checkpoint_status(run_id, status="RESUMED", retry_count=0)
        latest = repo.get_latest_checkpoint(novel_id)
        assert latest["status"] == "RESUMED"
        assert latest["retry_count"] == 0

    def test_chapter_draft_audits_isolation(self, memory_db_repo):
        repo, conn = memory_db_repo
        novel_id = "test_novel_audit"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "審計日誌小說"))
        conn.commit()

        audit_id = repo.record_draft_audit(
            novel_id=novel_id,
            chapter_index=12,
            audit_status="VIOLATED",
            defects=[{"type": "FACT_DIFF", "desc": "角色武器描述與正典衝突"}],
            audit_report={"editor_suggestion": "修正武器為青霜劍"},
        )
        assert audit_id > 0

        history = repo.get_draft_audits(novel_id, chapter_index=12)
        assert len(history) == 1
        assert history[0]["audit_status"] == "VIOLATED"
        assert history[0]["defects"][0]["type"] == "FACT_DIFF"

    def test_delete_master_graph_cascade(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "test_novel_del"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "刪除測試小說"))
        conn.commit()

        repo.save_master_graph(novel_id, sample_graph, revision=1)
        assert repo.has_master_graph(novel_id) is True

        repo.delete_master_graph(novel_id)
        assert repo.has_master_graph(novel_id) is False
        stats = repo.get_master_graph_stats(novel_id)
        assert stats["node_count"] == 0


class TestUpstreamAgentsAdaptationAndGates:
    """測試世界觀、角色、伏筆上游 Agent 的 Master Graph 槽位回填與閘門驗證。"""

    def test_story_architect_backfill_and_worldview_gate(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "novel_sa_001"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "世界觀測試小說"))
        conn.commit()

        repo.save_master_graph(novel_id, sample_graph, revision=1)

        worldview_data = {
            "theme": "天道衰微與凡人弒神之路",
            "main_conflict": "九大古世家對天地源氣的壟斷引發底層逆伐",
            "worldview": "太初大陸分為九大靈域，古族執掌天軌，散修與異族在夾縫中求存。",
            "macro_outline": "林辰自邊陲崛起，勘破天道枷鎖，團結流亡勢力，最終掀翻古族祭壇。",
            "factions": [
                {"name": "太虛古族", "type": "古老世家"},
                {"name": "破曉同盟", "type": "起義散修"},
            ],
            "progressive_character_plan": [
                {"name": "林辰", "faction": "破曉同盟"},
                {"name": "姬如霜", "faction": "太虛古族"},
            ],
        }

        # 執行世界觀回填
        success = backfill_worldview_to_master_graph(novel_id, worldview_data)
        assert success is True

        # 重新載入並驗證 WorldviewGate
        loaded_graph = repo.load_master_graph(novel_id)
        gate_res = WorldviewGate.evaluate(loaded_graph)
        assert gate_res.passed is True, f"WorldviewGate 未通過: {gate_res.defects}"
        assert gate_res.metrics["worldview_backfill_rate"] == 1.0

    def test_character_designer_backfill_and_character_gate(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "novel_cd_001"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "角色測試小說"))
        conn.commit()

        repo.save_master_graph(novel_id, sample_graph, revision=1)

        # 構建包含 20 名主要角色的清單，包含部分可能帶有終局狀態的髒資料
        characters_list = [
            {
                "character_id": f"CHAR_{i:03d}",
                "name": f"核心角色_{i}",
                "faction": "破曉同盟" if i % 2 == 0 else "太虛古族",
                "role": "PROTAGONIST" if i == 1 else "ACTOR",
                "initial_status": "DEAD" if i == 5 else "ACTIVE", # 測試去命運化洗滌
                "destined_death": "第8卷戰死" if i == 5 else None, # 測試劇透欄位移除
                "motivation": f"守護信念，打破桎梏_{i}",
            }
            for i in range(1, 25)
        ]

        # 執行角色名冊回填 (自動補足至 10 卷規模 70+ 名角色)
        success = backfill_characters_to_master_graph(novel_id, characters_list, min_roster=70)
        assert success is True

        # 重新載入並驗證 CharacterGate
        loaded_graph = repo.load_master_graph(novel_id)
        gate_res = CharacterGate.evaluate(loaded_graph, min_roster_count=70)
        assert gate_res.passed is True, f"CharacterGate 未通過: {gate_res.defects}"
        assert gate_res.metrics["unique_characters_count"] >= 70
        assert gate_res.metrics["de_destined_compliance"] is True
        assert gate_res.metrics["spoiler_violations_count"] == 0

    def test_foreshadowing_orchestrator_backfill_and_gates(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "novel_fo_001"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "伏筆測試小說"))
        conn.commit()

        # 先回填角色槽位以供事件實體使用
        backfill_characters_to_master_graph(novel_id, [], min_roster=70)
        # 儲存
        repo.save_master_graph(novel_id, sample_graph, revision=1)

        seeds = [
            {"clue_id": f"CLUE_0{i}", "name": f"殘缺玉簡_{i}", "description": f"記錄古神隕落真相_{i}"}
            for i in range(1, 9)
        ]
        turning_points = [
            {"turn_id": f"TURN_0{i}", "summary": f"第{i}卷核心大比奪魁與暗流湧動"}
            for i in range(1, 11)
        ]

        # 執行伏筆與轉折回填
        success = backfill_foreshadowing_and_twists_to_master_graph(
            novel_id, seeds=seeds, turning_points=turning_points
        )
        assert success is True

        # 重新載入並驗證 TwistGate (九維事件完備性)
        loaded_graph = repo.load_master_graph(novel_id)
        twist_res = TwistGate.evaluate(loaded_graph, strict=True)
        assert twist_res.passed is True, f"TwistGate 未通過: {twist_res.defects}"
        assert twist_res.metrics["core_completion_rate"] == 1.0

        # 驗證 ForeshadowingGate (時間序與 100% 閉環)
        fore_res = ForeshadowingGate.evaluate(loaded_graph)
        assert fore_res.passed is True, f"ForeshadowingGate 未通過: {fore_res.defects}"
        assert fore_res.metrics["closure_rate"] == 1.0
        assert fore_res.metrics["temporal_violations"] == 0


class TestSequentialIntegrationPipeline:
    """測試從幾何拓撲生成到各上游 Agent 循序回填與全閘門驗收之端到端流程。"""

    def test_sequential_upstream_pipeline_all_gates_pass(self, memory_db_repo, sample_graph):
        repo, conn = memory_db_repo
        novel_id = "pipeline_novel_e2e"
        cursor = conn.cursor()
        cursor.execute("INSERT INTO novels (id, title) VALUES (?, ?)", (novel_id, "全管線整合小說"))
        conn.commit()

        # Stage 02: 拓撲引擎產生 Master Graph 骨架並寫入 SQLite
        repo.save_master_graph(novel_id, sample_graph, revision=1)
        topo_res = TopologyGate.evaluate(sample_graph)
        assert topo_res.passed is True

        # Stage 03: Worldview Agent 填充世界觀
        worldview_payload = {
            "theme": "文明興衰與天道輪迴",
            "main_conflict": "上界仙門與下界凡國之氣運爭端",
            "factions": ["太一仙宗", "天機閣", "南荒萬妖山", "大周仙朝"],
        }
        res_wv = backfill_worldview_to_master_graph(novel_id, worldview_payload)
        assert res_wv is True
        g_wv = repo.load_master_graph(novel_id)
        assert WorldviewGate.evaluate(g_wv).passed is True

        # Stage 04: Character Agent 填充角色名冊 (70+ 角色無劇透)
        res_char = backfill_characters_to_master_graph(novel_id, [], min_roster=75)
        assert res_char is True
        g_char = repo.load_master_graph(novel_id)
        assert CharacterGate.evaluate(g_char, min_roster_count=70).passed is True

        # Stage 05: Twist & Foreshadowing Agent 填充九維事件與伏筆閉環
        res_twist = backfill_foreshadowing_and_twists_to_master_graph(novel_id)
        assert res_twist is True
        g_twist = repo.load_master_graph(novel_id)
        assert TwistGate.evaluate(g_twist, strict=True).passed is True
        assert ForeshadowingGate.evaluate(g_twist).passed is True

        # 驗證整體資料庫統計數據
        stats = repo.get_master_graph_stats(novel_id)
        assert stats["node_count"] > 0
        assert stats["edge_count"] > 0
        assert stats["story_event_count"] > 0
        assert stats["graph_revision"] >= 4
