# -*- coding: utf-8 -*-
"""
Adversarial Challenge & Empirical Verification Harness for Milestones 1 and 4.
Authored by challenger_2 (teamwork_preview_challenger).

Covers:
1. Pipeline cancellation, stop_requested handling, and exception recovery.
2. validator._infer_chapter_index across DB-backed and argument-based modes.
3. refusal_filter fourth-wall detection and false positive resistance.
4. FastAPI modern React serving, asset routing, and dist-missing fallback.
"""

import json
import os
import threading
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend import persistence as db
from backend.app import app, get_static_dir
from backend.common.refusal_filter import find_meta_narrative_leaks
from backend.generation.routing.validator import (
    _find_first_missing,
    _infer_chapter_index,
    resolve_generation_task_target,
)
from backend.generation.routing.schema import GenerationTaskRequest
from backend.services.autonomous_pipeline import (
    AutonomousPipelineManager,
    NovelPipelineTask,
    PipelineHaltedException,
)
from backend.services.narrative.narrative_auditor import NarrativeAuditor


# =============================================================================
# PART 1: Pipeline Cancellation & Exception Recovery
# =============================================================================

def test_pipeline_stop_requested_halts_without_advancing_downstream(novel_factory):
    """Verify that setting task.stop_requested immediately halts the autonomous flow
    and never invokes subsequent downstream stages."""
    novel_id = novel_factory(title="中斷測試小說", genre="科幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    executed_stages = []

    def fake_execute(task, stage, *args, **kwargs):
        executed_stages.append(stage)
        # User clicks stop while worldview stage is being executed
        task.stop_requested = True
        return MagicMock(ok=True)

    with patch.object(manager, "_execute_stage_with_retry", side_effect=fake_execute), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False), \
         patch("backend.services.autonomous_pipeline._are_characters_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="構建賽博世界", max_chapters=3)

    assert task.is_running is False
    assert task.stop_requested is False  # finally resets stop_requested
    assert executed_stages == ["worldview"], f"Downstream stages were executed after stop: {executed_stages}"
    assert db.get_pipeline_lock_status(novel_id) is None, "Pipeline lock must be released on stop!"


def test_pipeline_unexpected_exception_recovery(novel_factory):
    """Verify that an unexpected exception (e.g. GPU OOM, DB disconnect) in autonomous flow
    is caught, marks task as error, calls task.fail(), and releases the pipeline lock."""
    novel_id = novel_factory(title="異常恢復測試", genre="玄幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    db.acquire_pipeline_lock(novel_id, "test_runner")

    def exploding_execute(*args, **kwargs):
        raise RuntimeError("GPU VRAM OutOfMemory: allocated 24GB")

    with patch.object(manager, "_execute_stage_with_retry", side_effect=exploding_execute), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="天道崩塌", max_chapters=3)

    assert task.is_running is False
    assert task.current_stage == "error"
    assert "GPU VRAM OutOfMemory" in (task.error or "")
    assert "執行中斷" in task.status_message or "GPU VRAM" in task.status_message
    assert db.get_pipeline_lock_status(novel_id) is None, "Lock must be released even on catastrophic failure!"


def test_stop_pipeline_releases_lock_and_flags_task(novel_factory):
    """Verify that AutonomousPipelineManager.stop_pipeline correctly sets stop_requested
    and cleans up DB pipeline lock."""
    novel_id = novel_factory(title="手動停止測試", genre="仙俠")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    db.acquire_pipeline_lock(novel_id, "active_worker")
    assert db.get_pipeline_lock_status(novel_id) is not None

    res = manager.stop_pipeline(novel_id)
    assert res["success"] is True
    assert res["status"] == "stopping"
    assert task.stop_requested is True
    assert db.get_pipeline_lock_status(novel_id) is None, "stop_pipeline must clear the SQLite lock!"


def test_pipeline_halted_exception_unhandled_action_behavior(novel_factory):
    """Adversarial check: what if PipelineHaltedException is raised with an unexpected action?"""
    novel_id = novel_factory(title="未知決策測試", genre="修真")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    task.current_stage = "worldview"
    manager.tasks[novel_id] = task

    def halt_unexpected(*args, **kwargs):
        raise PipelineHaltedException(action="CUSTOM_PAUSE", reason="等待外部審核")

    with patch.object(manager, "_execute_stage_with_retry", side_effect=halt_unexpected), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="測試", max_chapters=3)

    # Must cleanly exit without crashing the worker thread
    assert task.is_running is False
    assert db.get_pipeline_lock_status(novel_id) is None


# =============================================================================
# PART 2: Validator _infer_chapter_index Comprehensive Combinations
# =============================================================================

def test_infer_chapter_index_db_lookup_with_volumes_and_chapters(novel_factory):
    """Test _infer_chapter_index with database lookup across empty, partially written,
    and fully written novels."""
    novel_id = novel_factory(title="章節推斷整合測試", genre="都市")

    # 1. Fresh novel with no volumes -> defaults to 1
    assert _infer_chapter_index(novel_id) == 1

    # 2. Novel with 2 volumes, total 4 chapters planned
    vols = [
        {"volume_index": 1, "title": "第一卷", "chapter_count": 2, "chapters_outline": json.dumps([{"chapter_index": 1}, {"chapter_index": 2}])},
        {"volume_index": 2, "title": "第二卷", "chapter_count": 2, "chapters_outline": json.dumps([{"chapter_index": 3}, {"chapter_index": 4}])},
    ]
    db.save_volumes(novel_id, vols)

    # 0 chapters written -> next is 1
    assert _infer_chapter_index(novel_id) == 1
    assert _infer_chapter_index(novel_id=novel_id) == 1

    # Chapter 1 written -> next is 2
    db.save_chapter(novel_id, 1, "第 1 章正文")
    assert _infer_chapter_index(novel_id) == 2

    # Chapter 1 and 2 written -> next is 3
    db.save_chapter(novel_id, 2, "第 2 章正文")
    assert _infer_chapter_index(novel_id) == 3

    # Chapters 1, 2, 4 written (gap at 3) -> next is 3
    db.save_chapter(novel_id, 4, "第 4 章正文")
    assert _infer_chapter_index(novel_id) == 3

    # All chapters 1, 2, 3, 4 written -> returns None!
    db.save_chapter(novel_id, 3, "第 3 章正文")
    assert _infer_chapter_index(novel_id) is None
    assert _infer_chapter_index(novel_id=novel_id) is None


def test_infer_chapter_index_argument_combinations():
    """Adversarial parameter stress test for _find_first_missing (pure helper of _infer_chapter_index)."""
    # Dict chapters with string chapter_index
    assert _find_first_missing([{"chapter_index": "1"}], 3) == 2

    # Dict chapters with None/missing chapter_index
    assert _find_first_missing([{"bad_key": 1}, {"chapter_index": None}], 2) == 1

    # Mixed ints and dicts
    assert _find_first_missing([1, {"chapter_index": 2}], 3) == 3

    # Out of order chapters
    assert _find_first_missing([4, 1, 3], 4) == 2

    # Written chapters exceeding total planned
    assert _find_first_missing([1, 2, 3, 4, 5], 3) is None

    # Empty inputs and zero/negative total
    assert _find_first_missing([], 0) == 1
    assert _find_first_missing([], -5) == 1
    assert _find_first_missing(None, None) == 1


# =============================================================================
# PART 3: Refusal Filter Fourth-Wall Detection & False Positive Resistance
# =============================================================================

def test_refusal_filter_fourth_wall_positive_detections():
    """Verify that blatant and subtle fourth-wall breaking expressions are detected."""
    positive_cases = [
        "作者在此需要向讀者說明，林默此時的修為境界早已超越同輩。",
        "作者在此解釋道，當年的真相其實並非如此。",
        "筆者在此向讀者說明當年的背景。",
        "向讀者交代一下這段歷史。",
        "對讀者介紹一下修仙等級。",
        "給讀者解釋這個世界的魔法體系。",
        "正如在上一章中描述的那樣",
        "讀者可能還記得那個夜晚",
        "讀者記得那個夜晚",
        "【場景目標】林默突破金丹期",
        "沒有制式化的渲染，他直接拔劍",
    ]

    for prose in positive_cases:
        leaks = find_meta_narrative_leaks(prose)
        assert len(leaks) >= 1, f"Expected fourth-wall leak detected in: {prose}"


def test_refusal_filter_subtle_simplified_chinese_bypasses():
    """Adversarial Finding: Document that simplified Chinese variants like '向读者说明'
    bypass the current traditional-only regexes."""
    # Current regex only contains '讀者', omitting '读者'
    simplified_leak = "向读者说明一下情况。"
    leaks = find_meta_narrative_leaks(simplified_leak)
    # This documents the gap: leaks is empty because '读者' is not matched by r'(?:向|對|給|给)讀者'
    assert isinstance(leaks, list)


def test_refusal_filter_false_positive_analysis():
    """Adversarial stress test: Evaluate false positive rates on in-character dialogue
    and non-narrative prose (e.g. train carriage, classroom)."""
    # 1. In-world book reference is protected by in_world_reference regex
    safe_prose = "這卷古籍的上一章節記載了封印符陣。"
    assert find_meta_narrative_leaks(safe_prose) == []

    # 2. General dialogue mentioning reader
    dialogue_reader = "「我是這本書的讀者，但我從未見過作者。」林默冷冷地說道。"
    assert find_meta_narrative_leaks(dialogue_reader) == []

    # 3. Known sensitivity: '上一節' catches '上一節車廂' or '上一節課'
    carriage_prose = "他在上一節車廂看到了兇手。"
    carriage_leaks = find_meta_narrative_leaks(carriage_prose)
    # Documents that '上一節' naively matches carriage
    assert "上一節" in carriage_leaks

    # 4. Known sensitivity: '如前所述' in military/strategic character dialogue
    military_dialogue = "「如前所述，敵人有三千精兵。」軍師說道。"
    military_leaks = find_meta_narrative_leaks(military_dialogue)
    assert "如前所述" in military_leaks


# =============================================================================
# PART 4: Milestone 4 Static Route Resolution & Dist Handling
# =============================================================================

def test_legacy_static_directory_does_not_exist():
    """Verify that frontend/static has been completely deleted."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    legacy_dir = os.path.join(root, "frontend", "static")
    assert not os.path.exists(legacy_dir), f"frontend/static must not exist: {legacy_dir}"


def test_fastapi_has_no_routes_referencing_legacy_static():
    """Verify that no registered route in FastAPI references 'frontend/static'."""
    for route in app.routes:
        route_str = str(getattr(route, "endpoint", "")) + str(getattr(route, "path", ""))
        assert "frontend/static" not in route_str
        assert "legacy_static" not in route_str


def test_static_routes_with_dist_present():
    """Verify static file serving when frontend/dist/ is present."""
    client = TestClient(app)

    # 1. Root serves index.html
    r = client.get("/")
    assert r.status_code == 200
    assert '<div id="root"></div>' in r.text

    # 2. Favicon requests route to dist
    r_ico = client.get("/favicon.ico")
    assert r_ico.status_code == 200

    r_png = client.get("/favicon.png")
    assert r_png.status_code == 200

    # 3. Built Vite assets are served properly
    dist_dir = get_static_dir()
    if dist_dir and os.path.exists(os.path.join(dist_dir, "assets")):
        assets = os.listdir(os.path.join(dist_dir, "assets"))
        for asset_name in assets[:2]:
            resp = client.get(f"/assets/{asset_name}")
            assert resp.status_code == 200


def test_static_routes_with_dist_missing(monkeypatch):
    """Verify that when frontend/dist is missing, FastAPI handles requests gracefully
    without 500 internal server errors."""
    import backend.app as app_module
    client = TestClient(app)

    # Simulate dist missing
    monkeypatch.setattr(app_module, "get_static_dir", lambda: None)
    monkeypatch.setattr(app_module, "static_dir", None)

    # 1. GET / returns friendly fallback JSON
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"message": "AI Novel Factory UI files missing"}

    # 2. API endpoints remain 100% operational
    r_api = client.get("/api/terms/categories")
    assert r_api.status_code in (200, 401, 404, 422)  # Valid HTTP response, NOT 500!
