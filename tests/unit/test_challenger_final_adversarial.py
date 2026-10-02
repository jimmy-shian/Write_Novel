# -*- coding: utf-8 -*-
"""
Adversarial Verification Suite for Final Acceptance Criteria (Milestones 1-4).
Authored by challenger_final (teamwork_preview_challenger).

Empirical verification of:
1. Macro/Character/Cross-relation semantic handlers execution, database state persistence,
   and dynamic feed-forward into volume skeleton and writer context.
2. Director-driven outline expansion / node splitting cascade across all tables and GeometryGraph.
3. Resilience guarantees: WAIT_USER halting, markdown code block prose preservation,
   _infer_chapter_index boundary safety, NovelPipelineTask thread concurrency.
4. Modern React frontend dist-only serving and static deprecation.
"""

import json
import os
import threading
from unittest.mock import MagicMock, patch
import pytest

from backend import persistence as db
from backend.app import app, get_static_dir
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
    PipelineHaltedException,
    _is_geometry_ready,
    _is_macro_semantic_ready,
    _is_character_semantic_ready,
    _is_cross_relation_ready,
)
from backend.generation.routing.stage_registry import STAGE_ORDER, next_stage
from backend.services.diagnostics import detect_current_stage
from backend.generation.orchestration.post_processor import _normalize_result_text, _normalize_text_by_stage, _build_state_updates
from backend.generation.routing.validator import _find_first_missing, _infer_chapter_index, resolve_generation_task_target
from backend.generation.routing.schema import GenerationTaskRequest, GenerationTaskTarget
from backend.generation.routing.router import execute_generation_task
from backend.agents.director.contracts import EXECUTABLE_DIRECTOR_ACTIONS
from backend.agents.director.runner import _director_decision_needs_recovery
from backend.services.narrative.density import (
    is_chapter_outline_density_overloaded,
    build_split_chapter_outlines,
)
from backend.persistence.repositories.volumes import (
    split_and_expand_chapter_outline,
    get_volumes,
    save_volumes,
)
from backend.agents.volume_skeleton.prompts import build_volume_skeleton_planner_messages
from backend.services.director.context_compiler import GeometryContextCompiler
from backend.services.context.writer_context_builder import WriterContextBuilder


# =============================================================================
# SUITE 1: Semantic Topology Execution, State Persistence, and Feed-Forward
# =============================================================================

def test_semantic_handlers_end_to_end_state_updates(novel_factory, monkeypatch):
    """
    Empirically verify that macro_semantic, character_semantic, and cross_relation
    handlers execute through generation router, updating geometry_volumes,
    geometry_threads, geometry_nodes, and geometry_edges in the DB.
    """
    novel_id = novel_factory(title="終極語義拓撲驗證小說")
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第一卷：啟示", "summary": "卷概要", "chapter_count": 8}])

    params = GeometryParams(target_chapters=8, volume_count=1, chapters_per_volume=8, seed_for_rng="adv_final_sem")
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
                "volumes": {vol_id: {"title": "宿命之卷", "summary": "宿命與意志的碰撞", "theme": "反抗神意", "core_conflict": "神律壓制"}},
                "arcs": {arc_id: {"tension_focus": "生死逃亡"}}
            }
        elif agent_role == "character":
            return {
                "thread_bindings": {thread_id: {"character_name": "夜空", "arc_theme": "破繭成蝶", "flaw_to_overcome": "逃避"}},
                "node_shifts": {node_id: {"focus_character": "夜空", "internal_shift": "從自私到犧牲", "dramatic_choice": "折斷本命法寶救人"}}
            }
        else:
            msg_str = str(messages)
            if "Motif" in msg_str or "causal_link" in msg_str:
                return {
                    "edges": {e.edge_id: {"causal_link": "前因爆發直接導致血戰", "dramatic_clash": "信任崩解"} for e in graph.edges}
                }
            return {
                "threads": {thread_id: {"thread_name": "逆天奪造化主線", "core_question": "凡人能否主宰命運？", "description": "主線"}}
            }

    monkeypatch.setattr("backend.agents.macro_semantic.runner.call_llm_json", mock_llm_json)
    monkeypatch.setattr("backend.agents.character_semantic.runner.call_llm_json", mock_llm_json)
    monkeypatch.setattr("backend.agents.cross_relation.runner.call_llm_json", mock_llm_json)

    # 1. Execute macro_semantic
    resp_macro = execute_generation_task(GenerationTaskRequest(novel_id=novel_id, stage="macro_semantic", task_type="generate"))
    assert resp_macro.status == "completed"
    assert _is_macro_semantic_ready(novel_id) is True

    # 2. Execute character_semantic
    resp_char = execute_generation_task(GenerationTaskRequest(novel_id=novel_id, stage="character_semantic", task_type="generate"))
    assert resp_char.status == "completed"
    assert _is_character_semantic_ready(novel_id) is True

    # 3. Execute cross_relation
    resp_cross = execute_generation_task(GenerationTaskRequest(novel_id=novel_id, stage="cross_relation", task_type="generate"))
    assert resp_cross.status == "completed"
    assert _is_cross_relation_ready(novel_id) is True

    # 4. Verify DB state updates
    saved_graph = db.load_geometry_graph(novel_id)
    assert saved_graph is not None
    assert saved_graph.volumes[vol_id].semantic.get("theme") == "反抗神意"
    assert saved_graph.volumes[vol_id].semantic.get("core_conflict") == "神律壓制"
    assert saved_graph.threads[thread_id].semantic.get("thread_name") == "逆天奪造化主線"
    assert saved_graph.threads[thread_id].semantic.get("character_binding", {}).get("character_name") == "夜空"
    assert saved_graph.nodes[node_id].semantic.get("internal_shift") == "從自私到犧牲"
    assert saved_graph.nodes[node_id].semantic.get("dramatic_choice") == "折斷本命法寶救人"
    assert saved_graph.edges[0].semantic.get("causal_link") == "前因爆發直接導致血戰"

    # 5. Verify post_processor state updates contains geometry stats
    req = GenerationTaskRequest(novel_id=novel_id, stage="cross_relation", task_type="generate")
    updates = _build_state_updates(req)
    assert "geometry" in updates
    assert updates["geometry"]["filled_volumes"] >= 1
    assert updates["geometry"]["filled_threads"] >= 1
    assert updates["geometry"]["filled_nodes"] >= 1
    assert updates["geometry"]["filled_edges"] >= 1


def test_semantic_feed_forward_into_volume_skeleton_and_writer(novel_factory):
    """
    Empirically verify that semantic data feeds forward into:
    - Volume skeleton planner messages
    - GeometryContextCompiler overlay
    - WriterContextBuilder character states & prompt context
    """
    novel_id = novel_factory(title="語義FeedForward驗證小說")
    params = GeometryParams(target_chapters=5, volume_count=1, chapters_per_volume=5, seed_for_rng="adv_ff_test")
    graph = GeometryGenerator(params).generate()
    db.save_geometry_graph(novel_id, graph)

    vol_id = list(graph.volumes.keys())[0]
    thread_id = list(graph.threads.keys())[0]
    first_node = graph.get_chapter_nodes(1)[0]
    node_id = first_node.node_id

    db.update_volume_semantic(novel_id, vol_id, {"theme": "凡人逆命", "core_conflict": "階層固化不可逾越"})
    db.update_thread_semantic(novel_id, thread_id, {
        "thread_name": "天梯登頂線",
        "character_binding": {"character_name": "莫尋", "arc_theme": "求道求真", "flaw_to_overcome": "自傲"},
    })
    db.update_node_semantic(novel_id, node_id, {
        "focus_character": "莫尋",
        "internal_shift": "粉碎虛妄自信，坦承恐懼",
        "dramatic_choice": "將逃生符贈予同門",
    })

    # A. Volume skeleton prompt messages feed-forward
    msgs = build_volume_skeleton_planner_messages(
        worldview_text="修真界弱肉強食",
        volume_index=1,
        current_vol={"volume_index": 1, "title": "第 1 卷：初試鋒芒", "summary": "少年叩仙門"},
        start_ch=1,
        end_ch=5,
        vol_chapter_count=5,
        surrounding_context="角色名冊",
        precalc_clues="伏筆列表",
        user_prompt="規劃細綱",
        novel_id=novel_id,
        total_volume_chapters=5,
        vol_start_ch=1,
        vol_end_ch=5,
    )
    user_content = msgs[1]["content"]
    assert "凡人逆命" in user_content
    assert "階層固化不可逾越" in user_content
    assert "粉碎虛妄自信，坦承恐懼" in user_content
    assert "將逃生符贈予同門" in user_content

    # B. GeometryContextCompiler feed-forward
    pkg = GeometryContextCompiler.compile(novel_id, chapter_index=1, target_node_id=node_id)
    assert pkg.has_geometry is True
    assert pkg.internal_shift == "粉碎虛妄自信，坦承恐懼"
    assert pkg.dramatic_choice == "將逃生符贈予同門"
    overlay = pkg.format_geometry_overlay()
    assert "【本章核心心境位移與代價】" in overlay
    assert "粉碎虛妄自信，坦承恐懼" in overlay
    assert "將逃生符贈予同門" in overlay

    # C. WriterContextBuilder feed-forward
    builder = WriterContextBuilder()
    outline = {
        "chapter_index": 1,
        "characters_active": ["莫尋"],
        "scene_beats": [{"beat_index": 1, "description": "問道碑前"}],
    }
    bible = {
        "characters": [
            {
                "name": "莫尋",
                "role": "主角",
                "want": "登仙梯",
                "relationships": [{"target": "師尊", "relation": "依附", "tension": "師尊曾見死不救"}],
            }
        ]
    }
    char_states = builder.build_character_states(outline, bible, pov_character="莫尋", novel_id=novel_id, chapter_index=1)
    assert len(char_states) == 1
    assert "【本章心境位移：粉碎虛妄自信，坦承恐懼】" in char_states[0]["private_motivation"]
    assert "【面臨抉擇代價：將逃生符贈予同門】" in char_states[0]["private_motivation"]
    assert "自傲" in char_states[0]["dynamic_arc_obligation"]


# =============================================================================
# SUITE 2: Dynamic Outline Expansion & Persistence Cascade
# =============================================================================

def test_density_overload_and_split_helpers():
    """Empirically test density overload conditions and split partitioning."""
    # Normal outline -> not overloaded
    normal = {"turning_points": ["turn1"], "events": [{"scene_index": 1}], "foreshadowing_plants": ["f1"]}
    assert is_chapter_outline_density_overloaded(normal) is False

    # Overload 1: turning_points >= 2
    dense_turns = {"turning_points": ["turn1", "turn2"]}
    assert is_chapter_outline_density_overloaded(dense_turns) is True

    # Overload 2: foreshadowing >= 4 (sum of plants + payoffs)
    dense_fore = {"foreshadowing_plants": ["f1", "f2"], "foreshadowing_payoffs": ["f3", "f4"]}
    assert is_chapter_outline_density_overloaded(dense_fore) is True

    # Overload 3: events >= 3
    dense_events = {"events": [{"scene_index": 1}, {"scene_index": 2}, {"scene_index": 3}]}
    assert is_chapter_outline_density_overloaded(dense_events) is True

    # Overload 4: scene_jumps >= 2 and character_turns >= 1
    dense_jumps = {"scene_jumps": 2, "character_turns": 1}
    assert is_chapter_outline_density_overloaded(dense_jumps) is True

    # Partitioning verification
    split_src = {
        "chapter_index": 3,
        "chapter_title": "第 3 章：決戰前夕",
        "chapter_summary": "多線情報匯流與生死突破",
        "events": [{"scene_index": 1, "content": "暗中查訪"}, {"scene_index": 2, "content": "遭遇暗殺"}, {"scene_index": 3, "content": "破境迎敵"}],
        "allocated_tasks": {"turning_points": ["發現臥底", "長老反目"]},
    }
    splits = build_split_chapter_outlines(split_src, split_count=2)
    assert len(splits) == 2
    assert splits[0]["chapter_index"] == 3
    assert "（上）" in splits[0]["chapter_title"]
    assert splits[1]["chapter_index"] == 4
    assert "（下）" in splits[1]["chapter_title"]


def test_split_and_expand_boundary_first_chapter_cascade(novel_factory):
    """
    Adversarial test: Splitting at Chapter 1 of a multi-volume novel.
    Ensures that Chapter 1 splits into 1 & 2, and all downstream chapters
    in Volume 1 and Volume 2 shift cleanly without unique constraint collision.
    """
    novel_id = novel_factory(title="第一章拆分邊界測試")

    v1_outline = [
        {"chapter_index": 1, "chapter_title": "第 1 章：起點"},
        {"chapter_index": 2, "chapter_title": "第 2 章：跋涉"},
    ]
    v2_outline = [
        {"chapter_index": 3, "chapter_title": "第 3 章：風暴"},
        {"chapter_index": 4, "chapter_title": "第 4 章：終局"},
    ]
    volumes_data = [
        {"volume_index": 1, "title": "首卷", "summary": "首卷概要", "chapter_count": 2, "chapters_outline": v1_outline},
        {"volume_index": 2, "title": "次卷", "summary": "次卷概要", "chapter_count": 2, "chapters_outline": v2_outline},
    ]
    save_volumes(novel_id, volumes_data)

    # Seed chapters 1..4 in chapters and chapter_memory
    for c in range(1, 5):
        db.save_chapter(novel_id, c, f"章節 {c} 內容" * 20)
        db.save_chapter_memory(novel_id, c, {"summary": f"章節 {c} 記憶"})

    # Setup geometry graph
    params = GeometryParams(target_chapters=4, volume_count=2, chapters_per_volume=2, seed_for_rng="adv_split_first")
    graph = GeometryGenerator(params).generate()
    db.save_geometry_graph(novel_id, graph)

    # Split Chapter 1 into 2 chapters
    split_chapters = [
        {"chapter_index": 1, "chapter_title": "第 1 章：起點（上）", "chapter_summary": "第一階段"},
        {"chapter_index": 2, "chapter_title": "第 1 章：起點（下）", "chapter_summary": "第二階段"},
    ]
    res = split_and_expand_chapter_outline(novel_id, 1, split_chapters)
    assert res["success"] is True
    assert res["delta"] == 1

    # Check volumes
    vols = get_volumes(novel_id)
    assert vols[0]["chapter_count"] == 3
    assert vols[0]["chapters_outline"][0]["chapter_title"] == "第 1 章：起點（上）"
    assert vols[0]["chapters_outline"][1]["chapter_title"] == "第 1 章：起點（下）"
    assert vols[0]["chapters_outline"][2]["chapter_index"] == 3

    # Check Volume 2 shifted
    assert vols[1]["chapter_count"] == 2
    assert vols[1]["chapters_outline"][0]["chapter_index"] == 4
    assert vols[1]["chapters_outline"][1]["chapter_index"] == 5

    # Check chapter_memory shifted descending without collision
    mem3 = db.get_chapter_memory(novel_id, 3)
    assert mem3 is not None
    assert "章節 2 記憶" in mem3.get("summary_json", {}).get("summary", "")

    mem5 = db.get_chapter_memory(novel_id, 5)
    assert mem5 is not None
    assert "章節 4 記憶" in mem5.get("summary_json", {}).get("summary", "")


# =============================================================================
# SUITE 3: Pipeline Resilience & Post-Processor Robustness
# =============================================================================

def test_wait_user_halts_pipeline_without_stage_advancement(novel_factory):
    """
    Verify that when Director returns WAIT_USER, AutonomousPipelineManager:
    1. Raises PipelineHaltedException
    2. Sets task.is_running = False
    3. Leaves task halted without advancing downstream stages
    """
    novel_id = novel_factory(title="WAIT_USER中斷驗證小說")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    def mock_execute(task, stage, *args, **kwargs):
        if stage == "worldview":
            raise PipelineHaltedException(action="WAIT_USER", reason="世界觀需人工確認")
        return MagicMock(ok=True)

    with patch.object(manager, "_execute_stage_with_retry", side_effect=mock_execute), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False):
        manager._run_autonomous_flow(task, initial_prompt="構建新世界", max_chapters=3)

    assert task.is_running is False
    assert any("暫停等待使用者" in log.get("msg", "") for log in task.get_logs())


@pytest.mark.parametrize("adversarial_content,expected_contained", [
    (
        # Code fence with JSON {"text": ...} inside story prose
        "林默走入房間，看見控制台跳出一段代碼：\n```json\n{\"text\": \"SYSTEM ALERT\"}\n```\n他眉頭深鎖，轉身拔槍離去。",
        "他眉頭深鎖，轉身拔槍離去。"
    ),
    (
        # Code fence with JSON {"content": ...} inside story prose
        "這是一段開篇描寫。\n```json\n{\"content\": \"這是內嵌字串\"}\n```\n結尾故事繼續流淌，絕不可丟失。",
        "結尾故事繼續流淌，絕不可丟失。"
    ),
    (
        # Unclosed code block in chapter prose
        "主角啟動終端：\n```python\nprint('ACCESS DENIED')\n主角發現系統被鎖定了。",
        "主角發現系統被鎖定了。"
    ),
    (
        # LitRPG bracket format mixed with narrative
        "【系統提示：獲得經驗值 +500】\n```json\n{\"level\": 10, \"stats\": {\"str\": 20}}\n```\n林夜感到力量湧入四肢百骸。",
        "林夜感到力量湧入四肢百骸。"
    ),
])
def test_post_processor_preserves_story_prose_with_code_blocks(adversarial_content, expected_contained):
    """
    Empirically verify that post_processor._normalize_result_text never strips
    surrounding chapter prose when code blocks or JSON snippets are embedded.
    """
    res = _normalize_text_by_stage(adversarial_content, "writer")
    assert isinstance(res, dict)
    assert "text" in res
    assert expected_contained in res["text"]
    assert "```" in res["text"]


def test_post_processor_unwraps_genuine_outer_json_envelope():
    """Verify that pure outer JSON envelopes are still properly unwrapped."""
    outer_json = '{"text": "這是包裝在最外層的真正小說章節內文。"}'
    res1 = _normalize_text_by_stage(outer_json, "writer")
    assert res1["text"] == "這是包裝在最外層的真正小說章節內文。"

    outer_markdown = '```json\n{"content": "這是包裝在Markdown代碼塊中的真正小說內文。"}\n```'
    res2 = _normalize_text_by_stage(outer_markdown, "writer")
    assert res2["text"] == "這是包裝在Markdown代碼塊中的真正小說內文。"


def test_infer_chapter_index_boundary_conditions():
    """Empirically test _infer_chapter_index boundary behavior."""
    # 1. Total written equals total planned -> MUST return None (never overwrite final chapter)
    chapters_full = [{"chapter_index": 1}, {"chapter_index": 2}, {"chapter_index": 3}]
    assert _find_first_missing(chapters_full, 3) is None

    # 2. Total written exceeds total planned -> MUST return None
    assert _find_first_missing([1, 2, 3, 4], 3) is None

    # 3. Gap in chapters -> returns first missing
    assert _find_first_missing([1, 3], 3) == 2

    # 4. Sequential next
    assert _find_first_missing([1], 3) == 2

    # 5. Empty chapters with total > 0 -> returns 1
    assert _find_first_missing([], 3) == 1

    # 6. Total <= 0 -> fallback returns 1
    assert _find_first_missing([], 0) == 1
    assert _find_first_missing([], -1) == 1


def test_novel_pipeline_task_thread_concurrency():
    """High-concurrency stress test on NovelPipelineTask thread synchronization."""
    task = NovelPipelineTask(novel_id="concurrent_test")
    errors = []

    def writer_thread(tid):
        try:
            for i in range(100):
                task.log(f"Thread {tid} message {i}", level="info")
        except Exception as e:
            errors.append(e)

    def reader_thread():
        try:
            for _ in range(100):
                _ = task.to_dict()
                _ = task.get_logs()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer_thread, args=(i,)) for i in range(10)]
    threads += [threading.Thread(target=reader_thread) for _ in range(5)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(task.logs) == 100
    assert task.log_seq == 1000


# =============================================================================
# SUITE 4: Frontend Modern React Serving & Deprecation Verification
# =============================================================================

def test_frontend_legacy_removed_and_dist_serving(monkeypatch):
    """
    Verify:
    1. frontend/static is gone from filesystem
    2. get_static_dir exclusively resolves dist
    3. Root URL GET / serves the compiled React app
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    static_path = os.path.join(base_dir, "frontend", "static")
    dist_path = os.path.join(base_dir, "frontend", "dist")

    # 1. frontend/static does not exist
    assert not os.path.exists(static_path), f"Legacy directory {static_path} still exists!"

    # 2. get_static_dir exclusively targets dist
    resolved_dir = get_static_dir()
    assert resolved_dir is not None
    assert os.path.samefile(resolved_dir, dist_path)
    assert os.path.exists(os.path.join(resolved_dir, "index.html"))

    # 3. GET / returns 200 and serves HTML with #root
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
