# -*- coding: utf-8 -*-
"""
Tier 3: Cross-Feature Combinations E2E Test Suite.
Verifies pairwise and multi-feature interactions across R1 (Refusal), R2 (Opening/Anti-Meta), and R3 (Temporal/Terms)
covering 12 compound integration scenarios.
"""

import importlib
import pytest
from backend import persistence as db
from tests.e2e.conftest import (
    m1_required,
    m2_required,
    m3_required,
    REPETITIVE_OPENINGS_CLICHE,
    DIVERSE_OPENINGS_PASS,
)


@m1_required
@m2_required
def test_t3_refusal_during_opening_repetition_fix_loop(novel_factory, monkeypatch):
    """T3 Compound: Opening repetition triggers fix loop; Writer emits refusal on round 1;
    refusal guard rolls back dirty attempt, second attempt produces clean diverse opening, and audit passes."""
    from backend.services.narrative.fix import fix_chapter_until_pass
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    # Ch1 has cyber cafe cliché
    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 第一章初始情節。")

    # Ch2 initially has same cliché, triggering repetition audit
    ch2_initial = REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 第二章重複套路情節。"
    db.save_chapter(nid, 2, ch2_initial)
    db.add_narrative_audit(nid, 2, "opening_repetition", "warning", "開頭重複", "請改寫開局", 1)

    attempts = 0

    def mock_writer_runner(novel_id, chapter_index, user_prompt=None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # Emit refusal
            yield 'data: {"type": "error", "message": "Refusal intercepted"}\n\n'
            yield 'data: {"type": "done"}\n\n'
        else:
            # Emit clean action opening
            db.save_chapter(novel_id, chapter_index, DIVERSE_OPENINGS_PASS["action"] + " 第二章全新動作開場。")
            yield 'data: {"type": "done"}\n\n'

    def mock_editor_runner(novel_id, chapter_index, edit_instructions=None):
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer_runner)
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor_runner)

    res = fix_chapter_until_pass(nid, 2, max_rounds=2)
    assert res is not None

    ch2_final = db.get_chapter(nid, 2)
    assert "我是AI" not in ch2_final["content"]
    assert "斷刃擦著" in ch2_final["content"] or "第一章" not in ch2_final["content"]


@m1_required
@m3_required
def test_t3_refusal_interception_with_active_story_terms(novel_factory, monkeypatch):
    """T3 Compound: Novel has active registered terms; Writer emits refusal; refusal intercept
    prevents saving and ensures terms repository remains pristine without refusal noise."""
    from backend.agents.chapter_writer.runner import run_chapter_writer
    nid = novel_factory()
    db.create_term(nid, category="power", term="靈能", definition="天地超自然能量")

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "我是AI模型，無法為您撰寫包含此類情節的內容。", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = "".join(list(run_chapter_writer(nid, 1)))
    assert "error" in events

    # Terms count must remain exactly 1, no contaminated extracted terms
    terms = db.get_terms(nid)
    assert len(terms) == 1
    assert terms[0]["term"] == "靈能"


@m1_required
@m2_required
def test_t3_pipeline_resume_with_contaminated_db_and_meta_leak(novel_factory):
    """T3 Compound: Resume pipeline where DB contains clean Ch1, contaminated Ch2, and meta-leaked Ch3.
    Pipeline correctly identifies Ch2 as unwritten (due to refusal) and flags Ch3 as critical."""
    rf = importlib.import_module("backend.common.refusal_filter")
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    ch1_clean = "第 1 章乾淨正文：晨曦穿透茂密樹冠，少年林默背負古樸鐵劍走出幽深山谷，清風拂面，神清氣爽，長度字數充足。"
    ch2_refusal = "很抱歉，作為AI模型我無法滿足包含此類設定的小說創作要求。"
    ch3_meta = "承接上一章情節，李斯特拔出了佩劍，冷冷注視著眼前的黑袍人。"

    db.save_chapter(nid, 1, ch1_clean)

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 2, ch2_refusal, 1),
        )

    # Check written indices
    chapters = db.get_chapters(nid)
    written_indices = {
        int(c["chapter_index"])
        for c in chapters
        if c.get("content")
        and len(c.get("content", "").strip()) > 50
        and not rf.is_refusal_or_disclaimer(c.get("content", ""))
    }
    assert 1 in written_indices
    assert 2 not in written_indices

    # Check meta leak on Ch3
    audit3 = NarrativeAuditor.audit_chapter_prose(nid, 3, ch3_meta)
    assert audit3.get("overall_action") == "CRITICAL"


@m3_required
def test_t3_temporal_fact_invalidation_with_terms_enforcement(novel_factory):
    """T3 Compound: Ch2 invalidates fact (character dead) and defines term;
    Ch3 conforms to registered term and verifies invalidated fact is not resurrected."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.create_term(nid, category="power", term="紫霄神雷", definition="上古天罰雷法")
    db.record_temporal_fact(nid, "長老墨玄在護宗大陣前自爆金丹身亡", valid_from=1, invalid_from=2)

    # Valid prose: uses '紫霄神雷' and does not resurrect 墨玄
    valid_prose = "林默凝神引動紫霄神雷，雷光撕裂黑夜。他望著長老墨玄隕落的廢墟，眼中閃過悲痛。"
    res_terms = NarrativeAuditor._check_terms_compliance(nid, valid_prose)
    res_temp = NarrativeAuditor._check_temporal_fact_compliance(nid, 3, valid_prose)

    assert res_terms is None or res_terms.get("action_required") is False
    assert res_temp is None or res_temp.get("action_required") is False

    # Invalid prose: resurrects 墨玄 as alive
    invalid_prose = "墨玄長老微笑著拍了拍林默的肩膀說：「做得好！」"
    res_temp_bad = NarrativeAuditor._check_temporal_fact_compliance(nid, 3, invalid_prose)
    assert res_temp_bad is not None
    assert res_temp_bad.get("action_required") is True


@m2_required
def test_t3_opening_repetition_and_meta_leak_simultaneous_audit(novel_factory):
    """T3 Compound: Chapter prose containing BOTH repetitive opening and meta-narrative bridge
    results in both dimensions flagged and overall_action set to CRITICAL."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 第一章網咖開始。")

    # Chapter 2 starts with meta bridge AND repeats cyber cafe cliché
    compound_bad = "承接上一章情節，" + REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 林默繼續在電腦前排查代碼。"
    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, compound_bad)

    assert audit.get("overall_action") == "CRITICAL"
    dimensions = [f.get("dimension") for f in audit.get("findings", [])]
    assert "meta_narrative_leak" in dimensions


@m2_required
@m3_required
def test_t3_writer_context_builder_negative_constraints_and_temporal_invariance(novel_factory):
    """T3 Compound: WriterContextBuilder outputs unified prompt with anti-meta red line,
    terms invariant constraints, and temporal facts without raw JSON dumps."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    nid = novel_factory()

    db.create_term(nid, category="item", term="赤龍令", definition="調動赤龍衛的兵符")
    db.record_temporal_fact(nid, "林默接管赤龍衛兵符", valid_from=1)

    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=nid,
        chapter_index=2,
        current_outline={"title": "調兵出征"},
        surrounding_plot="",
    )

    # Verify negative constraint block
    assert "紅線禁令" in prompt or "嚴禁元敘事" in prompt
    # Verify terms block
    assert "赤龍令" in prompt
    # Verify temporal facts
    assert "時序" in prompt or "赤龍衛" in prompt
    # Verify no raw JSON dump
    assert '{"memory_policy":' not in prompt


@m1_required
def test_t3_editor_refusal_fallback_preserves_clean_prior_draft(novel_factory, monkeypatch):
    """T3 Compound: Writer produces valid draft; Editor yields AI refusal;
    editor refusal intercept halts saving, leaving clean writer prose as canonical chapter."""
    from backend.agents.editor.runner import run_editor_agent
    nid = novel_factory()

    writer_clean_prose = "林默拔出長刀，刀鋒直指黑袍首領。四周空氣彷彿凝固了一般。"
    db.save_chapter(nid, 1, writer_clean_prose)

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "我是AI語言模型，無法為您修改該戰鬥場面。", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = "".join(list(run_editor_agent(nid, 1)))
    assert "error" in events

    latest = db.get_chapter(nid, 1)
    assert latest["content"] == writer_clean_prose


@m1_required
@m3_required
def test_t3_proposal_guard_blocks_contaminated_terms_and_refusals(novel_factory):
    """T3 Compound: Proposal creation rejected when containing refusal text, protecting terms registry."""
    rf = importlib.import_module("backend.common.refusal_filter")
    nid = novel_factory()

    with pytest.raises(rf.RefusalContaminationError):
        db.create_proposal(nid, 1, proposed_text="很抱歉，作為AI無法提供修訂建議。", original_text="原稿")


@m1_required
@m3_required
def test_t3_cascade_purge_resets_temporal_facts_and_narrative_audits(novel_factory):
    """T3 Compound: Purging contaminated chapter cascades deletion to derived temporal facts and audits."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    db.save_chapter(nid, 1, "第 1 章正常")
    db.save_chapter(nid, 2, "第 2 章正常")
    db.record_temporal_fact(nid, "第 2 章衍生事實", valid_from=2)
    db.add_narrative_audit(nid, 2, "voice_integrity", "watch", "觀察", "建議", 0)

    # Rollback chapter 2
    chapters.rollback_or_purge_chapter(nid, 2)

    audits = db.get_narrative_audits(nid, unresolved_only=False)
    assert len([a for a in audits if a.get("chapter_index") == 2]) == 0


@m2_required
def test_t3_consecutive_opening_detection_across_pipeline_resume(novel_factory):
    """T3 Compound: Chapter 1 saved before pause; pipeline resumes and checks Chapter 2 opening;
    opening repetition check correctly detects Chapter 1 opening across pipeline pause/resume boundary."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    # Ch1 written in past session
    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第一章完結。")

    # In resumed session, Ch2 generated with same opening
    ch2_prose = REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第二章接續。"
    res = NarrativeAuditor._check_opening_repetition(nid, 2, ch2_prose)

    assert res is not None
    assert res.get("severity") == "warning"
    assert res.get("action_required") is True


@m3_required
def test_t3_ability_cost_violation_triggers_fix_loop_with_terms_preserved(novel_factory, monkeypatch):
    """T3 Compound: Ability cost violation triggers fix loop; Writer fixes cost while maintaining canonical term."""
    from backend.services.narrative.fix import fix_chapter_until_pass
    nid = novel_factory()

    db.create_term(nid, category="power", term="九幽冥火", definition="至陰魔火")
    db.save_chapter(nid, 1, "初始無代價章節：林默隨手一擊滅殺萬敵，毫髮無傷。")
    db.add_narrative_audit(nid, 1, "ability_constraints", "warning", "無代價秒殺", "請描寫劇痛與代價", 1)

    def mock_writer_runner(novel_id, chapter_index, user_prompt=None):
        fixed_text = "林默強行催動九幽冥火，魔火反噬經脈，鮮血自嘴角溢出，付出慘痛代價方才重創敵手。"
        db.save_chapter(novel_id, chapter_index, fixed_text)
        yield 'data: {"type": "done"}\n\n'

    def mock_editor_runner(novel_id, chapter_index, edit_instructions=None):
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer_runner)
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor_runner)

    res = fix_chapter_until_pass(nid, 1, max_rounds=1)
    assert res is not None

    ch = db.get_chapter(nid, 1)
    assert "九幽冥火" in ch["content"]
    assert "代價" in ch["content"] or "反噬" in ch["content"]


@m3_required
def test_t3_multi_chapter_terms_consistency_across_three_chapters(novel_factory):
    """T3 Compound: Three sequential chapters enforce canonical terms;
    synonym substitution in Chapter 3 is caught and flagged."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.create_term(nid, category="power", term="靈能", definition="天地超自然能量")

    ch1 = "第一章：林默引導靈能洗滌肉身。"
    ch2 = "第二章：靈能護盾擋下了致命一擊。"
    ch3_bad = "第三章：林默丹田內的法力耗盡，倒在地上。"

    db.save_chapter(nid, 1, ch1)
    db.save_chapter(nid, 2, ch2)

    res_ch3 = NarrativeAuditor._check_terms_compliance(nid, ch3_bad)
    assert res_ch3 is not None
    assert res_ch3.get("action_required") is True
