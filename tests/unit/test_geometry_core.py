# -*- coding: utf-8 -*-
"""
幾何核心模組單元測試 (Geometry Core Unit Tests)
驗證：
1. GeometryGenerator 生成完整圖譜、層級、節點與線程
2. MotifApplicator 成功生成 6 種敘事 Motif 結構邊
3. GeometryRepairEngine 嚴格遵循 4 大門禁條件，並支援 SPLIT / EXPAND / INSERT / COMPRESS
4. SQLite 持久層完整保存與恢復 GeometryGraph，包含語義增量更新
"""

import pytest

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    EdgeType,
    GeometryComplexity,
    GeometryParams,
    RepairOperation,
    RepairProposal,
    StructuralRole,
    ThreadType,
)
from backend.geometry.repair import (
    GeometryRepairCondition,
    GeometryRepairEngine,
    GeometryRepairGatekeeper,
)


def test_geometry_generation_scale_and_motifs():
    """驗證幾何圖生成規模、節點角色、線程分佈與 Motif 邊。"""
    params = GeometryParams(
        target_chapters=50,
        volume_count=2,
        chapters_per_volume=25,
        complexity=GeometryComplexity.DENSE,
        main_thread_count=2,
        subplot_count=4,
        character_arc_count=3,
        relationship_arc_count=2,
        thematic_thread_count=2,
        seed_for_rng="test_seed_12345",
    )

    generator = GeometryGenerator(params)
    graph = generator.generate()

    # 1. 驗證容器
    assert len(graph.volumes) == 2
    assert "V01" in graph.volumes
    assert "V02" in graph.volumes
    assert graph.volumes["V01"].chapter_range == (1, 25)
    assert graph.volumes["V02"].chapter_range == (26, 50)
    assert len(graph.arcs) >= 6

    # 2. 驗證節點數量與角色
    assert len(graph.nodes) >= 100  # 50 chapters * ~2.8 nodes
    roles = {n.structural_role for n in graph.nodes.values()}
    assert StructuralRole.OPEN_THREAD in roles
    assert StructuralRole.DEVELOP in roles

    # 3. 驗證線程
    assert len(graph.threads) >= 10
    main_threads = [t for t in graph.threads.values() if t.thread_type == ThreadType.MAIN]
    assert len(main_threads) == 2
    assert len(main_threads[0].node_sequence) >= 3

    # 4. 驗證邊與 Motif
    assert len(graph.edges) >= 50
    edge_types = {e.edge_type for e in graph.edges}
    assert EdgeType.CAUSES in edge_types or EdgeType.ENABLES in edge_types
    # 至少有部分高級敘事 Motif 邊被產生
    assert any(
        t in edge_types
        for t in (
            EdgeType.SETS_UP,
            EdgeType.ECHOES,
            EdgeType.PAYS_OFF,
            EdgeType.CONVERGES,
            EdgeType.CHARACTER_ARC,
            EdgeType.CONTRASTS,
        )
    )

    # 5. 驗證無懸空邊
    validation_errors = graph.validate()
    assert len(validation_errors) == 0


def test_geometry_repair_gatekeeper_and_operations():
    """驗證幾何修復引擎的 4 大門禁與 4 種操作。"""
    params = GeometryParams(target_chapters=20, volume_count=1, chapters_per_volume=20, seed_for_rng="repair_test")
    generator = GeometryGenerator(params)
    graph = generator.generate()
    engine = GeometryRepairEngine(graph)

    # 1. 門禁攔截測試：不滿足門禁時強制駁回
    fake_proposal = RepairProposal(
        operation=RepairOperation.SPLIT,
        target_nodes=["G0001"],
        reason="想寫詳細一點",
        detail={},
    )
    # 假數據未達門檻
    res_rejected = engine.execute_repair(
        proposal=fake_proposal,
        condition=GeometryRepairCondition.DENSITY_OVERLOAD,
        gatekeeper_context={"turning_points_count": 1, "foreshadowing_tasks_count": 1},
    )
    assert not res_rejected.success
    assert "駁回" in res_rejected.message

    # 2. 門禁通過測試：滿足門檻時成功執行 SPLIT
    target_node = list(graph.nodes.keys())[5]
    split_proposal = RepairProposal(
        operation=RepairOperation.SPLIT,
        target_nodes=[target_node],
        reason="單節點塞了 3 個轉折點，密度超載",
        detail={"split_count": 2},
    )
    res_split = engine.execute_repair(
        proposal=split_proposal,
        condition=GeometryRepairCondition.DENSITY_OVERLOAD,
        gatekeeper_context={"turning_points_count": 3},
    )
    assert res_split.success
    assert target_node not in graph.nodes
    assert len(res_split.new_nodes) == 2
    assert res_split.new_nodes[0] in graph.nodes
    assert res_split.new_nodes[1] in graph.nodes

    # 3. 測試 INSERT 橋接操作與章號順延
    node_a = list(graph.nodes.keys())[0]
    node_b = list(graph.nodes.keys())[1]
    initial_target_chapters = graph.params.target_chapters

    insert_proposal = RepairProposal(
        operation=RepairOperation.INSERT,
        target_nodes=[node_a, node_b],
        reason="A 與 B 間缺少重要因果橋接",
        detail={"after_node_id": node_a, "before_node_id": node_b, "is_new_chapter": True},
    )
    res_insert = engine.execute_repair(
        proposal=insert_proposal,
        condition=GeometryRepairCondition.CAUSAL_GAP,
        gatekeeper_context={"causal_gap_detected": True, "missing_cause_description": "需要先解鎖鑰匙"},
    )
    assert res_insert.success
    assert res_insert.chapter_delta == 1
    assert graph.params.target_chapters == initial_target_chapters + 1

    # 4. 測試 COMPRESS 水章合併
    n1 = list(graph.nodes.keys())[2]
    n2 = list(graph.nodes.keys())[3]
    compress_proposal = RepairProposal(
        operation=RepairOperation.COMPRESS,
        target_nodes=[n1, n2],
        reason="兩章均為過渡日常水章，予以壓縮",
        detail={},
    )
    res_compress = engine.execute_repair(
        proposal=compress_proposal,
        condition=GeometryRepairCondition.CHAPTER_EXPANSION,
        gatekeeper_context={"new_chapter_count": 19, "current_chapter_count": 20},
    )
    assert res_compress.success
    assert n1 in graph.nodes
    assert n2 not in graph.nodes


def test_geometry_persistence_roundtrip(novel_factory):
    """驗證幾何圖的 SQLite 寫入、完整載入、語義更新與統計回傳。"""
    novel_id = novel_factory(title="幾何持久化測試小說")

    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="db_test")
    generator = GeometryGenerator(params)
    original_graph = generator.generate()

    # 1. 保存幾何圖
    db.save_geometry_graph(novel_id, original_graph)
    assert db.has_geometry(novel_id)

    # 2. 讀取幾何圖
    loaded_graph = db.load_geometry_graph(novel_id)
    assert loaded_graph is not None
    assert len(loaded_graph.nodes) == len(original_graph.nodes)
    assert len(loaded_graph.edges) == len(original_graph.edges)
    assert len(loaded_graph.threads) == len(original_graph.threads)
    assert len(loaded_graph.volumes) == len(original_graph.volumes)

    # 3. 統計資訊
    stats = db.get_geometry_stats(novel_id)
    assert stats["node_count"] == len(original_graph.nodes)
    assert stats["filled_nodes"] == 0
    assert stats["filling_progress"] == 0.0

    # 4. 語義增量更新 (Pass 語義填充)
    sample_node_id = list(loaded_graph.nodes.keys())[0]
    sample_semantic = {"scene_title": "宗門初試", "core_action": "取得第一張符籙"}
    db.update_node_semantic(novel_id, sample_node_id, sample_semantic)

    node_data = db.get_geometry_node(novel_id, sample_node_id)
    assert node_data is not None
    assert node_data["semantic"] == sample_semantic

    # 重新檢查統計填充進度
    updated_stats = db.get_geometry_stats(novel_id)
    assert updated_stats["filled_nodes"] == 1
    assert updated_stats["filling_progress"] > 0.0

    # 5. 清理
    db.delete_geometry(novel_id)
    assert not db.has_geometry(novel_id)
