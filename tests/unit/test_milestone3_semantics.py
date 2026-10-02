# -*- coding: utf-8 -*-
"""
Milestone 3 Unit Tests: Semantic Topology Stage Activation & Feed-Forward
驗證：
1. 語義拓撲階段就緒檢查函數 (_is_macro_semantic_ready, _is_character_semantic_ready, _is_cross_relation_ready)
2. autonomous_pipeline.py 串接執行順序：geometry -> macro_semantic -> character_semantic -> cross_relation -> volume_skeleton
3. stage_registry.py STAGE_ORDER 順序與 detect_current_stage 階段遞進
4. post_processor.py _build_state_updates 包含幾何統計
5. volume_skeleton/prompts.py 動態注入卷主題、節點位移、邊因果與線程人物綁定
6. GeometryContextCompiler 與 WriterContextBuilder 語義與社交矩陣 feed-forward
"""

import json
import pytest

from backend import persistence as db
from backend.geometry.generator import GeometryGenerator
from backend.geometry.models import (
    GeometryParams,
    GeometryComplexity,
    StructuralRole,
    ThreadType,
    EdgeType,
    VolumeContainer,
    ArcContainer,
    GeometryNode,
    GeometryEdge,
    GeometryThread,
    NodeHierarchy,
)
from backend.services.autonomous_pipeline import (
    AutonomousPipelineManager,
    NovelPipelineTask,
    _is_geometry_ready,
    _is_macro_semantic_ready,
    _is_character_semantic_ready,
    _is_cross_relation_ready,
)
from backend.generation.routing.stage_registry import (
    STAGE_ORDER,
    next_stage,
    previous_stage,
)
from backend.services.diagnostics import detect_current_stage
from backend.generation.orchestration.post_processor import _build_state_updates
from backend.generation.routing.schema import GenerationTaskRequest, GenerationTaskTarget
from backend.agents.volume_skeleton.prompts import build_volume_skeleton_planner_messages
from backend.services.director.context_compiler import GeometryContextCompiler
from backend.services.context.writer_context_builder import WriterContextBuilder


def test_semantic_readiness_checkers(novel_factory):
    """驗證語義階段就緒判定邏輯隨資料寫入逐步點亮。"""
    novel_id = novel_factory(title="語義就緒測試小說")

    # 1. 初始無幾何圖：全為 False
    assert _is_geometry_ready(novel_id) is False
    assert _is_macro_semantic_ready(novel_id) is False
    assert _is_character_semantic_ready(novel_id) is False
    assert _is_cross_relation_ready(novel_id) is False

    # 2. 鋪設基礎幾何圖（無語義）
    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="sem_ready_test")
    generator = GeometryGenerator(params)
    graph = generator.generate()
    db.save_geometry_graph(novel_id, graph)

    assert _is_geometry_ready(novel_id) is True
    # 尚無語義
    assert _is_macro_semantic_ready(novel_id) is False
    assert _is_character_semantic_ready(novel_id) is False
    assert _is_cross_relation_ready(novel_id) is False

    # 3. 填充 Volume 與 Thread 語義 (Pass 1 & Pass 2)
    vol_id = list(graph.volumes.keys())[0]
    thread_id = list(graph.threads.keys())[0]
    db.update_volume_semantic(novel_id, vol_id, {"theme": "凡人逆命", "core_conflict": "神明壓制"})
    db.update_thread_semantic(novel_id, thread_id, {"thread_name": "逆命復仇主線", "core_question": "凡人能否斬神？"})

    assert _is_macro_semantic_ready(novel_id) is True
    assert _is_character_semantic_ready(novel_id) is False
    assert _is_cross_relation_ready(novel_id) is False

    # 4. 填充角色位移與線程綁定 (Pass 3)
    node_id = list(graph.nodes.keys())[0]
    db.update_node_semantic(novel_id, node_id, {
        "focus_character": "林夜",
        "internal_shift": "從自保到承擔救世",
        "dramatic_choice": "燃燒壽元激發禁器",
    })
    db.update_thread_semantic(novel_id, thread_id, {
        "thread_name": "逆命復仇主線",
        "character_binding": {"character_name": "林夜", "arc_theme": "凡人弒神", "flaw_to_overcome": "怯懦"},
    })

    assert _is_character_semantic_ready(novel_id) is True
    assert _is_cross_relation_ready(novel_id) is False

    # 5. 填充跨距邊語義 (Pass 4)
    edge = graph.edges[0]
    db.update_edge_semantic(novel_id, edge.edge_id, {
        "causal_link": "前置禁令破碎，引發本章黑市大暴動",
        "dramatic_clash": "同盟信條徹底破裂",
    })

    assert _is_cross_relation_ready(novel_id) is True


def test_stage_registry_and_detect_current_stage_progression(novel_factory, monkeypatch):
    """驗證 stage_registry 階段排序與 detect_current_stage 依拓撲進度推進。"""
    monkeypatch.setattr("backend.services.diagnostics.report.MIN_FORESHADOWING_SEEDS", 5)
    monkeypatch.setattr("backend.services.diagnostics.report.MIN_KEY_TURNING_POINTS", 5)

    # 1. 驗證 STAGE_ORDER 排序
    expected_order = [
        "worldview",
        "characters",
        "foreshadowing",
        "volumes",
        "geometry",
        "macro_semantic",
        "character_semantic",
        "cross_relation",
        "volume_skeleton",
        "writer",
        "editor",
    ]
    assert STAGE_ORDER == expected_order
    assert next_stage("volumes") == "geometry"
    assert next_stage("geometry") == "macro_semantic"
    assert next_stage("macro_semantic") == "character_semantic"
    assert next_stage("character_semantic") == "cross_relation"
    assert next_stage("cross_relation") == "volume_skeleton"
    assert previous_stage("geometry") == "volumes"
    assert previous_stage("volume_skeleton") == "cross_relation"

    # 2. 驗證 detect_current_stage 推進
    novel_id = novel_factory(title="階段偵測推進小說")
    wb_data = {
        "theme": "逆命破天",
        "main_conflict": "凡人與神明的矛盾",
        "macro_outline": "全書宏觀大綱",
        "worldview": "世界觀核心設定，靈氣復甦與九大陣營體系完整自洽。",
        "foreshadowing_seeds": [{"seed": f"伏筆{i}"} for i in range(1, 10)],
        "key_turning_points": [{"turning_point": f"轉折{i}"} for i in range(1, 10)],
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False))

    chars_data = [
        {"name": "主角林夜", "role": "protagonist", "archetype": "孤勇者"},
        {"name": "反派主祭", "role": "antagonist", "archetype": "狂熱信徒"},
    ]
    db.save_characters(novel_id, chars_data)

    # 尚無分卷
    assert detect_current_stage(novel_id) == "volumes"

    # 建立分卷，但無幾何圖譜
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第一卷", "summary": "初入黑市", "chapter_count": 10}])
    assert detect_current_stage(novel_id) == "geometry"

    # 保存幾何圖譜（未填充語義）
    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="detect_seed")
    graph = GeometryGenerator(params).generate()
    db.save_geometry_graph(novel_id, graph)
    assert detect_current_stage(novel_id) == "macro_semantic"

    # 填充篇卷/線程語義
    vol_id = list(graph.volumes.keys())[0]
    thread_id = list(graph.threads.keys())[0]
    db.update_volume_semantic(novel_id, vol_id, {"theme": "破局"})
    db.update_thread_semantic(novel_id, thread_id, {"thread_name": "主線"})
    assert detect_current_stage(novel_id) == "character_semantic"

    # 填充角色位移語義
    node_id = list(graph.nodes.keys())[0]
    db.update_node_semantic(novel_id, node_id, {"internal_shift": "頓悟"})
    assert detect_current_stage(novel_id) == "cross_relation"

    # 填充跨距邊語義
    for e in graph.edges:
        db.update_edge_semantic(novel_id, e.edge_id, {"causal_link": "因果推動"})
    # 語義全滿，但 chapters_outline 尚未規劃完整骨架細綱 -> 前進至 volume_skeleton
    assert detect_current_stage(novel_id) == "volume_skeleton"


def test_autonomous_pipeline_wiring_executes_semantic_stages(novel_factory):
    """驗證 autonomous_pipeline._run_autonomous_flow 依序調度 macro_semantic, character_semantic, cross_relation。"""
    novel_id = novel_factory(title="自主流水線拓撲語義測試")

    wb_data = {
        "theme": "求道長生",
        "main_conflict": "資源匱乏與宗門兼併",
        "macro_outline": "全書宏觀大綱架構",
        "worldview": "世界觀完整內容，包含天地法則與修行境界設定。",
        "foreshadowing_seeds": [{"seed": f"S{i}"} for i in range(1, 10)],
        "key_turning_points": [{"turning_point": f"T{i}"} for i in range(1, 10)],
    }
    db.save_worldbuilding(novel_id, json.dumps(wb_data, ensure_ascii=False))

    chars = [{"name": f"角色{i}", "role": "主角" if i == 1 else "配角"} for i in range(1, 16)]
    db.save_characters(novel_id, chars)
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第一卷", "summary": "卷概要", "chapter_count": 10}])

    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id, "自主流水線拓撲語義測試")

    executed_stages = []

    def mock_execute_stage(task, stage, task_type="generate", instruction="", user_prompt="", verify_fn=None, target=None):
        executed_stages.append({
            "stage": stage,
            "progress": task.progress_percent,
        })
        if stage == "geometry":
            params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="pipe_test")
            graph = GeometryGenerator(params).generate()
            db.save_geometry_graph(novel_id, graph)
        elif stage == "macro_semantic":
            vols = db.get_geometry_stats(novel_id)
            graph = db.load_geometry_graph(novel_id)
            if graph:
                vol_id = list(graph.volumes.keys())[0]
                thread_id = list(graph.threads.keys())[0]
                db.update_volume_semantic(novel_id, vol_id, {"theme": "宏觀主題"})
                db.update_thread_semantic(novel_id, thread_id, {"thread_name": "主線"})
        elif stage == "character_semantic":
            graph = db.load_geometry_graph(novel_id)
            if graph:
                node_id = list(graph.nodes.keys())[0]
                db.update_node_semantic(novel_id, node_id, {"internal_shift": "位移"})
        elif stage == "cross_relation":
            graph = db.load_geometry_graph(novel_id)
            if graph and graph.edges:
                db.update_edge_semantic(novel_id, graph.edges[0].edge_id, {"causal_link": "因果"})
        elif stage == "volume_skeleton":
            # 停止後續
            task.stop_requested = True

    manager._execute_stage_with_retry = mock_execute_stage

    manager._run_autonomous_flow(task, initial_prompt="測試執行", max_chapters=5)

    stages_called = [s["stage"] for s in executed_stages]
    # 幾何之後必須緊跟三個語義階段
    assert "geometry" in stages_called
    geom_idx = stages_called.index("geometry")
    assert stages_called[geom_idx + 1] == "macro_semantic"
    assert stages_called[geom_idx + 2] == "character_semantic"
    assert stages_called[geom_idx + 3] == "cross_relation"

    # 進度百分比平滑提升
    macro_item = next(s for s in executed_stages if s["stage"] == "macro_semantic")
    char_item = next(s for s in executed_stages if s["stage"] == "character_semantic")
    cross_item = next(s for s in executed_stages if s["stage"] == "cross_relation")
    assert macro_item["progress"] == 38
    assert char_item["progress"] == 39
    assert cross_item["progress"] == 40


def test_post_processor_state_updates_includes_geometry(novel_factory):
    """驗證 post_processor._build_state_updates 在小說擁有幾何圖時包含幾何統計。"""
    novel_id = novel_factory(title="後處理器幾何狀態更新測試")
    req = GenerationTaskRequest(
        novel_id=novel_id,
        stage="macro_semantic",
        task_type="generate",
    )

    # 1. 無幾何圖
    updates_empty = _build_state_updates(req)
    assert "geometry" not in updates_empty

    # 2. 鋪設幾何圖
    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="post_proc_test")
    graph = GeometryGenerator(params).generate()
    db.save_geometry_graph(novel_id, graph)

    updates_with_geom = _build_state_updates(req)
    assert "geometry" in updates_with_geom
    geom_stats = updates_with_geom["geometry"]
    assert geom_stats["node_count"] > 0
    assert "filled_nodes" in geom_stats
    assert "filled_threads" in geom_stats
    assert "filled_edges" in geom_stats
    assert "filled_volumes" in geom_stats


def test_volume_skeleton_planner_messages_feed_forward(novel_factory):
    """驗證 volume_skeleton prompt 注入 VolumeContainer.semantic、node.semantic、edge.semantic 與 character_binding。"""
    novel_id = novel_factory(title="細綱規劃語義FeedForward測試")

    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="skel_ff_test")
    graph = GeometryGenerator(params).generate()

    # 注入篇卷語義
    vol_id = list(graph.volumes.keys())[0]
    graph.volumes[vol_id].semantic = {
        "theme": "絕境重生之破滅與涅槃",
        "core_conflict": "凡俗賤民與九天仙官的不可調和矛盾",
        "climax_turn": "斬仙台崩毀",
    }

    # 注入節點位移語義
    first_node_id = graph.get_chapter_nodes(1)[0].node_id
    graph.nodes[first_node_id].semantic = {
        "focus_character": "林夜",
        "internal_shift": "從自私苟活轉向捨身破局",
        "dramatic_choice": "以命換道，斬斷自身靈脈",
    }

    # 注入邊語義
    in_edges = graph.get_incoming_edges(first_node_id)
    if in_edges:
        in_edges[0].semantic = {"causal_link": "前置盜取道骨的代價爆發"}
    out_edges = graph.get_outgoing_edges(first_node_id)
    if out_edges:
        out_edges[0].semantic = {"causal_link": "引動第二章執法隊的封城追殺"}

    # 注入線程人物綁定
    t_id = graph.nodes[first_node_id].primary_thread
    if t_id and t_id in graph.threads:
        graph.threads[t_id].semantic = {
            "thread_name": "逆道弒仙線",
            "character_binding": {
                "character_name": "林夜",
                "arc_theme": "斬破虛偽仙道",
                "flaw_to_overcome": "對人性的徹底懷疑與孤僻",
            },
        }

    db.save_geometry_graph(novel_id, graph)

    current_vol = {
        "volume_index": 1,
        "title": "破滅卷",
        "summary": "凡人林夜於微末崛起",
        "chapter_count": 10,
    }

    msgs = build_volume_skeleton_planner_messages(
        worldview_text="天道不仁的世界觀",
        volume_index=1,
        current_vol=current_vol,
        start_ch=1,
        end_ch=5,
        vol_chapter_count=5,
        surrounding_context="角色名冊",
        precalc_clues="伏筆列表",
        user_prompt="規劃第1卷第1-5章細綱",
        novel_id=novel_id,
        total_volume_chapters=10,
        vol_start_ch=1,
        vol_end_ch=10,
    )

    prompt_content = msgs[1]["content"]

    # 1. 驗證 VolumeContainer.semantic 注入
    assert "絕境重生之破滅與涅槃" in prompt_content
    assert "凡俗賤民與九天仙官的不可調和矛盾" in prompt_content

    # 2. 驗證 node.semantic (心境位移與代價抉擇) 注入
    assert "從自私苟活轉向捨身破局" in prompt_content
    assert "以命換道，斬斷自身靈脈" in prompt_content
    assert "林夜" in prompt_content

    # 3. 驗證 edge.semantic 邊因果注入
    if in_edges or out_edges:
        assert any(link in prompt_content for link in ("前置盜取道骨的代價爆發", "引動第二章執法隊的封城追殺"))

    # 4. 驗證活躍線程人物綁定注入
    assert "【幾何線程人物綁定與弧線契約 (Active Character Thread Bindings)】" in prompt_content
    assert "斬破虛偽仙道" in prompt_content
    assert "對人性的徹底懷疑與孤僻" in prompt_content


def test_geometry_context_compiler_and_writer_context_feed_forward(novel_factory):
    """驗證 GeometryContextCompiler 與 WriterContextBuilder 的語義與社交矩陣 feed-forward。"""
    novel_id = novel_factory(title="正文組裝語義FeedForward測試")

    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="writer_ff_test")
    graph = GeometryGenerator(params).generate()

    # 篇卷語義
    vol_id = list(graph.volumes.keys())[0]
    graph.volumes[vol_id].semantic = {
        "theme": "暗夜微光",
        "core_conflict": "信念與現實的劇烈撕裂",
    }
    # 弧語義
    if graph.arcs:
        arc_id = list(graph.arcs.keys())[0]
        graph.arcs[arc_id].semantic = {
            "tension_focus": "生死逃亡與背叛邊緣",
        }

    # 節點心境位移
    node_id = graph.get_chapter_nodes(1)[0].node_id
    graph.nodes[node_id].semantic = {
        "focus_character": "林夜",
        "internal_shift": "撕裂童年創傷，直面血色真相",
        "dramatic_choice": "放棄同伴獨自斷後",
    }

    # 線程人物綁定
    primary_t = graph.nodes[node_id].primary_thread
    if primary_t and primary_t in graph.threads:
        graph.threads[primary_t].semantic = {
            "character_binding": {
                "character_name": "林夜",
                "arc_theme": "直面宿命",
                "flaw_to_overcome": "逃避責任",
            }
        }

    db.save_geometry_graph(novel_id, graph)

    # 1. 驗證 GeometryContextCompiler 編譯與 overlay 格式化
    pkg = GeometryContextCompiler.compile(novel_id, chapter_index=1, target_node_id=node_id)
    assert pkg.has_geometry is True
    assert pkg.internal_shift == "撕裂童年創傷，直面血色真相"
    assert pkg.dramatic_choice == "放棄同伴獨自斷後"
    assert pkg.focus_character == "林夜"

    overlay = pkg.format_geometry_overlay()
    assert "【本章核心心境位移與代價】" in overlay
    assert "撕裂童年創傷，直面血色真相" in overlay
    assert "放棄同伴獨自斷後" in overlay

    # 2. 驗證 WriterContextBuilder.build_character_states
    builder = WriterContextBuilder()
    outline = {
        "chapter_index": 1,
        "characters_active": ["林夜", "蘇晚晚"],
        "scene_beats": [{"beat_index": 1, "description": "城門突圍"}],
    }
    bible = {
        "characters": [
            {
                "name": "林夜",
                "role": "主角",
                "want": "活下去",
                "relationships": [
                    {"target": "蘇晚晚", "relation": "生死同伴", "tension": "隱瞞了滅門真相的愧疚"}
                ],
            },
            {
                "name": "蘇晚晚",
                "role": "重要同伴",
                "want": "尋找兄長",
                "relationships": [
                    {"target": "林夜", "relation": "依賴與猜疑", "tension": "察覺林夜眼神中的閃躲"}
                ],
            }
        ]
    }

    states = builder.build_character_states(
        outline, bible, pov_character="林夜", novel_id=novel_id, chapter_index=1
    )
    assert len(states) == 2
    lin_state = next(s for s in states if s["name"] == "林夜")

    # 驗證林夜心境位移與抉擇代價融入私密動機
    assert "【本章心境位移：撕裂童年創傷，直面血色真相】" in lin_state["private_motivation"]
    assert "【面臨抉擇代價：放棄同伴獨自斷後】" in lin_state["private_motivation"]
    assert "【幾何弧線目標：直面宿命】" in lin_state["private_motivation"]
    assert "逃避責任" in lin_state["dynamic_arc_obligation"]

    # 驗證社交矩陣現場關係張力
    assert "relational_tensions" in lin_state
    assert any("蘇晚晚" in t for t in lin_state["relational_tensions"])

    # 3. 驗證 WriterContextBuilder.format_writer_prompt_context
    prompt = builder.format_writer_prompt_context(
        novel_id=novel_id,
        worldview_text="仙凡之隔",
        characters_bible=bible,
        current_outline=outline,
        surrounding_plot="",
        vol_outline_context="",
        clue_payoff_details="",
        custom_style="冷峻肅殺",
        chapter_index=1,
    )

    # 幾何 Overlay 注入
    assert "【本章核心心境位移與代價】" in prompt
    assert "撕裂童年創傷，直面血色真相" in prompt
    # 角色弧線契約與社交張力注入
    assert "幾何弧線契約" in prompt
    assert "直面宿命" in prompt
    assert "現場關係張力 (Social Matrix)" in prompt
    # 篇卷主題與張力焦點注入
    assert "當前卷宏觀主題：暗夜微光" in prompt
    assert "當前卷核心衝突焦點：信念與現實的劇烈撕裂" in prompt
    assert "當前弧線張力焦點：生死逃亡與背叛邊緣" in prompt


def test_semantic_handlers_execution_with_mock_llm(novel_factory, monkeypatch):
    """驗證 macro_semantic, character_semantic, cross_relation handler 端到端調用與資料庫更新。"""
    from backend.generation.routing.router import execute_generation_task

    novel_id = novel_factory(title="語義Handler執行測試")
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第一卷", "summary": "卷概要", "chapter_count": 10}])

    params = GeometryParams(target_chapters=10, volume_count=1, chapters_per_volume=10, seed_for_rng="handler_test")
    graph = GeometryGenerator(params).generate()
    db.save_geometry_graph(novel_id, graph)

    vol_id = list(graph.volumes.keys())[0]
    thread_id = list(graph.threads.keys())[0]
    node_id = list(graph.nodes.keys())[0]
    edge_id = graph.edges[0].edge_id
    arc_id = list(graph.arcs.keys())[0]

    def mock_llm_json(agent_role, messages, **kwargs):
        if agent_role == "volumes":
            return {
                "volumes": {vol_id: {"title": "逆命卷", "summary": "逆命破局", "theme": "反抗", "core_conflict": "神罰"}},
                "arcs": {arc_id: {"tension_focus": "生死逃亡"}}
            }
        elif agent_role == "character":
            return {
                "thread_bindings": {thread_id: {"character_name": "林夜", "arc_theme": "破局", "flaw_to_overcome": "猶豫"}},
                "node_shifts": {node_id: {"focus_character": "林夜", "internal_shift": "決心", "dramatic_choice": "破釜沉舟"}}
            }
        else:
            msg_str = str(messages)
            if "Motif" in msg_str or "causal_link" in msg_str:
                return {
                    "edges": {e.edge_id: {"causal_link": "因果爆發", "dramatic_clash": "同盟決裂"} for e in graph.edges}
                }
            return {
                "threads": {thread_id: {"thread_name": "弒神主線", "core_question": "能否斬神？", "description": "主線"}}
            }

    monkeypatch.setattr("backend.agents.macro_semantic.runner.call_llm_json", mock_llm_json)
    monkeypatch.setattr("backend.agents.character_semantic.runner.call_llm_json", mock_llm_json)
    monkeypatch.setattr("backend.agents.cross_relation.runner.call_llm_json", mock_llm_json)

    # 1. 執行 macro_semantic
    req_macro = GenerationTaskRequest(novel_id=novel_id, stage="macro_semantic", task_type="generate")
    resp_macro = execute_generation_task(req_macro)
    assert resp_macro.status == "completed"
    assert _is_macro_semantic_ready(novel_id) is True

    # 2. 執行 character_semantic
    req_char = GenerationTaskRequest(novel_id=novel_id, stage="character_semantic", task_type="generate")
    resp_char = execute_generation_task(req_char)
    assert resp_char.status == "completed"
    assert _is_character_semantic_ready(novel_id) is True

    # 3. 執行 cross_relation
    req_cross = GenerationTaskRequest(novel_id=novel_id, stage="cross_relation", task_type="generate")
    resp_cross = execute_generation_task(req_cross)
    assert resp_cross.status == "completed"
    assert _is_cross_relation_ready(novel_id) is True
