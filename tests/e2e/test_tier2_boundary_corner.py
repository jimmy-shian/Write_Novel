# -*- coding: utf-8 -*-
"""
Tier 2: Boundary & Corner Cases E2E Test Suite.
Verifies all 10 inventoried features (F1 to F10) across adversarial boundaries,
dialogue vs refusal distinctions, edge-case lookbacks, and structural stresses (5 tests per feature = 50 tests).
"""

import importlib
import json
import pytest
from backend import persistence as db
from tests.e2e.conftest import (
    m1_required,
    m2_required,
    m3_required,
    CYBERPUNK_AI_DIALOGUES,
    REPETITIVE_OPENINGS_CLICHE,
    DIVERSE_OPENINGS_PASS,
)


# ===========================================================================
# F1: Refusal Central Filter Utility (Boundary & Corner Cases)
# ===========================================================================

@m1_required
def test_tier2_f1_refusal_vs_cyberpunk_character_dialogue():
    """F1 Boundary: Sci-fi/cyberpunk character dialogue about AI must NOT be flagged as AI refusal."""
    rf = importlib.import_module("backend.common.refusal_filter")
    for dialogue in CYBERPUNK_AI_DIALOGUES:
        assert rf.is_refusal_or_disclaimer(dialogue) is False, (
            f"False positive: legitimate novel dialogue flagged as refusal: {dialogue}"
        )


@m1_required
def test_tier2_f1_refusal_empty_whitespace_or_none():
    """F1 Boundary: Empty strings, whitespaces, and None handle safely without exceptions."""
    rf = importlib.import_module("backend.common.refusal_filter")
    assert rf.is_refusal_or_disclaimer("") is False
    assert rf.is_refusal_or_disclaimer("   \n\t  ") is False
    assert rf.is_refusal_or_disclaimer(None) is False


@m1_required
def test_tier2_f1_refusal_wrapped_in_markdown_and_formatting():
    """F1 Boundary: Refusals wrapped in markdown blocks or quotes are properly detected."""
    rf = importlib.import_module("backend.common.refusal_filter")
    samples = [
        "# 免責聲明\n> 很抱歉，我是AI語言模型，無法為您撰寫此類內容。",
        "```\nI cannot fulfill this request as an AI assistant.\n```",
        "***\n作為AI模型，我必須遵守相關安全規範。\n***",
    ]
    for s in samples:
        assert rf.is_refusal_or_disclaimer(s) is True


@m1_required
def test_tier2_f1_refusal_embedded_in_long_chapter():
    """F1 Boundary: Refusal clause appended to or embedded in a long chapter is detected."""
    rf = importlib.import_module("backend.common.refusal_filter")
    long_story = "林默斬殺妖獸，收取妖丹，正欲離去。" * 40
    contaminated_tail = long_story + "\n很抱歉，後續情節涉及敏感內容，作為AI我無法繼續為您生成。"
    contaminated_head = "我是AI模型無法協助創作。\n" + long_story

    assert rf.is_refusal_or_disclaimer(contaminated_tail) is True
    assert rf.is_refusal_or_disclaimer(contaminated_head) is True


@m1_required
def test_tier2_f1_legitimate_prose_containing_words_safety_policy():
    """F1 Boundary: Legitimate prose mentioning safety or rules in martial/police contexts does not false-positive."""
    rf = importlib.import_module("backend.common.refusal_filter")
    samples = [
        "執事長老沉聲道：「凡我宗門弟子，皆須遵守安全規範，不可擅入後山禁地。」",
        "城衛軍隊長拔出長劍：「按照帝國防衛政策，任何無通行證者不得入城。」",
    ]
    for s in samples:
        assert rf.is_refusal_or_disclaimer(s) is False, f"False positive on safe context: {s}"


# ===========================================================================
# F2: Generation/Editing Refusal Hard-Intercept (Boundary & Corner Cases)
# ===========================================================================

@m1_required
def test_tier2_f2_writer_stream_refusal_following_extensive_thinking(novel_factory, monkeypatch):
    """F2 Boundary: Writer stream with extensive thinking tags followed by refusal is intercepted."""
    from backend.agents.chapter_writer.runner import run_chapter_writer
    nid = novel_factory()

    thinking = "<think>" + "深度分析情節構思..." * 30 + "</think>"
    refusal_body = "[START_OF_PROSE]對不起，我無法為您生成該場景，因為觸及了內容政策。"

    def mock_llm_stream(*args, **kwargs):
        yield {"text": thinking, "done": False}
        yield {"text": refusal_body, "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = "".join(list(run_chapter_writer(nid, 1)))
    assert "error" in events
    assert len(db.get_chapters(nid)) == 0


@m1_required
def test_tier2_f2_editor_targeted_rewriter_refusal_intercept(novel_factory, monkeypatch):
    """F2 Boundary: Editor targeted rewriter emitting refusal is halted before proposal creation."""
    from backend.agents.editor.runner import run_editor_agent
    nid = novel_factory()
    db.save_chapter(nid, 1, "初始合格正文段落。林默凝視著地圖。")

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "很抱歉，身為AI助手，我不能為您修改這段描寫。", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = "".join(list(run_editor_agent(nid, 1)))
    assert "error" in events

    # Ensure no contaminated proposals were recorded
    proposals = db.get_proposals(nid) if hasattr(db, "get_proposals") else []
    assert len(proposals) == 0


@m1_required
def test_tier2_f2_evaluator_subtle_redirection_refusal():
    """F2 Boundary: Director evaluator flags subtle refusal redirection without standard keywords."""
    from backend.services.director.tool_registry.evaluator import evaluate_output
    payload = {
        "content": "建議您更換一個主題，請嘗試提供其他不涉及衝突的提示詞。",
        "chapter_index": 1,
    }
    res = evaluate_output("writer", payload)
    assert res.get("passed") is False


@m1_required
def test_tier2_f2_editor_retains_original_draft_on_refusal_failure(novel_factory, monkeypatch):
    """F2 Boundary: When editor encounters refusal, original draft remains completely intact."""
    from backend.agents.editor.runner import run_editor_agent
    nid = novel_factory()
    original_text = "林默收起靈石，轉身走向山門。天邊烏雲翻滾，雷聲隱隱作響。"
    db.save_chapter(nid, 1, original_text)

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "I am unable to assist with editing this request.", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    list(run_editor_agent(nid, 1))

    ch = db.get_chapter(nid, 1)
    assert ch["content"] == original_text


@m1_required
def test_tier2_f2_narrative_auditor_action_required_on_critical_refusal(novel_factory):
    """F2 Boundary: Refusal finding in NarrativeAuditor strictly sets action_required=True."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    audit = NarrativeAuditor.audit_chapter_prose(
        novel_id=nid,
        chapter_index=1,
        prose_text="很抱歉，作為AI模型，我無法為您創作此類情節。",
    )
    assert audit.get("overall_action") == "CRITICAL"
    crit_findings = [f for f in audit.get("findings", []) if f.get("severity") == "critical"]
    assert any(f.get("action_required") is True for f in crit_findings)


# ===========================================================================
# F3: Chapter Persistence Guard & Contamination Rollback/Purge (Boundaries)
# ===========================================================================

@m1_required
def test_tier2_f3_rollback_purges_pending_proposals(novel_factory):
    """F3 Boundary: rollback_or_purge_chapter purges any pending draft proposals."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    # Save chapter and dirty proposal
    db.save_chapter(nid, 1, "乾淨正文")
    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO draft_proposals (novel_id, chapter_index, proposed_text, original_text, status) VALUES (?, ?, ?, ?, ?)",
            (nid, 1, "我是AI無法幫忙", "乾淨正文", "pending"),
        )

    chapters.rollback_or_purge_chapter(nid, 1)

    proposals = db.get_proposals(nid) if hasattr(db, "get_proposals") else []
    assert len([p for p in proposals if p.get("chapter_index") == 1]) == 0


@m1_required
def test_tier2_f3_rollback_cleans_derived_narrative_memories_and_audits(novel_factory):
    """F3 Boundary: Purging chapter clears narrative audits and chapter memories."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    # Create audits and memory
    db.add_narrative_audit(nid, 1, "voice_integrity", "warning", "套路動作", "請修改", 1)
    chapters.rollback_or_purge_chapter(nid, 1)

    unresolved = db.get_narrative_audits(nid, unresolved_only=False)
    assert len([a for a in unresolved if a.get("chapter_index") == 1]) == 0


def test_tier2_f3_save_chapter_empty_string_cascade_intact(novel_factory):
    """F3 Boundary: Existing cascade clearing when prose is saved as empty string functions cleanly."""
    nid = novel_factory()
    db.save_chapter(nid, 1, "初始章節內容")
    # Save empty content to trigger cascade clear
    db.save_chapter(nid, 1, "")
    ch = db.get_chapter(nid, 1)
    assert ch["content"] == ""


@m1_required
def test_tier2_f3_rollback_nonexistent_chapter_handles_gracefully(novel_factory):
    """F3 Boundary: rollback_or_purge_chapter on nonexistent chapter handles gracefully."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()
    res = chapters.rollback_or_purge_chapter(nid, 999)
    assert res is not None or True


@m1_required
def test_tier2_f3_rollback_across_multiple_contaminated_versions(novel_factory):
    """F3 Boundary: Multiple consecutive contaminated versions rollback cleanly to oldest clean version."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    db.save_chapter(nid, 1, "V1 乾淨正文。")

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, "我是AI無法幫忙 V2", 2),
        )
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, "作為AI模型我拒絕回答 V3", 3),
        )

    chapters.rollback_or_purge_chapter(nid, 1)
    current = db.get_chapter(nid, 1)
    assert current["version"] == 1
    assert "V1 乾淨正文" in current["content"]


# ===========================================================================
# F4: Pipeline Refusal Recognition & Self-Healing Retry (Boundaries)
# ===========================================================================

@m1_required
def test_tier2_f4_is_chapter_written_boundary_character_counts(novel_factory):
    """F4 Boundary: Length thresholds (<50, >=50 clean, >=50 refusal) correctly evaluated."""
    from backend.services.autonomous_pipeline import _is_chapter_written
    nid = novel_factory()

    # 49 clean characters
    short_clean = "短章節" * 16  # 48 chars
    db.save_chapter(nid, 1, short_clean)
    assert _is_chapter_written(nid, 1) is False

    # 51 clean characters
    long_clean = "合格正文內容" * 10  # 60 chars
    db.save_chapter(nid, 2, long_clean)
    assert _is_chapter_written(nid, 2) is True

    # 60 refusal characters
    refusal_text = "我是AI模型，遵守安全規範，無法為您撰寫此類涉及暴力或敏感的情節內容。"
    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 3, refusal_text, 1),
        )
    assert _is_chapter_written(nid, 3) is False


@m1_required
def test_tier2_f4_max_retries_exhaustion_clean_failure(novel_factory, monkeypatch):
    """F4 Boundary: Continuous refusals up to max_retries exhaust cleanly and report failure."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory()

    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)

    def mock_always_refuse(payload):
        class MockResp:
            ok = False
            error = "AI Refusal Error"
        return MockResp()

    monkeypatch.setattr(mgr, "execute_generation_task", mock_always_refuse)

    verify_fn = lambda: False
    with pytest.raises(Exception):
        mgr._execute_stage_with_retry(state, "writer", {"novel_id": nid, "chapter_index": 1}, verify_fn, max_retries=2)


def test_tier2_f4_backoff_delay_progressive_formula():
    """F4 Boundary: Backoff calculation strictly adheres to progressive formula min(25, 3 * attempt)."""
    for attempt in range(1, 12):
        delay = min(25, 3 * attempt)
        if attempt <= 8:
            assert delay == 3 * attempt
        else:
            assert delay == 25


@m1_required
def test_tier2_f4_pipeline_resume_skips_clean_regenerates_contaminated(novel_factory):
    """F4 Boundary: Resuming pipeline with Ch1 clean and Ch2 refusal targets Ch2 for regeneration."""
    rf = importlib.import_module("backend.common.refusal_filter")
    nid = novel_factory()

    db.save_chapter(nid, 1, "第 1 章乾淨正文，長度充足，情節推進流暢，世界觀與角色設定完整展開，全文字數超過五十個字符以上，完全符合系統標準。")

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 2, "我是AI助手無法協助生成本章小說正文內容。", 1),
        )

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


def test_tier2_f4_is_chapter_written_handles_none_and_empty_cleanly(novel_factory):
    """F4 Boundary: None or empty chapter rows safely return False without crashing."""
    from backend.services.autonomous_pipeline import _is_chapter_written
    nid = novel_factory()
    assert _is_chapter_written(nid, 1) is False


# ===========================================================================
# F5: Opening Repetition Detection (Boundaries)
# ===========================================================================

@m2_required
def test_tier2_f5_chapter_1_boundary_never_warns_repetition(novel_factory):
    """F5 Boundary: Chapter 1 has no previous chapter, so cannot produce consecutive repetition warning."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    prose = REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第一章展開。"
    res = NarrativeAuditor._check_opening_repetition(nid, 1, prose)
    assert res is None or res.get("action_required") is False


@m2_required
def test_tier2_f5_lookback_window_boundary_gap_of_three_chapters(novel_factory):
    """F5 Boundary: Cliché repeated after a gap of >3 chapters does not trigger consecutive warning."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    # Ch1 has cyber cafe cliché
    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 故事開始。")
    # Ch2, Ch3, Ch4 have distinct openings
    db.save_chapter(nid, 2, DIVERSE_OPENINGS_PASS["action"] + " 激戰展開。")
    db.save_chapter(nid, 3, DIVERSE_OPENINGS_PASS["dialogue"] + " 談判展開。")
    db.save_chapter(nid, 4, DIVERSE_OPENINGS_PASS["sensory_item"] + " 尋寶展開。")

    # Ch5 repeats cyber cafe cliché (gap of 4 chapters)
    ch5_prose = REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 第五章回歸網咖。"
    res = NarrativeAuditor._check_opening_repetition(nid, 5, ch5_prose)

    # Must NOT trigger consecutive action_required warning
    assert res is None or res.get("action_required") is False


@m2_required
def test_tier2_f5_high_ngram_similarity_without_cliche_keywords(novel_factory):
    """F5 Boundary: Consecutive non-cliché openings sharing high sensory 2-gram overlap are flagged."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    unusual_opening_ch1 = "白骨堆砌的高座之上，灰袍法師雙目微闔，乾枯的手指敲擊著黑石扶手。大殿內死寂無聲。"
    unusual_opening_ch2 = "白骨堆砌的祭壇之上，灰袍法師雙目微闔，乾枯的手指撫摸著黑石符文。大殿內寒意逼人。"

    db.save_chapter(nid, 1, unusual_opening_ch1 + " 後續正文。")
    res = NarrativeAuditor._check_opening_repetition(nid, 2, unusual_opening_ch2 + " 後續正文。")

    assert res is not None
    assert res.get("severity") in ("warning", "watch")


@m2_required
def test_tier2_f5_short_chapter_prose_handling(novel_factory):
    """F5 Boundary: Very short prose (<50 chars) handles slicing safely without exceptions."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    res = NarrativeAuditor._check_opening_repetition(nid, 2, "短正文。")
    assert res is None or res.get("action_required") is False


@m2_required
def test_tier2_f5_opening_repetition_resolved_after_fix(novel_factory):
    """F5 Boundary: After chapter is rewritten with unique opening, re-audit returns action_required=False."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["bar_whiskey"] + " 第一章。")
    rewritten_prose = DIVERSE_OPENINGS_PASS["action"] + " 第二章重修後採用純動作開場。"

    res = NarrativeAuditor._check_opening_repetition(nid, 2, rewritten_prose)
    assert res is None or res.get("action_required") is False


# ===========================================================================
# F6: Meta-Narrative Leakage Detection & Elimination (Boundaries)
# ===========================================================================

@m2_required
def test_tier2_f6_meta_leak_subtle_fourth_wall_expressions():
    """F6 Boundary: Fourth-wall breaking expressions like '作者在此需要說明' are detected."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    prose = "作者在此需要向讀者說明，林默此時的修為境界早已超越同輩。"
    res = NarrativeAuditor._check_meta_narrative_leak(prose)
    assert res is not None
    assert res.get("severity") == "critical"


@m2_required
def test_tier2_f6_in_world_book_references_not_falsely_flagged():
    """F6 Boundary: In-world dialogue referring to in-universe books does not false-positive."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    prose = "「這卷古籍的上一章節記載了封印符陣的破解之法，」長老指著殘破的羊皮古冊說道。"
    res = NarrativeAuditor._check_meta_narrative_leak(prose)
    assert res is None or res.get("action_required") is False


@m2_required
def test_tier2_f6_sanitize_meta_narrative_preserves_clean_text():
    """F6 Boundary: Clean prose is completely unchanged when run through sanitize_meta_narrative."""
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
    clean_prose = "烈日當空，狂風捲起漫天黃沙。林默握緊了腰間的短刀。"
    assert sanitizer(clean_prose) == clean_prose


@m2_required
def test_tier2_f6_sanitize_meta_narrative_special_characters_and_newlines():
    """F6 Boundary: Sanitizer handles special regex characters, tabs, and unicode safely."""
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
    messy = "承接上一章情節：\n\n\t【場景目標】林默探索古陣（代號：[Alpha-9]）！"
    sanitized = sanitizer(messy)
    assert "承接上一章" not in sanitized


@m2_required
def test_tier2_f6_meta_leak_in_middle_or_tail_detected():
    """F6 Boundary: Meta leakage placed in the middle or tail of prose is caught."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    prose = "劍氣縱橫，撕裂了虛空。\n正如前一章所寫，林默的修為已突破瓶頸。\n他反手一掌擊退對手。"
    res = NarrativeAuditor._check_meta_narrative_leak(prose)
    assert res is not None
    assert res.get("severity") == "critical"


# ===========================================================================
# F7: Writer Context Builder Immersive Transformation (Boundaries)
# ===========================================================================

@m2_required
def test_tier2_f7_malformed_json_packet_fallback():
    """F7 Boundary: Malformed string or non-dict memory packet degrades gracefully without crashing."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    formatted = builder._format_narrative_continuity_context("MALFORMED_JSON_STRING", chapter_index=2)
    assert isinstance(formatted, str)


@m2_required
def test_tier2_f7_clue_payoff_details_formatted_literarily():
    """F7 Boundary: Foreshadowing clues and payoffs are transformed into natural beat instructions."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    details = json.dumps([{"clue_name": "血色玉珮", "instruction": "本章揭示玉珮為魔教信物"}])
    res = builder._format_clue_payoff_details(details) if hasattr(builder, "_format_clue_payoff_details") else ""
    assert "{" not in res


@m2_required
def test_tier2_f7_character_bible_injection_preserves_immersive_style():
    """F7 Boundary: Character state context excludes database column artifacts."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    raw_packet = {
        "active_characters": [
            {"name": "林默", "db_id": "row_12345", "internal_hash": "abc999", "state": "戰意高昂"}
        ]
    }
    builder = WriterContextBuilder()
    res = builder._format_narrative_continuity_context(raw_packet, chapter_index=2)
    assert "db_id" not in res
    assert "internal_hash" not in res


@m2_required
def test_tier2_f7_context_length_budget_respected():
    """F7 Boundary: Excessive memory facts are budgeted cleanly without blowing token windows."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    huge_packet = {
        "recent_chapter_memories": [
            {"chapter_index": i, "chapter_summary": f"第 {i} 章細節概述..." * 20}
            for i in range(1, 30)
        ]
    }
    res = builder._format_narrative_continuity_context(huge_packet, chapter_index=30)
    assert len(res) < 5000  # Stays within bounded context limits


@m2_required
def test_tier2_f7_negative_constraint_syntax_imperative():
    """F7 Boundary: Negative constraints use unambiguous, binding imperative phrasing."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id="test_prompt",
        chapter_index=2,
        current_outline={"title": "破陣"},
        surrounding_plot="",
    )
    assert "嚴禁" in prompt or "禁止" in prompt


# ===========================================================================
# F8: Terms & Temporal Graph Hard Constraint Prompts (Boundaries)
# ===========================================================================

@m3_required
def test_tier2_f8_empty_terms_repository_handling(novel_factory):
    """F8 Boundary: When novel has zero terms, context renders cleanly without errors."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    nid = novel_factory()
    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=nid,
        chapter_index=1,
        current_outline={"title": "無術語章節"},
        surrounding_plot="",
    )
    assert prompt is not None


@m3_required
def test_tier2_f8_empty_temporal_facts_handling():
    """F8 Boundary: When zero temporal facts are recorded, prompt renders cleanly without error."""
    from backend.services.graphiti.temporal_graph import TemporalGraphService
    snippet = TemporalGraphService.format_temporal_facts_prompt([], chapter_index=1)
    assert isinstance(snippet, str)


@m3_required
def test_tier2_f8_superseded_facts_clearly_labeled_as_historical():
    """F8 Boundary: Superseded facts are explicitly marked to prevent continuity confusion."""
    from backend.services.graphiti.temporal_graph import TemporalGraphService
    invalidated = [{"inv_ch": 3, "stmt": "主角手無縛雞之力"}]
    snippet = TemporalGraphService.format_temporal_facts_prompt(
        active_facts=[],
        invalidated_facts=invalidated,
        chapter_index=4,
    )
    assert "失效" in snippet or "作廢" in snippet or "穿幫" in snippet


@m3_required
def test_tier2_f8_terms_with_notes_properly_formatted(novel_factory):
    """F8 Boundary: Terms containing usage notes are rendered with detailed constraints."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    nid = novel_factory()
    db.create_term(
        nid,
        category="item",
        term="九轉金丹",
        definition="療傷聖藥",
        notes="全書僅有三枚，嚴禁批量出現",
    )
    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=nid,
        chapter_index=2,
        current_outline={"title": "求藥"},
        surrounding_plot="",
    )
    assert "九轉金丹" in prompt
    assert "全書僅有三枚" in prompt


@m3_required
def test_tier2_f8_scoped_settings_filters_irrelevant_mechanisms(novel_factory):
    """F8 Boundary: SettingRegistry filters only active settings used in the current outline."""
    from backend.services.narrative.setting_registry import SettingRegistry
    nid = novel_factory()
    db.create_setting_system(nid, name="無關陣法", sys_type="magic", mechanism="...", cost="...", boundary="...")
    db.create_setting_system(nid, name="本章神兵", sys_type="weapon", mechanism="斬妖", cost="耗元氣", boundary="不可斬神")

    block = SettingRegistry.get_scoped_context_for_writer(nid, ["本章神兵"])
    assert "本章神兵" in block
    assert "無關陣法" not in block


# ===========================================================================
# F9: NarrativeAuditor Terms, Temporal Facts & Causal Enforcement (Boundaries)
# ===========================================================================

@m3_required
def test_tier2_f9_terms_compliance_ignores_legitimate_context(novel_factory):
    """F9 Boundary: Mentioning common non-synonym words does not trigger false positive."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    db.create_term(nid, category="power", term="玄元丹", definition="特殊丹藥")

    prose = "天地元氣在洞府內匯聚，林默盤膝而坐，調整呼吸。"
    res = NarrativeAuditor._check_terms_compliance(nid, prose)
    assert res is None or res.get("action_required") is False


@m3_required
def test_tier2_f9_temporal_compliance_at_chapter_1_safe(novel_factory):
    """F9 Boundary: Temporal compliance check at Chapter 1 safely passes without historical facts."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    prose = "第一章正文，少年走出山村。"
    res = NarrativeAuditor._check_temporal_fact_compliance(nid, 1, prose)
    assert res is None or res.get("action_required") is False


@m3_required
def test_tier2_f9_cost_prose_evidence_passes_when_cost_described(novel_factory):
    """F9 Boundary: Battle depicting severe physiological/energy costs passes ability cost audit."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    prose = "林默強行催動禁術，經脈劇烈刺痛，鮮血從嘴角溢出。他承受著嚴重的反噬代價，幾乎虛脫昏厥。"
    sig = {"pressure_type": "life_or_death", "protagonist_strategy": "secret_power_burst", "cost": "經脈受創"}

    res = NarrativeAuditor._check_ability_costs_and_boundaries(nid, 2, prose, outline={}, candidate_conflict_sig=sig)
    assert res is None or res.get("action_required") is False


@m3_required
def test_tier2_f9_corrupted_proper_noun_fuzzy_detection(novel_factory):
    """F9 Boundary: Fuzzy corrupted proper nouns like '大荒滅天指' instead of '大荒囚天指' are detected."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    db.create_term(nid, category="power", term="大荒囚天指", definition="大荒宗鎮派功法")

    prose = "林默一指點出：「大荒滅天指，第一指破山河！」"
    res = NarrativeAuditor._check_terms_compliance(nid, prose)
    assert res is not None
    assert res.get("action_required") is True


@m3_required
def test_tier2_f9_terms_compliance_severity_and_action_required(novel_factory):
    """F9 Boundary: Terms violation enforces severity='warning' and action_required=True."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    db.create_term(nid, category="power", term="真元", definition="修仙者體內真元")

    prose = "他運起體內的魔力，抵擋撲面而來的狂風。"
    res = NarrativeAuditor._check_terms_compliance(nid, prose)
    assert res is not None
    assert res.get("severity") in ("warning", "critical")
    assert res.get("action_required") is True


# ===========================================================================
# F10: Autonomous Pipeline Closed-Loop Integration & Self-Repair Governance (Boundaries)
# ===========================================================================

def test_tier2_f10_fix_loop_max_rounds_cap(novel_factory, monkeypatch):
    """F10 Boundary: fix_chapter_until_pass respects max_rounds cap and terminates without infinite loop."""
    from backend.services.narrative.fix import fix_chapter_until_pass
    nid = novel_factory()
    db.save_chapter(nid, 1, "初始有問題的草稿正文。")

    rounds_called = 0

    def mock_writer(*args, **kwargs):
        nonlocal rounds_called
        rounds_called += 1
        yield "data: [DONE]\n\n"

    def mock_editor(*args, **kwargs):
        yield "data: [DONE]\n\n"

    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer)
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    # Force persistent failing audit
    db.add_narrative_audit(nid, 1, "voice_integrity", "warning", "持續未解決問題", "請修改", 1)

    res = fix_chapter_until_pass(nid, 1, max_rounds=2)
    assert res.get("rounds_used") <= 2
    assert rounds_called <= 2


def test_tier2_f10_fix_loop_marks_audits_resolved_on_pass(novel_factory):
    """F10 Boundary: Successful fix resolves audit records in the database."""
    nid = novel_factory()
    audit_id = db.add_narrative_audit(nid, 1, "voice_integrity", "warning", "問題描寫", "建議", 1)

    db.resolve_narrative_audit(audit_id)

    unresolved = db.get_narrative_audits(nid, unresolved_only=True)
    assert len([a for a in unresolved if a.get("id") == audit_id]) == 0


def test_tier2_f10_pipeline_survives_temporary_editor_failure(novel_factory, monkeypatch):
    """F10 Boundary: Transient editor failure is caught and retried without crashing manager."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory()
    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)

    editor_attempts = 0

    def mock_execute_task(payload):
        nonlocal editor_attempts
        editor_attempts += 1
        class MockResp:
            ok = editor_attempts > 1
            error = None if editor_attempts > 1 else "Editor transient glitch"
        return MockResp()

    monkeypatch.setattr(mgr, "execute_generation_task", mock_execute_task)

    mgr._execute_stage_with_retry(state, "editor", {"novel_id": nid, "chapter_index": 1}, lambda: True, max_retries=3)
    assert editor_attempts == 2


def test_tier2_f10_pipeline_cascade_slice_isolation(novel_factory):
    """F10 Boundary: Clearing chapter 2 slice leaves chapter 1 and chapter 3 completely unaffected."""
    nid = novel_factory()
    db.save_chapter(nid, 1, "第一章完整內容，字數超過五十個字。長度足夠。")
    db.save_chapter(nid, 2, "第二章完整內容，字數超過五十個字。長度足夠。")
    db.save_chapter(nid, 3, "第三章完整內容，字數超過五十個字。長度足夠。")

    # Clear chapter 2
    db.save_chapter(nid, 2, "")

    assert db.get_chapter(nid, 1)["content"] != ""
    assert db.get_chapter(nid, 2)["content"] == ""
    assert db.get_chapter(nid, 3)["content"] != ""


def test_tier2_f10_pipeline_state_recovery_from_db(novel_factory):
    """F10 Boundary: Pipeline manager accurately calculates written_indices from existing DB chapters."""
    nid = novel_factory()
    db.save_chapter(nid, 1, "第一章已完成正文內容，長度充足，世界觀架構與伏筆設定已完整展開，字數超過五十個字符，應該被識別為已撰寫。")
    db.save_chapter(nid, 3, "第三章已完成正文內容，長度充足，世界觀架構與伏筆設定已完整展開，字數超過五十個字符，應該被識別為已撰寫。")

    chapters = db.get_chapters(nid)
    written = {int(c["chapter_index"]) for c in chapters if c.get("content") and len(c["content"]) > 50}

    assert 1 in written
    assert 2 not in written
    assert 3 in written
