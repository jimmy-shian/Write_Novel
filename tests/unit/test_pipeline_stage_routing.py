# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch
import pytest

from backend.services.autonomous_pipeline import (
    AutonomousPipelineManager,
    NovelPipelineTask,
    StageRedirectException,
    ChapterHaltedException,
    RETRY_POLICY,
    classify_pipeline_error,
)


def test_classify_pipeline_error_categories():
    assert classify_pipeline_error("EDITOR_MISSING_INPUT: Chapter 1 prose not found") == "EDITOR_MISSING_INPUT"
    assert classify_pipeline_error("Connection refused by proxy") == "INFRA_ERROR"
    assert classify_pipeline_error("content 不可為空") == "EMPTY_OUTPUT"
    assert classify_pipeline_error("content 長度不足：至少 1200 字") == "SHORT_OUTPUT"
    assert classify_pipeline_error("時序世界線穿幫：已於第 5 章死亡") == "TEMPORAL_ERROR"
    assert classify_pipeline_error("【場景地點漂移】大綱指定房號為 101") == "SCENE_DRIFT"


def test_editor_missing_prose_does_not_retry_stage_limit():
    """Editor 找不到正文時，應直接觸發 StageRedirectException 導向 writer"""
    svc = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id="test_novel")

    # 模擬 database 返回空正文
    with patch("backend.persistence.get_latest_chapter", return_value={"content": ""}):
        with patch("backend.persistence.get_chapter", return_value={"content": ""}):
            # 在 _run_editor_for_chapter 中前置檢查就會直接返回 REDIRECT_TO_WRITER
            res = svc._run_editor_for_chapter(
                task=task,
                novel_id="test_novel",
                ch_idx=1,
                total_target=10,
                curr_vol_idx=1,
                director_eval={},
            )
            assert res == "REDIRECT_TO_WRITER"
            # 前置輸入缺失不屬於可透過重送解決的端點錯誤，因此不重試
            assert task.stage_retry_counts.get("editor", 0) == 0


def test_director_redirect_writer_actually_redirects():
    """Director 回傳 target_stage=writer 時，實際拋出 StageRedirectException 重定向"""
    svc = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id="test_novel")

    mock_decision = {
        "action": "REDIRECT",
        "target_stage": "writer",
        "reason": "情節因果需要重構",
        "agent_prompt": "請重新撰寫本章因果",
    }

    # 模擬執行生成拋出品質異常，Director 給出 REDIRECT 到 writer 的決策
    with patch.object(svc, "execute_generation_task", side_effect=RuntimeError("文風偏離")):
        with patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision):
            with patch("backend.persistence.get_chapter", return_value={"content": "原有初稿"}):
                with patch("time.sleep", return_value=None):
                    with pytest.raises(StageRedirectException) as exc_info:
                        svc._execute_stage_with_retry(
                            task=task,
                            stage="editor",
                            target={"chapter_index": 1},
                        )

                    assert exc_info.value.target_stage == "writer"
                    assert task.stage_redirect_count >= 1


def test_writer_gate_failure_blocks_editor():
    """Writer 二次修正失敗時，不得進入 Editor"""
    svc = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id="test_novel")

    # 模擬正文包含拒答標記，重新驗收依然包含拒答標記
    mock_bad_chapter = {"content": "我身為 AI 助手，無法生成相關內容..."}
    with patch("backend.persistence.get_chapter", return_value=mock_bad_chapter):
        with patch.object(svc, "_execute_stage_with_retry", return_value=None):
            eval_res = svc._run_director_chapter_gate(
                task=task,
                novel_id="test_novel",
                ch_idx=1,
                curr_vol_idx=1,
            )
            # 必須判定為失敗且 writer_failed
            assert eval_res.get("passed") is False
            assert eval_res.get("writer_failed") is True


def test_halt_chapter_halts_single_chapter_gracefully():
    """HALT_CHAPTER 會停止本章但不崩潰拋錯"""
    svc = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id="test_novel")

    mock_decision = {
        "action": "HALT_CHAPTER",
        "reason": "大綱衝突需要等待主線調整",
    }

    with patch.object(svc, "execute_generation_task", side_effect=RuntimeError("品質不符")):
        with patch("backend.services.autonomous_pipeline.get_director_decision_sync", return_value=mock_decision):
            with patch("time.sleep", return_value=None):
                with pytest.raises(ChapterHaltedException) as exc_info:
                    svc._execute_stage_with_retry(
                        task=task,
                        stage="writer",
                        target={"chapter_index": 1},
                    )
                assert "HALT_CHAPTER" in str(exc_info.value) or "大綱衝突" in str(exc_info.value)


def test_retry_policy_limits_retries_per_stage():
    """每個階段最多使用設定的 retry 次數（如 writer: 3, editor: 3）"""
    svc = AutonomousPipelineManager()
    task = NovelPipelineTask(novel_id="test_novel")

    assert RETRY_POLICY["writer"] == 30
    assert RETRY_POLICY["editor"] == 30

    attempts_made = 0

    def mock_fail_task(*args, **kwargs):
        nonlocal attempts_made
        attempts_made += 1
        raise RuntimeError("持續連線逾時 TimeoutError")

    with patch.object(svc, "execute_generation_task", side_effect=mock_fail_task):
        with patch("time.sleep", return_value=None):
            with pytest.raises(RuntimeError):
                svc._execute_stage_with_retry(
                    task=task,
                    stage="writer",
                    target={"chapter_index": 1},
                )

    # 應執行 30 次（符合 RETRY_POLICY["writer"]）
    assert attempts_made == RETRY_POLICY["writer"]
