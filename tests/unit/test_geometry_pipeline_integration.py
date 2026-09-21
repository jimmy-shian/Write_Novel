# -*- coding: utf-8 -*-
"""
幾何管線整合測試 (Geometry Pipeline Integration Tests)
驗證：
1. run_geometry_task 接收 GenerationTaskRequest，成功串流生成 GeometryGraph 並保存至資料庫
2. blueprint.py 在存在幾何圖時，自動切換至 build_blueprint_from_geometry
3. 章節任務映射 (build_canonical_foreshadowing_task_map) 正確繼承幾何結構邊
"""

import json
import pytest

from backend import persistence as db
from backend.generation.handlers.geometry_handler import run_geometry_task
from backend.generation.routing.schema import GenerationTaskOptions, GenerationTaskRequest
from backend.services.foreshadowing.blueprint import (
    build_canonical_foreshadowing_task_map,
    get_global_foreshadowing_blueprint,
)


def test_geometry_task_handler_and_blueprint_integration(novel_factory):
    novel_id = novel_factory(title="幾何管線整合測試小說")

    # 1. 設置基本世界觀（包含伏筆種子與轉折點）
    sample_seeds = [{"id": i, "name": f"伏筆種子_{i}", "description": "秘密"} for i in range(1, 11)]
    sample_turns = [{"id": i, "turning_point_name": f"大轉折_{i}", "description": "突變"} for i in range(1, 6)]
    wb_data = {
        "theme": "逆天改命",
        "main_conflict": "宗門內鬥",
        "worldview": "修真大世界",
        "macro_outline": "主角自微末崛起，破除古宗陰謀，最終登臨大道絕巔。",
        "foreshadowing_seeds": sample_seeds,
        "key_turning_points": sample_turns,
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False))

    # 2. 透過 run_geometry_task 執行幾何生成
    task = GenerationTaskRequest(
        novel_id=novel_id,
        stage="geometry",
        task_type="generate",
        scope="global",
        options=GenerationTaskOptions(stream=True),
    )

    generator = run_geometry_task(task)
    events = list(generator)
    assert len(events) >= 3
    assert any("[DONE]" in ev for ev in events)

    # 3. 驗證資料庫中幾何圖譜已正確生成
    assert db.has_geometry(novel_id)
    stats = db.get_geometry_stats(novel_id)
    assert stats["node_count"] > 0
    assert stats["edge_count"] > 0

    # 4. 驗證伏筆藍圖成功從幾何圖譜中提取
    blueprint = get_global_foreshadowing_blueprint(novel_id)
    assert blueprint is not None
    assert len(blueprint["foreshadowing_allocations"]) == len(sample_seeds)
    assert len(blueprint["turning_allocations"]) == len(sample_turns)

    # 5. 驗證任務分配映射表 (task map) 正確解析出伏筆種植與回收章節
    task_map = build_canonical_foreshadowing_task_map(novel_id)
    assert len(task_map) > 0
    has_plant = any(len(t["foreshadowing_plants"]) > 0 for t in task_map.values())
    has_payoff = any(len(t["foreshadowing_payoffs"]) > 0 for t in task_map.values())
    has_turn = any(len(t["turning_points"]) > 0 for t in task_map.values())
    assert has_plant
    assert has_payoff
    assert has_turn
