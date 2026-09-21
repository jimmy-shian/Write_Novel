# -*- coding: utf-8 -*-
"""
敘事幾何 API 端點單元測試 (Geometry API Endpoints Test)
驗證：
1. GET /api/novels/{novel_id}/geometry - 幾何圖譜全景或章節切片查詢
2. GET /api/novels/{novel_id}/geometry/stats - 統計與語義填充進度
3. POST /api/novels/{novel_id}/geometry/generate - 手動重新生成幾何圖
4. POST /api/novels/{novel_id}/geometry/repair - 執行幾何修復操作
5. PATCH /api/novels/{novel_id}/geometry/nodes/{node_id}/semantic - 單節點語義增量更新
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend import persistence as db

client = TestClient(app)


def test_geometry_api_lifecycle(novel_factory):
    novel_id = novel_factory(title="幾何 API 測試小說")

    # 1. 尚未生成幾何圖時查詢
    res_empty = client.get(f"/api/novels/{novel_id}/geometry")
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["has_geometry"] is False
    assert len(data_empty["nodes"]) == 0

    # 2. 觸發手動幾何圖生成
    gen_payload = {
        "target_chapters": 20,
        "volume_count": 1,
        "complexity": "STANDARD",
        "main_thread_count": 2,
        "subplot_count": 4,
    }
    res_gen = client.post(f"/api/novels/{novel_id}/geometry/generate", json=gen_payload)
    assert res_gen.status_code == 200
    assert res_gen.json()["status"] == "success"

    # 3. 驗證幾何圖讀取
    res_graph = client.get(f"/api/novels/{novel_id}/geometry")
    assert res_graph.status_code == 200
    graph_data = res_graph.json()
    assert graph_data["has_geometry"] is True
    assert len(graph_data["nodes"]) > 0
    assert len(graph_data["edges"]) > 0
    assert len(graph_data["threads"]) >= 2

    # 4. 驗證統計端點
    res_stats = client.get(f"/api/novels/{novel_id}/geometry/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["node_count"] == len(graph_data["nodes"])
    assert stats["filling_progress"] == 0.0

    # 5. 驗證單節點語義 PATCH 更新
    sample_node_id = graph_data["nodes"][0]["node_id"]
    patch_semantic = {
        "scene_title": "山門試煉",
        "core_action": "一劍破開幻陣",
    }
    res_patch = client.patch(
        f"/api/novels/{novel_id}/geometry/nodes/{sample_node_id}/semantic",
        json=patch_semantic,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "success"

    # 再次查詢統計，填充進度應增加
    res_stats_after = client.get(f"/api/novels/{novel_id}/geometry/stats")
    assert res_stats_after.json()["filled_nodes"] == 1
    assert res_stats_after.json()["filling_progress"] > 0.0

    # 6. 驗證幾何修復端點 (repair)
    repair_payload = {
        "operation": "SPLIT",
        "condition": "DENSITY_OVERLOAD",
        "target_nodes": [sample_node_id],
        "reason": "單節點轉折過多",
        "detail": {"split_count": 2},
        "gatekeeper_context": {"turning_points_count": 3},
    }
    res_repair = client.post(f"/api/novels/{novel_id}/geometry/repair", json=repair_payload)
    assert res_repair.status_code == 200
    repair_result = res_repair.json()
    assert repair_result["success"] is True
    assert len(repair_result["new_nodes"]) == 2
