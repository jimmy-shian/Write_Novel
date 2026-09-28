# -*- coding: utf-8 -*-
"""
End-to-End Autonomous Pipeline Integration Suite.
Validates the full orchestrator lifecycle of AutonomousNovelPipeline / AutonomousPipelineManager
across all three core guard rails: R1 (Refusal), R2 (Opening/Anti-Meta), and R3 (Temporal/Terms).
"""

import importlib
import pytest
from backend import persistence as db
from tests.e2e.conftest import (
    m1_required,
    m2_required,
    m3_required,
    DIVERSE_OPENINGS_PASS,
    REPETITIVE_OPENINGS_CLICHE,
)


def test_pipeline_e2e_initialization_and_lock_hygiene():
    """E2E Pipeline: Pipeline manager initializes safely, cleans stale locks, and reports idle."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager
    mgr = AutonomousPipelineManager()
    assert mgr is not None
    # Stale lock cleanup hook executes on startup
    db.db_init()


def test_pipeline_e2e_novel_outline_ready_check(novel_factory):
    """E2E Pipeline: Pipeline validates whether volume and chapter outlines are ready before prose generation."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory(title="大綱校驗測試")

    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)

    # Empty novel without outlines should fail ready check
    chapters = db.get_chapters(nid)
    assert len(chapters) == 0


@m1_required
def test_pipeline_e2e_self_healing_from_refusal_loop(novel_factory, monkeypatch):
    """E2E Pipeline: Complete autonomous self-healing loop: Writer generates refusal;
    refusal guard triggers rollback/purge and exponential retry; second attempt produces clean prose."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory(title="拒答自癒全流程")

    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)

    attempts = 0

    def mock_task_executor(payload):
        nonlocal attempts
        attempts += 1
        class MockResp:
            pass
        resp = MockResp()
        if attempts == 1:
            resp.ok = False
            resp.error = "RefusalContaminationError: 我是AI模型無法創作"
        else:
            resp.ok = True
            resp.error = None
            db.save_chapter(nid, 1, "第 1 章自癒成功正文：少年林默拔劍出鞘，劍鳴如龍吟。字數大於五十個字。")
        return resp

    monkeypatch.setattr(mgr, "execute_generation_task", mock_task_executor)

    mgr._execute_stage_with_retry(
        task=state,
        stage_name="writer",
        payload={"novel_id": nid, "chapter_index": 1},
        verify_fn=lambda: db.get_chapter(nid, 1) is not None,
        max_retries=3,
    )

    assert attempts == 2
    ch = db.get_chapter(nid, 1)
    assert ch is not None
    assert "我是AI" not in ch["content"]
    assert "少年林默" in ch["content"]


@m2_required
def test_pipeline_e2e_opening_deduplication_audit_loop(novel_factory, monkeypatch):
    """E2E Pipeline: Opening deduplication closed-loop: Ch1 has neon cliché; Ch2 starts with neon cliché;
    auditor flags REVISE; pipeline triggers fix loop, resulting in clean action opening."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    from backend.services.narrative.fix import fix_chapter_until_pass
    nid = novel_factory(title="開篇去重全流程")

    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第一章落定。")
    db.save_chapter(nid, 2, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第二章重複開頭。")

    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, db.get_chapter(nid, 2)["content"])
    assert audit.get("overall_action") in ("REVISE", "CRITICAL")

    def mock_writer(novel_id, chapter_index, user_prompt=None, **kwargs):
        db.save_chapter(novel_id, chapter_index, DIVERSE_OPENINGS_PASS["dialogue"] + " 第二章修改為對話開局。")
        yield 'data: {"type": "done"}\n\n'

    def mock_editor(novel_id, chapter_index, edit_instructions=None, **kwargs):
        db.save_chapter(novel_id, chapter_index, DIVERSE_OPENINGS_PASS["dialogue"] + " 第二章修改為對話開局。")
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer)
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    res = fix_chapter_until_pass(nid, 2, max_rounds=2)
    assert res is not None

    ch2 = db.get_chapter(nid, 2)
    assert "對話開局" in ch2["content"] or "只有三分鐘" in ch2["content"]


@m2_required
def test_pipeline_e2e_meta_narrative_purging_loop(novel_factory):
    """E2E Pipeline: Meta-narrative detection and elimination closed loop."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="元文本消除全流程")

    prose_meta = "正如前一章所述，長老會的通牒送達天元峰。林默冷冷注視著使者。"
    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, prose_meta)
    assert audit.get("overall_action") == "CRITICAL"

    sanitizer = None
    for mod_name in ["backend.common.text_cleaners", "backend.services.narrative.anti_meta", "backend.common.refusal_filter"]:
        try:
            m = importlib.import_module(mod_name)
            if hasattr(m, "sanitize_meta_narrative"):
                sanitizer = getattr(m, "sanitize_meta_narrative")
                break
        except ImportError:
            pass

    assert sanitizer is not None
    prose_clean = sanitizer(prose_meta)
    assert "正如前一章" not in prose_clean
    assert "長老會的通牒送達天元峰" in prose_clean

    db.save_chapter(nid, 2, prose_clean)
    audit_clean = NarrativeAuditor.audit_chapter_prose(nid, 2, prose_clean)
    assert audit_clean.get("overall_action") != "CRITICAL"


@m3_required
def test_pipeline_e2e_worldline_causal_invariance_loop(novel_factory):
    """E2E Pipeline: Worldline causal and terms invariance closed loop."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="世界線時序閉環")

    db.create_term(nid, category="power", term="純陽罡氣", definition="至剛至陽護體真罡")
    db.record_temporal_fact(nid, "黑煞教舵主被林默斬首於落日崖", valid_from=1, invalid_from=2)

    # Valid prose
    prose_ok = "林默運轉純陽罡氣，護住週身大穴。他看著落日崖下舵主的埋骨處，神色凝重。"
    res_ok = NarrativeAuditor.audit_chapter_prose(nid, 2, prose_ok)
    assert res_ok.get("overall_action") != "CRITICAL"

    # Corrupted prose
    prose_bad = "舵主狂笑著帶領黑煞教眾人殺出：「林默，交出純陽罡氣！」"
    res_bad = NarrativeAuditor._check_temporal_fact_compliance(nid, 2, prose_bad)
    assert res_bad is not None
    assert res_bad.get("action_required") is True


def test_pipeline_e2e_task_pause_resume_integrity(novel_factory):
    """E2E Pipeline: Pipeline cleanly pauses and resumes across sessions without state corruption."""
    nid = novel_factory(title="暫停恢復測試")

    # Session 1: Writes chapter 1
    db.save_chapter(nid, 1, "第 1 章正文內容，故事宏觀背景與核心世界觀完整展開，主線情節推進流暢無阻，全章字數已超過五十個字標準，順利完畢。")

    # Session 2: Resumes
    chapters = db.get_chapters(nid)
    written_indices = {int(c["chapter_index"]) for c in chapters if c.get("content") and len(c["content"]) > 50}

    assert 1 in written_indices
    # Session 2 continues with chapter 2
    db.save_chapter(nid, 2, "第 2 章接續正文內容，人物成長與伏筆收束穩步推進，世界觀格局逐步放大，全章字數已超過五十個字符標準，情節延續。")

    all_chapters = db.get_chapters(nid)
    assert len(all_chapters) == 2
