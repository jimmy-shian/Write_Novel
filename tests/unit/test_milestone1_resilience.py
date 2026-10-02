# -*- coding: utf-8 -*-
"""
Unit tests for Milestone 1: Pipeline Resilience & Bug Fixes.

Covers:
1. autonomous_pipeline.py: Director WAIT_USER/FINISH halting via PipelineHaltedException.
2. NovelPipelineTask: Thread-safe locking (RLock), concurrent logging, polling, finish, fail, get_logs.
3. post_processor.py: Markdown code-block prose precedence, text patch emission without code keys.
4. validator.py: _infer_chapter_index boundary handling (returns None when all written, correct index when unwritten).
5. refusal_filter.py: Meta-narrative detection for '作者在此' and '向讀者說明'.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from backend import persistence as db
from backend.common.refusal_filter import find_meta_narrative_leaks
from backend.generation.orchestration.post_processor import (
    _derive_patches,
    _normalize_result_text,
    _normalize_text_by_stage,
    build_post_process_result,
)
from backend.generation.routing.schema import GenerationTaskRequest, GenerationTaskTarget
from backend.generation.routing.validator import _find_first_missing, _infer_chapter_index, resolve_generation_task_target
from backend.services.autonomous_pipeline import (
    AutonomousPipelineManager,
    NovelPipelineTask,
    PipelineHaltedException,
)
from backend.services.narrative.narrative_auditor import NarrativeAuditor


# =============================================================================
# 1. Pipeline Halting on Director WAIT_USER / FINISH
# =============================================================================

def test_pipeline_halted_exception_raised_on_wait_user(novel_factory):
    novel_id = novel_factory(title="中斷測試小說", genre="奇幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)

    mock_decision = {
        "action": "WAIT_USER",
        "reason": "修仙門派勢力邊界衝突未定義，需要作者釐清",
        "hint": "請先設定宗門勢力範圍",
    }

    with patch.object(manager, "execute_generation_task", return_value=MagicMock(ok=True)), \
         patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision):
        with pytest.raises(PipelineHaltedException) as exc_info:
            manager._execute_stage_with_retry(
                task=task,
                stage="worldview",
                task_type="generate",
                instruction="設計世界觀",
                user_prompt="核心設定",
                verify_fn=lambda: False,
                max_retries=2,
            )
        assert exc_info.value.action == "WAIT_USER"
        assert "修仙門派勢力邊界" in exc_info.value.reason


def test_pipeline_halted_exception_raised_on_finish(novel_factory):
    novel_id = novel_factory(title="完結測試小說", genre="都市")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)

    mock_decision = {
        "action": "FINISH",
        "reason": "小說所有支線已完全收束，無需額外生成",
    }

    with patch.object(manager, "execute_generation_task", return_value=MagicMock(ok=True)), \
         patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision):
        with pytest.raises(PipelineHaltedException) as exc_info:
            manager._execute_stage_with_retry(
                task=task,
                stage="worldview",
                task_type="generate",
                instruction="設計世界觀",
                user_prompt="核心設定",
                verify_fn=lambda: False,
                max_retries=2,
            )
        assert exc_info.value.action == "FINISH"


def test_run_autonomous_flow_cleanly_halts_on_wait_user(novel_factory):
    novel_id = novel_factory(title="流程暫停測試", genre="玄幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    mock_decision = {
        "action": "WAIT_USER",
        "reason": "世界觀存在嚴重邏輯矛盾，需人工修正",
    }

    characters_called = []
    def fake_are_characters_ready(*args, **kwargs):
        characters_called.append(True)
        return False

    with patch.object(manager, "execute_generation_task", return_value=MagicMock(ok=True)), \
         patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False), \
         patch("backend.services.autonomous_pipeline._are_characters_ready", side_effect=fake_are_characters_ready):

        manager._run_autonomous_flow(task, initial_prompt="請創作宏大玄幻小說", max_chapters=3)

    assert task.is_running is False
    assert task.current_stage == "worldview_wait_user"
    assert "⏸️ 等待使用者介入: 世界觀存在嚴重邏輯矛盾" in task.status_message
    assert len(characters_called) == 0, "Downstream stage 'characters' must not be executed after WAIT_USER!"
    assert db.get_pipeline_lock_status(novel_id) is None, "Pipeline lock must be released on halt!"


def test_run_autonomous_flow_cleanly_completes_on_finish(novel_factory):
    novel_id = novel_factory(title="流程結束測試", genre="科幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    mock_decision = {
        "action": "FINISH",
        "reason": "故事主線已圓滿抵達終局",
    }

    with patch.object(manager, "execute_generation_task", return_value=MagicMock(ok=True)), \
         patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="創作科幻短篇", max_chapters=1)

    assert task.is_running is False
    assert task.current_stage == "completed"
    assert task.progress_percent == 100
    assert "🎉 創作已由 Director 判定圓滿完成！" in task.status_message
    assert db.get_pipeline_lock_status(novel_id) is None


# =============================================================================
# 2. NovelPipelineTask Thread Safety & Synchronization
# =============================================================================

def test_novel_pipeline_task_concurrent_logging_and_polling():
    task = NovelPipelineTask(novel_id="test_concurrent_task", novel_title="並發測試")
    task.is_running = True

    errors = []
    stop_event = threading.Event()

    def worker_logger(worker_id: int):
        try:
            for i in range(150):
                task.log(f"Worker-{worker_id} message #{i}", level="info")
                time.sleep(0.0005)
        except Exception as e:
            errors.append(f"Logger error: {e}")

    def poller_reader(poller_id: int):
        try:
            while not stop_event.is_set():
                state = task.to_dict()
                assert isinstance(state["logs"], list)
                assert state["log_seq"] >= 0
                assert len(state["logs"]) <= 100
                logs = task.get_logs(since_seq=max(0, state["log_seq"] - 10))
                assert isinstance(logs, list)
                time.sleep(0.001)
        except Exception as e:
            errors.append(f"Reader error: {e}")

    log_threads = [threading.Thread(target=worker_logger, args=(i,)) for i in range(4)]
    poll_threads = [threading.Thread(target=poller_reader, args=(i,)) for i in range(3)]

    for t in poll_threads:
        t.start()
    for t in log_threads:
        t.start()

    for t in log_threads:
        t.join()

    stop_event.set()
    for t in poll_threads:
        t.join()

    assert not errors, f"Race condition errors encountered during concurrent execution: {errors}"
    assert task.log_seq == 4 * 150
    final_dict = task.to_dict()
    assert len(final_dict["logs"]) == 100
    # Confirm sequence monotonicity
    seqs = [e["seq"] for e in final_dict["logs"]]
    assert seqs == sorted(seqs)


def test_novel_pipeline_task_finish_and_fail_state():
    task = NovelPipelineTask(novel_id="task_finish_fail")
    task.is_running = True

    task.finish(status_message="大結局撰寫完成")
    assert task.is_running is False
    assert task.current_stage == "completed"
    assert task.progress_percent == 100
    assert task.status_message == "大結局撰寫完成"

    task.is_running = True
    task.fail(error_message="伺服器記憶體超限")
    assert task.is_running is False
    assert task.current_stage == "error"
    assert task.error == "伺服器記憶體超限"
    assert "執行中斷" in task.status_message or "伺服器記憶體超限" in task.status_message


def test_novel_pipeline_task_get_logs_filtering():
    task = NovelPipelineTask(novel_id="task_logs")
    for i in range(10):
        task.log(f"msg {i+1}")

    all_logs = task.get_logs(0)
    assert len(all_logs) == 10
    assert all_logs[0]["seq"] == 1
    assert all_logs[-1]["seq"] == 10

    filtered = task.get_logs(since_seq=7)
    assert len(filtered) == 3
    assert [e["seq"] for e in filtered] == [8, 9, 10]


# =============================================================================
# 3. Post-Processor Markdown JSON Precedence & Patch Emission
# =============================================================================

def test_normalize_result_text_preserves_writer_prose_with_code_blocks():
    req = GenerationTaskRequest(
        novel_id="test_prose",
        stage="writer",
        target=GenerationTaskTarget(chapter_index=3),
    )
    raw_prose = (
        "林默推開廢棄控制室的大門，眼前的古老主機突然閃爍起幽藍色的代碼光芒：\n\n"
        "```json\n"
        "{\n"
        '  "system_id": "OMEGA-09",\n'
        '  "security_level": 5,\n'
        '  "alert": "INTRUDER_DETECTED"\n'
        "}\n"
        "```\n\n"
        "他深吸了一口氣，伸手握住了腰間的短刃，警惕地掃視著四周。"
    )

    norm = _normalize_result_text(req, raw_prose)
    assert isinstance(norm, dict)
    assert "text" in norm
    assert norm["text"] == raw_prose

    patches = _derive_patches(req, norm)
    assert len(patches) == 1
    assert patches[0]["op"] == "replace"
    assert patches[0]["path"] == "/chapters/3/content"
    assert patches[0]["value"] == raw_prose
    assert not any(p["path"] in ("/system_id", "/security_level", "/alert", "/text") for p in patches)


def test_normalize_result_text_unwraps_explicit_content_wrapper():
    req = GenerationTaskRequest(
        novel_id="test_wrapper",
        stage="editor",
        target=GenerationTaskTarget(chapter_index=1),
    )
    wrapped = json.dumps({"content": "這是一段經過微調潤飾的故事正文。"}, ensure_ascii=False)
    norm = _normalize_result_text(req, wrapped)
    assert norm == {"text": "這是一段經過微調潤飾的故事正文。"}

    patches = _derive_patches(req, norm)
    assert len(patches) == 1
    assert patches[0]["path"] == "/chapters/1/content"
    assert patches[0]["value"] == "這是一段經過微調潤飾的故事正文。"


def test_normalize_result_text_flexible_arguments_support():
    prose = "清風吹拂著山崗，明月照耀著大江。"
    # Pure text+stage helper (no task wrapper needed)
    res1 = _normalize_text_by_stage(prose, "writer")
    assert res1 == {"text": prose}

    res2 = _normalize_text_by_stage(prose, "editor")
    assert res2 == {"text": prose}


def test_normalize_result_text_non_writer_stages_retain_json_parsing():
    req = GenerationTaskRequest(novel_id="test_wv", stage="worldview")
    raw_json = json.dumps({"theme": "賽博修仙", "power_ranks": ["練氣", "築基", "金丹"]}, ensure_ascii=False)
    norm = _normalize_result_text(req, raw_json)
    assert isinstance(norm, dict)
    assert norm.get("theme") == "賽博修仙"
    assert "power_ranks" in norm

    patches = _derive_patches(req, norm)
    paths = {p["path"] for p in patches}
    assert "/theme" in paths
    assert "/power_ranks" in paths


# =============================================================================
# 4. Validator _infer_chapter_index Boundary Handling
# =============================================================================

def test_infer_chapter_index_returns_none_when_all_written():
    # 5 chapters planned, all 5 chapters written
    written_chapters = [{"chapter_index": i} for i in range(1, 6)]
    assert _find_first_missing(written_chapters, 5) is None

    # Using integer list
    assert _find_first_missing([1, 2, 3], 3) is None


def test_infer_chapter_index_finds_first_missing_chapter():
    # Chapter 2 is missing
    written_chapters = [
        {"chapter_index": 1},
        {"chapter_index": 3},
        {"chapter_index": 4},
    ]
    assert _find_first_missing(written_chapters, 4) == 2


def test_infer_chapter_index_returns_next_sequential_chapter():
    written = [1, 2]
    assert _find_first_missing(written, 5) == 3


def test_infer_chapter_index_zero_planned_chapters():
    assert _find_first_missing([], 0) == 1


def test_resolve_generation_task_target_sets_none_when_fully_written(novel_factory):
    novel_id = novel_factory(title="全書完結測試", genre="修真")
    vols = [
        {
            "volume_index": 1,
            "title": "第一卷",
            "chapter_count": 2,
            "chapters_outline": json.dumps([{"chapter_index": 1}, {"chapter_index": 2}]),
        }
    ]
    db.save_volumes(novel_id, vols)
    db.save_chapter(novel_id, 1, "第 1 章正文內容...")
    db.save_chapter(novel_id, 2, "第 2 章大結局正文內容...")

    req = GenerationTaskRequest(novel_id=novel_id, stage="writer")
    resolved = resolve_generation_task_target(req)
    assert resolved.target.chapter_index is None, "When all chapters are written, chapter_index must be None to prevent overwrite!"


# =============================================================================
# 5. Refusal Filter Meta-Narrative Detection
# =============================================================================

def test_refusal_filter_detects_subtle_fourth_wall_expressions():
    prose = "作者在此需要向讀者說明，林默此時的修為境界早已超越同輩。"
    leaks = find_meta_narrative_leaks(prose)
    assert len(leaks) >= 1

    finding = NarrativeAuditor._check_meta_narrative_leak(prose)
    assert finding is not None
    assert finding.get("severity") == "critical"
    assert finding.get("action_required") is True


def test_refusal_filter_does_not_false_positive_on_in_world_book_references():
    prose = "「這卷古籍的上一章節記載了封印符陣的破解之法，」長老指著殘破的羊皮古冊說道。"
    finding = NarrativeAuditor._check_meta_narrative_leak(prose)
    assert finding is None or finding.get("action_required") is False
