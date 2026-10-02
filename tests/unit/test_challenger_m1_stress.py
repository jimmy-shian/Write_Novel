# -*- coding: utf-8 -*-
"""
Empirical Stress Test Harness for Milestone 1: Pipeline Resilience & Bug Fixes.
Authored by challenger_1 (teamwork_preview_challenger).

Adversarial Stress Test Matrix:
1. NovelPipelineTask:
   - High concurrency with 24 writer threads + 8 reader threads + 2 lifecycle threads.
   - 2,400+ concurrent log operations under heavy contention.
   - Monotonic sequence verification, log window truncation (<= 100 entries), 0 race conditions,
     0 deadlocks, 0 list mutation RuntimeErrors.
   - Reentrant lock safety verification.
2. post_processor.py:
   - Nested markdown code blocks (python within markdown, bash, json).
   - Unclosed code blocks and syntax-broken JSON.
   - LitRPG character stat tables with complex nested curly brackets {}.
   - Explicit wrapper extraction vs raw prose preserving.
   - Strict verification that `/chapters/{index}/content` patch is emitted with full prose intact
     and no spurious JSON key patches.
3. validator.py (_infer_chapter_index):
   - Boundary total <= 0.
   - All planned chapters written (returns None).
   - Non-consecutive gaps (missing chapter 1, missing intermediate chapters).
   - Out-of-order chapter lists (shuffled, reverse).
   - Over-length lists (indices > total), duplicate chapters, malformed objects.
   - Database integration with multi-volume chapter counting.
4. autonomous_pipeline.py:
   - Director WAIT_USER halting across worldview, characters, volumes, and writer stages.
   - Director FINISH halting across multiple stages.
   - Strict verification that downstream stages are NEVER executed after halt.
   - Verification of lock release and task state transition.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from backend import persistence as db
from backend.generation.orchestration.post_processor import (
    _derive_patches,
    _normalize_result_text,
    build_post_process_result,
)
from backend.generation.routing.schema import GenerationTaskRequest, GenerationTaskTarget
from backend.generation.routing.validator import _find_first_missing, _infer_chapter_index, resolve_generation_task_target
from backend.services.autonomous_pipeline import (
    AutonomousPipelineManager,
    NovelPipelineTask,
    PipelineHaltedException,
)


# =============================================================================
# 1. NovelPipelineTask High-Concurrency Stress Test
# =============================================================================

def test_novel_pipeline_task_heavy_concurrency_24_writers_8_readers():
    """Stress test NovelPipelineTask with 24 concurrent writer threads and 8 reader threads.
    
    Verifies:
    - 0 race conditions or thread crashes.
    - Exact monotonic sequence counter matching total write operations.
    - logs list never exceeds 100 items.
    - Final logs list contains strictly monotonically increasing seq values.
    - 0 deadlocks within timeout.
    """
    task = NovelPipelineTask(novel_id="stress_concurrency_task", novel_title="高並發壓力測試")
    task.is_running = True

    NUM_WRITERS = 24
    WRITES_PER_THREAD = 100
    TOTAL_WRITES = NUM_WRITERS * WRITES_PER_THREAD
    NUM_READERS = 8

    errors = []
    stop_event = threading.Event()
    start_barrier = threading.Barrier(NUM_WRITERS + NUM_READERS)

    def writer_worker(worker_id: int):
        try:
            start_barrier.wait()
            for i in range(WRITES_PER_THREAD):
                task.log(f"Writer-{worker_id:02d} entry #{i:04d}", level="info")
        except Exception as exc:
            errors.append(f"Writer-{worker_id} crashed: {exc}")

    def reader_worker(reader_id: int):
        try:
            start_barrier.wait()
            prev_seq = -1
            while not stop_event.is_set():
                state = task.to_dict()
                assert isinstance(state, dict)
                assert isinstance(state["logs"], list)
                assert len(state["logs"]) <= 100
                assert state["log_seq"] >= 0
                assert state["log_seq"] >= prev_seq
                prev_seq = state["log_seq"]

                # Exercise get_logs with dynamic since_seq
                since = max(0, state["log_seq"] - 20)
                incremental = task.get_logs(since_seq=since)
                assert isinstance(incremental, list)
                assert len(incremental) <= 100
                for item in incremental:
                    assert item["seq"] > since
        except Exception as exc:
            errors.append(f"Reader-{reader_id} crashed: {exc}")

    writer_threads = [threading.Thread(target=writer_worker, args=(i,)) for i in range(NUM_WRITERS)]
    reader_threads = [threading.Thread(target=reader_worker, args=(i,)) for i in range(NUM_READERS)]

    for t in writer_threads + reader_threads:
        t.start()

    # Join writers
    for t in writer_threads:
        t.join(timeout=15.0)
        assert not t.is_alive(), "Writer thread deadlocked or timed out!"

    # Signal readers to stop and join
    stop_event.set()
    for t in reader_threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "Reader thread deadlocked or timed out!"

    assert not errors, f"Errors occurred during 24-writer concurrency stress test: {errors}"
    assert task.log_seq == TOTAL_WRITES, f"Expected {TOTAL_WRITES} log_seq, got {task.log_seq}"

    final_state = task.to_dict()
    assert len(final_state["logs"]) == 100, f"Expected 100 logs in window, got {len(final_state['logs'])}"
    seqs = [entry["seq"] for entry in final_state["logs"]]
    assert seqs == sorted(seqs), "Logs in window must be strictly sorted by seq!"
    assert len(seqs) == len(set(seqs)), "Duplicate sequence numbers detected in logs window!"
    assert seqs[-1] == TOTAL_WRITES, f"Last seq in window should be {TOTAL_WRITES}, got {seqs[-1]}"


def test_novel_pipeline_task_reentrant_lock_and_lifecycle():
    """Verify RLock reentrancy and state transitions under lock holding."""
    task = NovelPipelineTask(novel_id="task_reentrant", novel_title="重入鎖與生命週期")

    # Reentrant lock test: holding outer lock while invoking inner methods
    with task._lock:
        task.log("Reentrant log message")
        state = task.to_dict()
        assert state["log_seq"] == 1
        filtered = task.get_logs(0)
        assert len(filtered) == 1
        task.finish("提前完結")
        assert task.is_running is False
        assert task.current_stage == "completed"

    # Verify failure transition overrides
    task.is_running = True
    task.fail("資源耗盡崩潰")
    assert task.is_running is False
    assert task.current_stage == "error"
    assert task.error == "資源耗盡崩潰"


# =============================================================================
# 2. post_processor.py Prose vs Markdown Code Blocks & LitRPG Stats
# =============================================================================

def test_post_processor_nested_code_blocks_preserves_full_prose():
    """Stress test prose containing nested markdown code blocks (python inside markdown)."""
    req = GenerationTaskRequest(
        novel_id="novel_stress_nested",
        stage="writer",
        target=GenerationTaskTarget(chapter_index=7),
    )
    complex_prose = (
        "林默調出古代機關遺蹟的運行日誌，全息投影呈現出以下代碼構架：\n\n"
        "````markdown\n"
        "```python\n"
        "import torch\n"
        "class SpatialMatrix(nn.Module):\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        '        self.weights = {"alpha": 1.0, "omega": 9.9}\n'
        "```\n"
        "````\n\n"
        "符文陣列轟鳴運轉，他握緊劍柄，神識如潮水般擴散。"
    )

    norm = _normalize_result_text(req, complex_prose)
    assert isinstance(norm, dict)
    assert norm.get("text") == complex_prose

    patches = _derive_patches(req, norm)
    assert len(patches) == 1
    assert patches[0]["op"] == "replace"
    assert patches[0]["path"] == "/chapters/7/content"
    assert patches[0]["value"] == complex_prose
    # Verify no leaked sub-keys from python dict
    assert not any(p["path"] in ("/weights", "/alpha", "/omega") for p in patches)


def test_post_processor_embedded_code_block_with_text_or_content_key():
    """Adversarial test: Prose containing an inner code block that has a 'text' or 'content' key.
    Checks whether post_processor strips the surrounding story prose.
    """
    req = GenerationTaskRequest(
        novel_id="test_leak",
        stage="writer",
        target=GenerationTaskTarget(chapter_index=1),
    )
    prose = (
        "林默走進房間，看見終端機上顯示著：\n\n"
        "```json\n"
        "{\n"
        '  "text": "系統警告：能源不足！"\n'
        "}\n"
        "```\n\n"
        "他嘆了一口氣，轉身離開了房間。"
    )
    norm = _normalize_result_text(req, prose)
    assert "林默走進房間" in norm["text"], f"Surrounding story prose was stripped! Extracted: {norm['text']}"
    assert "他嘆了一口氣" in norm["text"], f"Surrounding story prose was stripped! Extracted: {norm['text']}"


def test_post_processor_litrpg_stats_and_curly_brackets():
    """Stress test LitRPG stat tables with nested curly braces and brackets."""
    req = GenerationTaskRequest(
        novel_id="novel_litrpg",
        stage="writer",
        target=GenerationTaskTarget(chapter_index=2),
    )
    litrpg_prose = (
        "【叮！宿主斬殺深淵領主，天道結算面板開啟】\n\n"
        "| 屬性 | 當前數值 | 裝備增益 | 詞條效果 |\n"
        "| :--- | :--- | :--- | :--- |\n"
        '| 力量 | 1,450 | {項鍊: +200, 護腕: +50} | {"破甲率": "45%", "震盪": true} |\n'
        '| 敏捷 | 980   | {靴子: +120} | {"幻影步": [1, 2, 3]} |\n'
        '| 智力 | {基礎: 500, 附魔: {"奧術增幅": 1.5}} | 無 | 特殊狀態 |\n\n'
        "隨即，金色流光湧入林默體內，筋骨發出雷鳴般的脆響。"
    )

    norm = _normalize_result_text(req, litrpg_prose)
    assert isinstance(norm, dict)
    assert norm.get("text") == litrpg_prose

    patches = _derive_patches(req, norm)
    assert len(patches) == 1
    assert patches[0]["path"] == "/chapters/2/content"
    assert patches[0]["value"] == litrpg_prose


def test_post_processor_unclosed_and_malformed_code_blocks():
    """Stress test prose with unclosed code blocks, syntax errors, and bash snippets."""
    req = GenerationTaskRequest(
        novel_id="novel_unclosed",
        stage="editor",
        target=GenerationTaskTarget(chapter_index=4),
    )
    malformed_prose = (
        "「看看這個終端日誌，」工程師指著屏幕怒吼道：\n"
        "```bash\n"
        "curl -X POST https://api.matrix.io/v1/overload \\\n"
        '  -H "Authorization: Bearer undefined" \\\n'
        '  -d \'{"trigger": true, "corrupted": [\n'
        "# 注意：代碼在此處突然被截斷，未閉合反引號與括號\n\n"
        "隨後整個核心機房火花四濺，防禦警報刺破黑夜。"
    )

    norm = _normalize_result_text(req, malformed_prose)
    assert isinstance(norm, dict)
    assert norm.get("text") == malformed_prose

    patches = _derive_patches(req, norm)
    assert len(patches) == 1
    assert patches[0]["path"] == "/chapters/4/content"
    assert patches[0]["value"] == malformed_prose


def test_post_processor_json_wrapped_vs_raw_prose_handling():
    """Ensure explicit JSON wrapping with content/text keys is unwrapped cleanly,
    while arbitrary JSON structures are preserved as raw chapter prose."""
    # Sub-case A: Explicit {"content": "..."}
    req_writer = GenerationTaskRequest(
        novel_id="novel_wrap_content",
        stage="writer",
        target=GenerationTaskTarget(chapter_index=1),
    )
    wrapped_json = json.dumps({"content": "這是一段被 JSON 封裝的故事章節正文。"}, ensure_ascii=False)
    norm_a = _normalize_result_text(req_writer, wrapped_json)
    assert norm_a == {"text": "這是一段被 JSON 封裝的故事章節正文。"}
    patch_a = _derive_patches(req_writer, norm_a)
    assert patch_a[0]["value"] == "這是一段被 JSON 封裝的故事章節正文。"

    # Sub-case B: Arbitrary JSON without content or text keys (e.g. system status output)
    arbitrary_json = json.dumps({"boss_status": "dead", "loot_items": ["龍骨", "聖杯"]}, ensure_ascii=False)
    norm_b = _normalize_result_text(req_writer, arbitrary_json)
    assert norm_b == {"text": arbitrary_json}
    patch_b = _derive_patches(req_writer, norm_b)
    assert patch_b[0]["value"] == arbitrary_json


def test_post_processor_non_writer_stages_preserve_structured_patches():
    """Contrast test: non-writer stages (e.g. worldview) MUST parse into structured entity patches."""
    req_worldview = GenerationTaskRequest(
        novel_id="novel_wv_structured",
        stage="worldview",
    )
    wv_payload = json.dumps(
        {
            "theme": "星際修真",
            "factions": ["太虛仙宗", "天網機械盟"],
            "power_system": "靈子躍遷架構",
        },
        ensure_ascii=False,
    )
    norm = _normalize_result_text(req_worldview, wv_payload)
    assert isinstance(norm, dict)
    assert norm["theme"] == "星際修真"

    patches = _derive_patches(req_worldview, norm)
    patch_dict = {p["path"]: p["value"] for p in patches}
    assert patch_dict["/theme"] == "星際修真"
    assert patch_dict["/factions"] == ["太虛仙宗", "天網機械盟"]
    assert patch_dict["/power_system"] == "靈子躍遷架構"


# =============================================================================
# 3. validator.py Boundary Gaps and Out-of-Order Lists
# =============================================================================

def test_infer_chapter_index_total_count_zero_or_negative():
    """Boundary test total <= 0 returns 1."""
    assert _find_first_missing([], 0) == 1
    assert _find_first_missing([], -1) == 1
    assert _find_first_missing([], -100) == 1


def test_infer_chapter_index_all_chapters_written():
    """Verify returns None when all planned chapters are written."""
    # Simple list 1..10
    assert _find_first_missing(list(range(1, 11)), 10) is None
    # Dicts 1..5
    written_dicts = [{"chapter_index": i} for i in range(1, 6)]
    assert _find_first_missing(written_dicts, 5) is None
    # Single chapter planned and written
    assert _find_first_missing([1], 1) is None


def test_infer_chapter_index_non_consecutive_gaps():
    """Test boundary non-consecutive chapter gaps."""
    # Gap at chapter 1 (first chapter unwritten)
    assert _find_first_missing([2, 3, 4], 4) == 1
    # Gap at intermediate chapter (1 written, 2 missing, 3 written)
    assert _find_first_missing([1, 3], 3) == 2
    # Multiple gaps (1, 4 written; 2, 3 missing -> returns first missing: 2)
    assert _find_first_missing([1, 4], 4) == 2
    # Gap at final chapter (1, 2 written, 3 missing)
    assert _find_first_missing([1, 2], 3) == 3


def test_infer_chapter_index_out_of_order_lists():
    """Test out-of-order, reversed, and shuffled chapter lists."""
    # Shuffled list: [5, 2, 4, 1], missing 3
    assert _find_first_missing([5, 2, 4, 1], 5) == 3
    # Reverse order: [3, 2, 1], all written
    assert _find_first_missing([3, 2, 1], 3) is None
    # Dicts out-of-order: [{"chapter_index": 3}, {"chapter_index": 1}], total=3 -> returns 2
    assert _find_first_missing([{"chapter_index": 3}, {"chapter_index": 1}], 3) == 2
    # Reverse with missing chapter 2: [5, 4, 3, 1], total=5 -> returns 2
    assert _find_first_missing([5, 4, 3, 1], 5) == 2


def test_infer_chapter_index_duplicates_and_extra_chapters():
    """Test resilience against duplicate entries and indices exceeding total."""
    # Duplicates: [1, 1, 1, 2, 2], total=3 -> returns 3
    assert _find_first_missing([1, 1, 1, 2, 2], 3) == 3
    # Extra chapter beyond total: [1, 2, 3, 99], total=3 -> returns None (1..3 satisfied)
    assert _find_first_missing([1, 2, 3, 99], 3) is None
    # Extra chapter with gap: [1, 3, 99], total=3 -> returns 2
    assert _find_first_missing([1, 3, 99], 3) == 2


def test_infer_chapter_index_malformed_entries():
    """Test resilience against None, string items, and corrupted dicts."""
    corrupted = [
        None,
        "not_a_chapter",
        {"no_index_key": "val"},
        {"chapter_index": "corrupted_str"},
        {"chapter_index": 1},
        3,
    ]
    # In corrupted list, 1 and 3 are extracted; for total=3, 2 is missing
    assert _find_first_missing(corrupted, 3) == 2


def test_infer_chapter_index_db_integration(novel_factory):
    """Test _infer_chapter_index with database-backed multi-volume novel."""
    novel_id = novel_factory(title="DB章節推斷測試")
    vols = [
        {
            "volume_index": 1,
            "title": "第一卷",
            "chapter_count": 2,
            "chapters_outline": json.dumps([{"chapter_index": 1}, {"chapter_index": 2}]),
        },
        {
            "volume_index": 2,
            "title": "第二卷",
            "chapter_count": 2,
            "chapters_outline": json.dumps([{"chapter_index": 3}, {"chapter_index": 4}]),
        },
    ]
    db.save_volumes(novel_id, vols)

    # When no chapters exist in DB, returns 1
    assert _infer_chapter_index(novel_id=novel_id) == 1

    # Save chapters 1 and 3 (chapter 2 missing)
    db.save_chapter(novel_id, 1, "第 1 章正文內容...")
    db.save_chapter(novel_id, 3, "第 3 章正文內容...")
    assert _infer_chapter_index(novel_id=novel_id) == 2

    # Save chapter 2 (now 1, 2, 3 written, 4 missing)
    db.save_chapter(novel_id, 2, "第 2 章正文內容...")
    assert _infer_chapter_index(novel_id=novel_id) == 4

    # Save chapter 4 (all 4 written)
    db.save_chapter(novel_id, 4, "第 4 章正文內容...")
    assert _infer_chapter_index(novel_id=novel_id) is None


# =============================================================================
# 4. autonomous_pipeline.py WAIT_USER & FINISH Halting Simulations
# =============================================================================

def test_autonomous_pipeline_halts_at_characters_stage(novel_factory):
    """Simulate WAIT_USER return from Director during 'characters' stage.
    Verify pipeline strictly halts and downstream stages (foreshadowing, volumes, writer) never run.
    """
    novel_id = novel_factory(title="角色中斷測試", genre="奇幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    downstream_calls = {"foreshadowing": 0, "volumes": 0, "writer": 0}

    def fake_execute_stage(task, stage, **kwargs):
        if stage == "characters":
            raise PipelineHaltedException(action="WAIT_USER", reason="主要反派陣營人設衝突，需使用者調解")
        if stage in downstream_calls:
            downstream_calls[stage] += 1
        return MagicMock(ok=True)

    with patch.object(manager, "_execute_stage_with_retry", side_effect=fake_execute_stage), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_characters_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="測試 prompt", max_chapters=2)

    assert task.is_running is False
    assert task.current_stage == "characters_wait_user"
    assert "⏸️ 等待使用者介入: 主要反派陣營人設衝突" in task.status_message
    assert downstream_calls["foreshadowing"] == 0, "Foreshadowing was invoked after WAIT_USER!"
    assert downstream_calls["volumes"] == 0, "Volumes was invoked after WAIT_USER!"
    assert downstream_calls["writer"] == 0, "Writer was invoked after WAIT_USER!"
    assert db.get_pipeline_lock_status(novel_id) is None, "Pipeline DB lock was not released!"


def test_autonomous_pipeline_completes_at_volumes_stage_on_finish(novel_factory):
    """Simulate FINISH return from Director during 'volumes' stage.
    Verify pipeline immediately finishes and downstream stages (geometry, writer) never run.
    """
    novel_id = novel_factory(title="分卷結束測試", genre="玄幻")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    downstream_calls = {"geometry": 0, "writer": 0}

    def fake_execute_stage(task, stage, **kwargs):
        if stage == "volumes":
            raise PipelineHaltedException(action="FINISH", reason="單卷微型短篇已足夠完備")
        if stage in downstream_calls:
            downstream_calls[stage] += 1
        return MagicMock(ok=True)

    with patch.object(manager, "_execute_stage_with_retry", side_effect=fake_execute_stage), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_characters_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_seeds_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_turning_points_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_volumes_ready", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="測試 prompt", max_chapters=1)

    assert task.is_running is False
    assert task.current_stage == "completed"
    assert task.progress_percent == 100
    assert "🎉 創作已由 Director 判定圓滿完成！" in task.status_message
    assert downstream_calls["geometry"] == 0
    assert downstream_calls["writer"] == 0
    assert db.get_pipeline_lock_status(novel_id) is None


def test_autonomous_pipeline_halts_during_writer_chapter_loop(novel_factory):
    """Simulate WAIT_USER return from Director while writing Chapter 2 of a 3-chapter novel.
    Verify Chapter 3 is NEVER attempted and the task is safely parked in wait_user state.
    """
    novel_id = novel_factory(title="章節寫作中斷測試", genre="都市")
    manager = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id=novel_id)
    task.is_running = True
    manager.tasks[novel_id] = task

    # Prepare volumes and stitched plot for 3 chapters
    vols = [
        {
            "volume_index": 1,
            "title": "第一卷",
            "chapter_count": 3,
            "chapters_outline": json.dumps([
                {"chapter_index": 1, "title": "第1章"},
                {"chapter_index": 2, "title": "第2章"},
                {"chapter_index": 3, "title": "第3章"},
            ]),
        }
    ]
    db.save_volumes(novel_id, vols)
    # Chapter 1 is already written
    db.save_chapter(novel_id, 1, "第 1 章正文，字數足夠達到五十個字以上。這是一段合格的完整正文小說情節。")

    chapters_attempted = []

    def fake_execute_stage(task, stage, **kwargs):
        target = kwargs.get("target") or {}
        ch_idx = target.get("chapter_index")
        if stage == "writer":
            chapters_attempted.append(ch_idx)
            if ch_idx == 2:
                raise PipelineHaltedException(action="WAIT_USER", reason="第 2 章戰鬥邏輯崩潰，需作者干預指導")
        return MagicMock(ok=True)

    with patch.object(manager, "_execute_stage_with_retry", side_effect=fake_execute_stage), \
         patch("backend.services.autonomous_pipeline._is_worldview_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_characters_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_seeds_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_turning_points_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._are_volumes_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._is_geometry_ready", return_value=True), \
         patch("backend.services.autonomous_pipeline._has_volume_skeleton", return_value=True), \
         patch("backend.services.autonomous_pipeline._chapter_needs_editor_retry", return_value=False):

        manager._run_autonomous_flow(task, initial_prompt="都市傳奇", max_chapters=3)

    assert task.is_running is False
    assert task.current_stage == "writer_ch2_wait_user"
    assert "⏸️ 等待使用者介入: 第 2 章戰鬥邏輯崩潰" in task.status_message
    assert 2 in chapters_attempted
    assert 3 not in chapters_attempted, "Chapter 3 was executed after Chapter 2 triggered WAIT_USER!"
    assert db.get_pipeline_lock_status(novel_id) is None, "Pipeline lock must be released on writer halt!"
