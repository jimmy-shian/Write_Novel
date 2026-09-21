# -*- coding: utf-8 -*-
"""
總監上下文編譯器與幾何修復工具單元測試 (Director Context Compiler & Repair Tests)
驗證：
1. GeometryContextCompiler 輸出合規的 6 層結構化上下文包裹 (Layer 3 & 4)
2. WriterContextBuilder 正確注入幾何結構角色義務與跨距線程交織
3. Director 工具 repair_story_geometry 執行門禁判定並成功重構幾何拓撲
"""

import json
import pytest

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import GeometryParams
from backend.generation.orchestration.context_builder import build_generation_context
from backend.generation.routing.schema import GenerationTaskOptions, GenerationTaskRequest
from backend.services.context.writer_context_builder import WriterContextBuilder
from backend.services.director.context_compiler import GeometryContextCompiler
from backend.services.director.tools import repair_story_geometry


def test_context_compiler_and_writer_prompt_injection(novel_factory):
    novel_id = novel_factory(title="上下文編譯測試小說")

    # 1. 生成幾何圖譜
    params = GeometryParams(target_chapters=30, volume_count=1, chapters_per_volume=30, seed_for_rng="compiler_test")
    generator = GeometryGenerator(params)
    graph = generator.generate()
    db.save_geometry_graph(novel_id, graph)

    # 2. 測試 GeometryContextCompiler
    pkg = GeometryContextCompiler.compile(novel_id, chapter_index=5)
    assert pkg.has_geometry
    assert pkg.structural_role != ""
    assert pkg.role_obligation != ""

    overlay_text = pkg.format_geometry_overlay()
    assert "幾何結構角色與敘事義務" in overlay_text
    assert pkg.structural_role in overlay_text

    # 3. 測試 WriterContextBuilder 注入幾何疊加層
    wb_data = {
        "worldview": "高武修真大世界",
        "power_system": "練氣、築基、金丹",
        "theme": "意志與宿命的抗爭",
        "main_conflict": "宗族腐朽",
        "macro_outline": "主角破關而出，重定乾坤。",
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False))

    current_outline = {
        "chapter_index": 5,
        "title": "密林突圍",
        "scene_beats": ["遭遇三名刺客伏擊", "激發初階符籙反殺", "發現暗殺令帶有家族族徽"],
        "scene_contract": {
            "pov_character": "葉辰",
            "narrative_mode": "third_person_limited",
            "narrative_distance": "close",
            "scene_goal": "活著穿過密林",
            "conflict": "刺客佈下殺陣",
            "turn": "認出領頭者隨身攜帶的玉佩",
            "outcome": "重傷突圍，得知暗殺背後是二長老指使",
        },
    }

    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=novel_id,
        worldview_text=wb_data["worldview"],
        characters_bible=[],
        current_outline=current_outline,
        surrounding_plot="",
        vol_outline_context="",
        clue_payoff_details="",
        custom_style="",
        chapter_index=5,
    )

    assert "幾何結構角色與敘事義務" in prompt
    assert pkg.structural_role in prompt

    # 4. 測試 build_generation_context 包含 geometry bundle
    req = GenerationTaskRequest(
        novel_id=novel_id,
        stage="writer",
        task_type="generate",
        scope="chapter",
        options=GenerationTaskOptions(stream=False),
    )
    req.target.chapter_index = 5

    ctx = build_generation_context(req)
    assert "geometry" in ctx
    assert ctx["geometry"]["has_geometry"] is True
    assert ctx["geometry"]["structural_role"] == pkg.structural_role


def test_director_geometry_repair_tool(novel_factory):
    novel_id = novel_factory(title="總監幾何修復工具測試小說")

    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="repair_tool_test")
    generator = GeometryGenerator(params)
    graph = generator.generate()
    db.save_geometry_graph(novel_id, graph)

    target_node = list(graph.nodes.keys())[3]

    # 1. 門禁攔截：數據不符門檻時被拒
    res_rejected = repair_story_geometry(
        novel_id=novel_id,
        operation="SPLIT",
        condition="DENSITY_OVERLOAD",
        target_nodes=[target_node],
        reason="想展開",
        detail={"split_count": 2},
        gatekeeper_context={"turning_points_count": 1},
    )
    assert res_rejected["success"] is False
    assert "駁回" in res_rejected["message"]

    # 2. 門禁通過：滿足門檻時成功執行並同步更新資料庫
    res_success = repair_story_geometry(
        novel_id=novel_id,
        operation="SPLIT",
        condition="DENSITY_OVERLOAD",
        target_nodes=[target_node],
        reason="單節點塞了 3 個轉折點，密度超載",
        detail={"split_count": 2},
        gatekeeper_context={"turning_points_count": 3},
    )
    assert res_success["success"] is True
    assert target_node in res_success["removed_nodes"]
    assert len(res_success["new_nodes"]) == 2

    # 驗證資料庫已同步更新
    reloaded_graph = db.load_geometry_graph(novel_id)
    assert target_node not in reloaded_graph.nodes
    assert res_success["new_nodes"][0] in reloaded_graph.nodes
    assert res_success["new_nodes"][1] in reloaded_graph.nodes
