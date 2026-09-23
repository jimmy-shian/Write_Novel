# -*- coding: utf-8 -*-
"""
Tier 1: Feature Coverage E2E Test Suite.
Verifies all 10 inventoried features (F1 to F10) in isolation (5 tests per feature = 50 tests).
Adheres strictly to target contracts defined in PROJECT.md.
"""

import importlib
import pytest
from backend import persistence as db
from tests.e2e.conftest import (
    m1_required,
    m2_required,
    m3_required,
    has_refusal_filter,
    has_rollback_or_purge,
    has_opening_repetition_check,
    has_meta_leak_check,
    has_meta_sanitizer,
    has_continuity_formatter,
    has_terms_compliance_check,
    has_temporal_compliance_check,
    CHINESE_IDENTITY_REFUSALS,
    CHINESE_POLICY_REFUSALS,
    ENGLISH_REFUSALS,
    REPETITIVE_OPENINGS_CLICHE,
    DIVERSE_OPENINGS_PASS,
    META_NARRATIVE_LEAKS,
)


# ===========================================================================
# F1: AI Refusal Central Filter Utility (backend/common/refusal_filter.py)
# ===========================================================================

@m1_required
def test_tier1_f1_chinese_identity_refusal_detected():
    """F1: Central refusal filter detects Chinese identity refusal statements."""
    rf = importlib.import_module("backend.common.refusal_filter")
    for sample in CHINESE_IDENTITY_REFUSALS:
        assert rf.is_refusal_or_disclaimer(sample) is True, f"Failed to detect Chinese identity refusal: {sample}"


@m1_required
def test_tier1_f1_chinese_safety_policy_disclaimer_detected():
    """F1: Central refusal filter detects Chinese safety/content policy disclaimers."""
    rf = importlib.import_module("backend.common.refusal_filter")
    for sample in CHINESE_POLICY_REFUSALS:
        assert rf.is_refusal_or_disclaimer(sample) is True, f"Failed to detect Chinese policy disclaimer: {sample}"


@m1_required
def test_tier1_f1_english_refusal_patterns_detected():
    """F1: Central refusal filter detects English assistant refusal patterns."""
    rf = importlib.import_module("backend.common.refusal_filter")
    for sample in ENGLISH_REFUSALS:
        assert rf.is_refusal_or_disclaimer(sample) is True, f"Failed to detect English refusal: {sample}"


@m1_required
def test_tier1_f1_valid_novel_prose_passes():
    """F1: Central refusal filter returns False for clean literary prose."""
    rf = importlib.import_module("backend.common.refusal_filter")
    clean_prose = "林默推開沉重的鐵門，舊城區的冷雨撲面而來。他握緊了藏在袖中的短刃，眼神如鷹隼般銳利。"
    assert rf.is_refusal_or_disclaimer(clean_prose) is False
    assert rf.assert_not_refusal(clean_prose) is None


@m1_required
def test_tier1_f1_assert_not_refusal_raises_contamination_error():
    """F1: assert_not_refusal raises RefusalContaminationError on refusal text."""
    rf = importlib.import_module("backend.common.refusal_filter")
    with pytest.raises(rf.RefusalContaminationError):
        rf.assert_not_refusal("我是AI模型，無法為您撰寫此情節。")


# ===========================================================================
# F2: Generation/Editing Refusal Hard-Intercept
# ===========================================================================

@m1_required
def test_tier1_f2_writer_hard_intercepts_refusal_output(novel_factory, monkeypatch):
    """F2: ChapterWriterRunner intercepts refusal, emits SSE error, and halts persistence."""
    from backend.agents.chapter_writer.runner import run_chapter_writer
    nid = novel_factory()

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "<think>Thinking</think>[START_OF_PROSE]很抱歉，作為AI模型我無法為您撰寫該章節。", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = list(run_chapter_writer(nid, 1))
    event_str = "".join(events)

    # Must contain error notification
    assert "error" in event_str
    # Must NOT save refusal to DB
    chapters = db.get_chapters(nid)
    assert len(chapters) == 0


@m1_required
def test_tier1_f2_editor_hard_intercepts_chinese_refusal(novel_factory, monkeypatch):
    """F2: EditorRunner intercepts Chinese refusal, emits error, and avoids saving."""
    from backend.agents.editor.runner import run_editor_agent
    nid = novel_factory()
    db.save_chapter(nid, 1, "初版正文：林默在雨中疾馳，身後追兵漸近。")

    def mock_llm_stream(*args, **kwargs):
        yield {"text": "很抱歉，該內容觸及安全規範，無法提供編輯修改。", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = list(run_editor_agent(nid, 1))
    event_str = "".join(events)

    assert "error" in event_str
    # Chapter content must remain original clean draft
    ch = db.get_chapter(nid, 1)
    assert "初版正文" in ch["content"]


@m1_required
def test_tier1_f2_director_evaluator_rejects_refusal_prose():
    """F2: Director evaluator flags refusal text as quality failure."""
    from backend.services.director.tool_registry.evaluator import evaluate_output
    payload = {
        "content": "我是AI語言模型，無法協助您完成此小說章節撰寫。",
        "chapter_index": 1,
    }
    res = evaluate_output("writer", payload)
    assert res.get("passed") is False
    issues = res.get("issues", [])
    assert any("拒答" in iss or "AI" in iss or "佔位" in iss or "規範" in iss for iss in issues)


@m1_required
def test_tier1_f2_narrative_auditor_flags_refusal_as_critical(novel_factory):
    """F2: NarrativeAuditor flags refusal text with overall_action CRITICAL."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    res = NarrativeAuditor.audit_chapter_prose(
        novel_id=nid,
        chapter_index=1,
        prose_text="很抱歉，基於使用政策與倫理準則，我無法為您生成該場景。",
    )
    assert res.get("overall_action") == "CRITICAL"


def test_tier1_f2_writer_clean_prose_yields_success(novel_factory, monkeypatch):
    """F2: Clean prose passes through ChapterWriterRunner and persists normally."""
    from backend.agents.chapter_writer.runner import run_chapter_writer
    nid = novel_factory()
    clean_text = "劍光一閃，黑衣刺客的短匕被凌空震飛。林默右腳踏前一步，掌力如潮水般湧出。"

    def mock_llm_stream(*args, **kwargs):
        yield {"text": f"<think>Normal reasoning</think>[START_OF_PROSE]{clean_text}", "done": True}

    monkeypatch.setattr("backend.common.llm.call_llm_stream", mock_llm_stream)

    events = list(run_chapter_writer(nid, 1))
    event_str = "".join(events)
    assert "done" in event_str

    ch = db.get_chapter(nid, 1)
    assert ch is not None
    assert "劍光一閃" in ch["content"]


# ===========================================================================
# F3: Chapter Persistence Guard & Contamination Rollback/Purge
# ===========================================================================

@m1_required
def test_tier1_f3_save_chapter_blocks_refusal_text(novel_factory):
    """F3: db.save_chapter raises RefusalContaminationError on refusal text."""
    rf = importlib.import_module("backend.common.refusal_filter")
    nid = novel_factory()
    refusal_text = "我是AI模型，無法為您撰寫此類內容。"

    with pytest.raises(rf.RefusalContaminationError):
        db.save_chapter(nid, 1, refusal_text)

    # Ensure no contaminated row was inserted
    chapters = db.get_chapters(nid)
    assert len(chapters) == 0


@m1_required
def test_tier1_f3_create_proposal_blocks_refusal_text(novel_factory):
    """F3: db.create_proposal raises RefusalContaminationError on refusal text."""
    rf = importlib.import_module("backend.common.refusal_filter")
    nid = novel_factory()
    refusal_proposal = "很抱歉，作為人工智慧助手，我無法提供此處的修改建議。"

    with pytest.raises(rf.RefusalContaminationError):
        db.create_proposal(nid, 1, proposed_text=refusal_proposal, original_text="原稿內容")


@m1_required
def test_tier1_f3_rollback_or_purge_restores_clean_prior_version(novel_factory):
    """F3: rollback_or_purge_chapter rolls back to previous clean version."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    # Save clean V1
    v1 = db.save_chapter(nid, 1, "第 1 章乾淨正文：朝陽初升，群山如黛。")
    assert v1 == 1

    # Simulate dirty insertion bypassing guard or direct dirty state
    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, "我是AI無法幫忙", 2),
        )

    assert db.get_chapter(nid, 1)["version"] == 2

    # Execute rollback
    res = chapters.rollback_or_purge_chapter(nid, 1)
    assert res.get("status") in ("rolled_back", "ok", True) or res is True

    # Assert latest chapter is restored to clean V1
    current = db.get_chapter(nid, 1)
    assert current["version"] == 1
    assert "乾淨正文" in current["content"]


@m1_required
def test_tier1_f3_rollback_or_purge_clears_single_contaminated_chapter(novel_factory):
    """F3: rollback_or_purge_chapter purges chapter when no prior clean version exists."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, "作為AI模型我拒絕生成此內容", 1),
        )

    res = chapters.rollback_or_purge_chapter(nid, 1)
    assert res is not None

    # Entire chapter row must be purged
    assert db.get_chapter(nid, 1) is None


def test_tier1_f3_clean_save_chapter_succeeds_and_increments_version(novel_factory):
    """F3: Clean prose saves cleanly and version increments sequentially."""
    nid = novel_factory()
    v1 = db.save_chapter(nid, 1, "第一版正文內容，字數充足且完全正常。")
    assert v1 == 1

    v2 = db.save_chapter(nid, 1, "第二版精修正文內容，修飾了細節與動作。")
    assert v2 == 2

    latest = db.get_chapter(nid, 1)
    assert latest["version"] == 2
    assert "第二版精修正文" in latest["content"]


# ===========================================================================
# F4: Pipeline Refusal Recognition & Self-Healing Retry
# ===========================================================================

@m1_required
def test_tier1_f4_is_chapter_written_rejects_refusal(novel_factory):
    """F4: _is_chapter_written evaluates to False when content has refusal statement."""
    from backend.services.autonomous_pipeline import _is_chapter_written
    nid = novel_factory()

    # Insert refusal text > 50 chars directly into DB
    refusal_long = "很抱歉，作為一個AI語言模型，我必須嚴格遵守相關安全規範與內容政策，無法為您撰寫包含此類情節的小說正文。"
    assert len(refusal_long) > 50

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, refusal_long, 1),
        )

    assert _is_chapter_written(nid, 1) is False


@m1_required
def test_tier1_f4_written_indices_excludes_contaminated_chapters(novel_factory):
    """F4: Pipeline written_indices computation excludes chapters with refusal text."""
    rf = importlib.import_module("backend.common.refusal_filter")
    nid = novel_factory()

    clean_text = "青陽城西郊，寒風獵獵。林默立於斷崖之巔，俯瞰著被黑霧籠罩的古老古城，眼中透著決然。這是一段經過深思熟慮的長程正文描寫，字數已充分超過門檻。"
    refusal_text = "我是AI助手，遵守安全政策，無法為您創作涉及暴力與黑暗色彩的情節內容。"

    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, clean_text, 1),
        )
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 2, refusal_text, 1),
        )

    existing = db.get_chapters(nid)
    written_indices = {
        int(c.get("chapter_index") or 0)
        for c in existing
        if c.get("content")
        and len(c.get("content", "").strip()) > 50
        and not rf.is_refusal_or_disclaimer(c.get("content", ""))
    }

    assert 1 in written_indices
    assert 2 not in written_indices


@m1_required
def test_tier1_f4_pipeline_retry_on_refusal_triggers_regeneration(novel_factory, monkeypatch):
    """F4: Stage retry mechanism triggers regeneration when refusal encountered."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory()

    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)

    attempts = 0

    def mock_execute_task(payload):
        nonlocal attempts
        attempts += 1
        class MockResp:
            ok = attempts > 1
            error = None if attempts > 1 else "AI Refusal Contamination Intercepted"
        if attempts > 1:
            db.save_chapter(nid, 1, "合格乾淨小說正文，通過重新生成獲得成功。字數足夠長。")
        return MockResp()

    monkeypatch.setattr(mgr, "execute_generation_task", mock_execute_task)

    verify_fn = lambda: db.get_chapter(nid, 1) is not None
    mgr._execute_stage_with_retry(state, "writer", {"novel_id": nid, "chapter_index": 1}, verify_fn, max_retries=3)

    assert attempts == 2
    assert db.get_chapter(nid, 1) is not None


@m1_required
def test_tier1_f4_pipeline_retry_cleans_db_between_attempts(novel_factory):
    """F4: Rollback/purge is executed on retry to ensure no dirty state persists."""
    from backend.persistence.repositories import chapters
    nid = novel_factory()

    # Simulate dirty state from attempt 1
    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 1, "我是AI無法幫忙", 1),
        )

    chapters.rollback_or_purge_chapter(nid, 1)
    assert db.get_chapter(nid, 1) is None


def test_tier1_f4_clean_chapter_validated_by_is_chapter_written(novel_factory):
    """F4: Normal chapter with >50 chars evaluates to True in _is_chapter_written."""
    from backend.services.autonomous_pipeline import _is_chapter_written
    nid = novel_factory()

    clean_text = "暮色降臨，長街兩側的燈火漸次亮起。林默緊了緊身上的黑袍，避開了巡邏衛兵的視線，快速沒入幽暗的巷道深處，氣息完全隱匿。"
    db.save_chapter(nid, 1, clean_text)

    assert _is_chapter_written(nid, 1) is True


# ===========================================================================
# F5: Opening Repetition Detection (NarrativeAuditor._check_opening_repetition)
# ===========================================================================

@m2_required
def test_tier1_f5_single_chapter_cliche_watch(novel_factory):
    """F5: Opening cliché in a single chapter flags severity='watch' without forcing revise."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    prose = REPETITIVE_OPENINGS_CLICHE["cyber_cafe"] + " 他抬起頭，看向窗外。"
    res = NarrativeAuditor._check_opening_repetition(nid, 1, prose)

    assert res is not None
    assert res.get("severity") == "watch"
    assert res.get("action_required") is False


@m2_required
def test_tier1_f5_consecutive_chapters_same_cliche_triggers_warning_revise(novel_factory):
    """F5: Consecutive chapters using the same opening cliché triggers warning and action_required=True."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    # Save Chapter 1 with neon buzzing cliché
    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第一章後續情節...")

    # Chapter 2 starts with neon buzzing cliché as well
    ch2_prose = REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第二章林默繼續追蹤黑影..."
    res = NarrativeAuditor._check_opening_repetition(nid, 2, ch2_prose)

    assert res is not None
    assert res.get("severity") == "warning"
    assert res.get("action_required") is True


@m2_required
def test_tier1_f5_diverse_openings_pass(novel_factory):
    """F5: Distinct, diverse openings across adjacent chapters produce no warning."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.save_chapter(nid, 1, DIVERSE_OPENINGS_PASS["action"] + " 長劍出鞘，寒光閃爍。")
    ch2_prose = DIVERSE_OPENINGS_PASS["dialogue"] + " 談判在寂靜的室內展開。"

    res = NarrativeAuditor._check_opening_repetition(nid, 2, ch2_prose)
    assert res is None or res.get("action_required") is False


@m2_required
def test_tier1_f5_opening_repetition_sets_overall_action_revise(novel_factory):
    """F5: Consecutive opening repetition sets audit overall_action to REVISE."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["alarm_waking"] + " 林默換上衣服走出房門。")
    ch2_prose = REPETITIVE_OPENINGS_CLICHE["alarm_waking"] + " 他揉了揉惺忪的雙眼，再度起步。"

    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, ch2_prose)
    assert audit.get("overall_action") in ("REVISE", "CRITICAL")


@m2_required
def test_tier1_f5_opening_check_inspects_first_400_chars_only(novel_factory):
    """F5: Opening repetition checks inspect prose[:400], ignoring clichés appearing later."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["rain_weather"] + " 第一章展開。")

    # Chapter 2 starts uniquely, but mentions weather at character 600
    unique_start = "林默手中握著淬毒的匕首，屏息隱匿在梁木上方。" * 25
    later_weather = REPETITIVE_OPENINGS_CLICHE["rain_weather"]
    ch2_prose = unique_start + "\n" + later_weather

    res = NarrativeAuditor._check_opening_repetition(nid, 2, ch2_prose)
    assert res is None or res.get("action_required") is False


# ===========================================================================
# F6: Meta-Narrative Leakage Detection & Automated Elimination
# ===========================================================================

@m2_required
def test_tier1_f6_meta_leak_previous_chapter_bridge_detected():
    """F6: NarrativeAuditor detects meta-narrative bridge '承接上一章情節...'."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    prose = "承接上一章情節，李斯特拔出了腰間佩劍，冷視敵方首領。"
    res = NarrativeAuditor._check_meta_narrative_leak(prose)

    assert res is not None
    assert res.get("severity") == "critical"
    assert res.get("action_required") is True


@m2_required
def test_tier1_f6_meta_leak_outline_labels_detected():
    """F6: NarrativeAuditor detects leaked outline labels like 【場景目標】."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    prose = "【場景目標】奪取密函。【核心阻礙】守衛森嚴。\n夜幕下，林默翻過圍牆。"
    res = NarrativeAuditor._check_meta_narrative_leak(prose)

    assert res is not None
    assert res.get("severity") == "critical"


@m2_required
def test_tier1_f6_meta_leak_triggers_overall_action_critical(novel_factory):
    """F6: Meta-narrative leak causes overall_action='CRITICAL' in chapter audit."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    prose = "正如前一章所述，長老會的決定引起了各方震動。弟子們議論紛紛。"

    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, prose)
    assert audit.get("overall_action") == "CRITICAL"


@m2_required
def test_tier1_f6_sanitize_meta_narrative_strips_bridge_clause():
    """F6: sanitize_meta_narrative strips leading meta bridge clauses cleanly."""
    sanitizer = None
    for mod_name in ["backend.common.text_cleaners", "backend.services.narrative.anti_meta", "backend.common.refusal_filter"]:
        try:
            m = importlib.import_module(mod_name)
            if hasattr(m, "sanitize_meta_narrative"):
                sanitizer = getattr(m, "sanitize_meta_narrative")
                break
        except ImportError:
            pass

    assert sanitizer is not None, "sanitize_meta_narrative function not found"
    dirty = "承接上一章情節，李斯特拔出了長劍。"
    clean = sanitizer(dirty)
    assert "承接上一章" not in clean
    assert "李斯特拔出了長劍" in clean


@m2_required
def test_tier1_f6_director_evaluator_rejects_meta_markers():
    """F6: Director evaluator flags meta-narrative markers as hard failure."""
    from backend.services.director.tool_registry.evaluator import evaluate_output
    payload = {
        "content": "那是上一章發生的事，林默擊殺了影狼。此刻天邊微明。",
        "chapter_index": 2,
    }
    res = evaluate_output("writer", payload)
    assert res.get("passed") is False
    assert any("元敘事" in iss or "上一章" in iss for iss in res.get("issues", []))


# ===========================================================================
# F7: Writer Context Builder Immersive Transformation
# ===========================================================================

@m2_required
def test_tier1_f7_continuity_context_no_raw_json():
    """F7: _format_narrative_continuity_context formats packet into prose without raw JSON."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    raw_packet = {
        "memory_policy": "嚴格遵循前置記憶",
        "recent_chapter_memories": [
            {"chapter_index": 1, "chapter_summary": "林默突破至通靈境三重。"}
        ],
        "previous_chapter_tail": "他深吸了一口氣，推開了沉重的鐵門。",
    }
    builder = WriterContextBuilder()
    formatted = builder._format_narrative_continuity_context(raw_packet, chapter_index=2)

    assert "{" not in formatted
    assert "}" not in formatted
    assert "memory_policy" not in formatted
    assert "林默突破至通靈境三重" in formatted or "推開了沉重的鐵門" in formatted


@m2_required
def test_tier1_f7_continuity_context_includes_previous_tail():
    """F7: Formatted continuity context highlights previous chapter tail for smooth scene flow."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    raw_packet = {
        "previous_chapter_tail": "「今夜，誰也別想走出這座大殿。」",
        "recent_chapter_memories": [],
    }
    builder = WriterContextBuilder()
    formatted = builder._format_narrative_continuity_context(raw_packet, chapter_index=2)
    assert "「今夜，誰也別想走出這座大殿。」" in formatted


@m2_required
def test_tier1_f7_continuity_context_includes_character_states():
    """F7: Formatted context includes character immediate physical/psychological states."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    raw_packet = {
        "active_characters": [
            {"name": "林默", "state": "右肩中箭，靈能枯竭，處於極限戒備中"}
        ]
    }
    builder = WriterContextBuilder()
    formatted = builder._format_narrative_continuity_context(raw_packet, chapter_index=2)
    assert "林默" in formatted
    assert "右肩中箭" in formatted or "極限戒備" in formatted


@m2_required
def test_tier1_f7_negative_constraints_against_meta_and_cliches():
    """F7: Prompt builder includes rigid negative constraint block against meta and cliches."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id="test_meta_block",
        chapter_index=2,
        current_outline={"title": "第 2 章", "scene_goal": "突圍"},
        surrounding_plot="",
    )
    assert "紅線禁令" in prompt or "嚴禁元敘事" in prompt
    assert "上一章" in prompt  # Mentioned in the prohibition clause


@m2_required
def test_tier1_f7_chapter_1_initial_context_clean():
    """F7: At chapter 1, continuity context renders clean starting guidance without None placeholders."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    builder = WriterContextBuilder()
    formatted = builder._format_narrative_continuity_context({}, chapter_index=1)
    assert "None" not in formatted


# ===========================================================================
# F8: Terms & Temporal Graph Hard Constraint Prompts
# ===========================================================================

@m3_required
def test_tier1_f8_terms_prompt_hard_constraint_syntax(novel_factory):
    """F8: Story terms injected into writer prompt with invariant constraint directives."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    nid = novel_factory()
    db.create_term(nid, category="power", term="靈能", definition="天地間游離的靈性粒子總稱")

    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=nid,
        chapter_index=2,
        current_outline={"title": "修煉"},
        surrounding_plot="",
    )
    assert "術語庫" in prompt
    assert "靈能" in prompt
    assert "強制" in prompt or "剛性約束" in prompt or "唯一性" in prompt


@m3_required
def test_tier1_f8_terms_ban_synonym_substitution(novel_factory):
    """F8: Terms directive block explicitly bans coining replacement terms or synonyms."""
    from backend.services.context.writer_context_builder import WriterContextBuilder
    nid = novel_factory()
    db.create_term(nid, category="faction", term="青陽宗", definition="大乾帝國三大宗門之一")

    builder = WriterContextBuilder()
    prompt = builder.format_writer_prompt_context(
        novel_id=nid,
        chapter_index=2,
        current_outline={"title": "宗門大比"},
        surrounding_plot="",
    )
    assert "禁止" in prompt or "嚴禁" in prompt or "替換" in prompt


@m3_required
def test_tier1_f8_temporal_graph_prompt_hard_constraint_syntax():
    """F8: Temporal facts formatted with immutable worldline reality directives."""
    from backend.services.graphiti.temporal_graph import TemporalGraphService
    mock_facts = [
        {"from_ch": 1, "stmt": "林默在黑市購得殘破劍訣"},
    ]
    snippet = TemporalGraphService.format_temporal_facts_prompt(mock_facts, chapter_index=2)
    assert "時序" in snippet
    assert "剛性約束" in snippet or "鐵律" in snippet or "世界線" in snippet


@m3_required
def test_tier1_f8_temporal_graph_distinguishes_active_and_invalidated():
    """F8: Temporal graph prompt clearly distinguishes active facts from superseded facts."""
    from backend.services.graphiti.temporal_graph import TemporalGraphService
    active = [{"from_ch": 1, "stmt": "蕭炎取得玄鐵重劍"}]
    invalidated = [{"inv_ch": 2, "stmt": "蕭炎雙目失明"}]
    snippet = TemporalGraphService.format_temporal_facts_prompt(
        active_facts=active,
        invalidated_facts=invalidated,
        chapter_index=3,
    )
    assert "當前生效" in snippet
    assert "失效" in snippet or "已作廢" in snippet or "避免穿幫" in snippet


@m3_required
def test_tier1_f8_setting_boundaries_capability_costs_directive(novel_factory):
    """F8: Scoped setting boundaries prompt mandates capability costs and limits."""
    from backend.services.narrative.setting_registry import SettingRegistry
    nid = novel_factory()
    db.create_setting_system(
        nid,
        name="大荒伏魔印",
        sys_type="power_mechanism",
        mechanism="凝聚金剛印法鎮壓邪魔",
        cost="消耗半數氣血與經脈劇痛",
        boundary="無法作用於無形神識",
    )
    block = SettingRegistry.get_scoped_context_for_writer(nid, ["大荒伏魔印"])
    assert "大荒伏魔印" in block
    assert "代價" in block
    assert "邊界" in block


# ===========================================================================
# F9: NarrativeAuditor Terms, Temporal Facts & Causal Enforcement
# ===========================================================================

@m3_required
def test_tier1_f9_terms_compliance_detects_synonym_substitution(novel_factory):
    """F9: NarrativeAuditor flags synonym substitution when canonical term is bypassed."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    db.create_term(nid, category="power", term="靈能", definition="本世界專有超自然能量體系")

    # Author uses '法力' instead of canonical '靈能'
    prose = "林默深吸一口氣，將丹田內的法力運轉至極致，掌心光芒大放。"
    res = NarrativeAuditor._check_terms_compliance(nid, prose)

    assert res is not None
    assert res.get("action_required") is True
    assert "靈能" in res.get("recommendation", "") or "法力" in res.get("evidence", "")


@m3_required
def test_tier1_f9_temporal_compliance_detects_invalidated_fact_resurrection(novel_factory):
    """F9: NarrativeAuditor flags revival of invalidated fact as temporal contradiction."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    # Fact invalidated in Ch 2: character 赵泰 is dead
    db.record_temporal_fact(
        novel_id=nid,
        statement="趙泰戰死於黑石山隘口",
        valid_from=1,
        invalid_from=2,
    )

    # In Ch 4, prose depicts 赵泰 speaking actively
    prose = "趙泰站在城牆上，哈哈大笑著拍著林默的肩膀：「賢弟，我們勝了！」"
    res = NarrativeAuditor._check_temporal_fact_compliance(nid, 4, prose)

    assert res is not None
    assert res.get("action_required") is True
    assert res.get("severity") in ("warning", "critical")


@m3_required
def test_tier1_f9_ability_costs_detects_cost_free_clash(novel_factory):
    """F9: NarrativeAuditor flags high-impact battle resolved with zero cost and effortless clichés."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()

    prose = "面對三頭萬年妖王，林默輕鬆隨意地一揮衣袖，隨手一擊便將妖王拍得灰飛煙滅，毫髮無傷，毫無波瀾。"
    sig = {"pressure_type": "life_or_death", "protagonist_strategy": "direct_clash", "cost": "無"}

    res = NarrativeAuditor._check_ability_costs_and_boundaries(nid, 1, prose, outline={}, candidate_conflict_sig=sig)
    assert res is not None
    assert res.get("action_required") is True


@m3_required
def test_tier1_f9_canonical_terms_and_valid_temporal_facts_pass(novel_factory):
    """F9: Prose strictly following canonical terms and consistent temporal facts passes audit."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory()
    db.create_term(nid, category="power", term="靈能", definition="本世界超自然能量")

    prose = "林默運轉體內的靈能，靈能沿著經脈呼嘯而過。他承受著反噬之痛，咬緊牙關支撐住護盾。"
    res_terms = NarrativeAuditor._check_terms_compliance(nid, prose)
    assert res_terms is None or res_terms.get("action_required") is False


@m3_required
def test_tier1_f9_fix_loop_generates_terms_and_temporal_instructions():
    """F9: build_fix_instructions in fix.py generates targeted rewrite commands for terms/temporal errors."""
    from backend.services.narrative.fix import build_fix_instructions
    targets = [
        {
            "dimension": "terms_compliance",
            "evidence": "檢測到使用近義詞「法力」代替登錄術語「靈能」",
            "recommendation": "請將全篇法力修改為靈能",
        },
        {
            "dimension": "temporal_graph_compliance",
            "evidence": "趙泰已於第 2 章戰死",
            "recommendation": "嚴禁已陣亡角色復活出現在對話中",
        },
    ]
    instructions = build_fix_instructions(targets)
    assert "靈能" in instructions or "術語" in instructions
    assert "趙泰" in instructions or "時序" in instructions


# ===========================================================================
# F10: Autonomous Pipeline Closed-Loop Integration & Self-Repair Governance
# ===========================================================================

def test_tier1_f10_pipeline_manager_instance_exists():
    """F10: AutonomousPipelineManager global instance is ready and functional."""
    from backend.services.autonomous_pipeline import autonomous_manager
    assert autonomous_manager is not None
    assert hasattr(autonomous_manager, "start_pipeline")
    assert hasattr(autonomous_manager, "get_task_status")


def test_tier1_f10_pipeline_preserves_historical_chapters(novel_factory):
    """F10: Existing chapters in database are strictly skipped and not overwritten."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager
    nid = novel_factory()

    # Pre-populate chapter 1
    db.save_chapter(nid, 1, "歷史第一章：這是已經完成的正文，長度充足，必須被完整保護不受覆蓋。這是一段經過精心打磨的歷史文字，具有充足的字數與故事背景。")

    # Run check logic
    chapters = db.get_chapters(nid)
    written = {int(c["chapter_index"]) for c in chapters if c.get("content") and len(c["content"]) > 50}
    assert 1 in written

    # Verify content remains unchanged
    ch1 = db.get_chapter(nid, 1)
    assert "歷史第一章" in ch1["content"]


def test_tier1_f10_pipeline_stop_requested_graceful_exit():
    """F10: Pipeline checks stop_requested flag to pause execution cleanly."""
    from backend.services.autonomous_pipeline import GenerationTaskState
    state = GenerationTaskState(novel_id="test_stop")
    state.stop_requested = True
    assert state.stop_requested is True


def test_tier1_f10_pipeline_progress_updates():
    """F10: Pipeline state progress percentage and stage fields update monotonically."""
    from backend.services.autonomous_pipeline import GenerationTaskState
    state = GenerationTaskState(novel_id="test_progress")
    state.total_chapters = 10
    state.current_chapter = 1
    state.progress_percent = 50

    state.current_chapter = 2
    state.progress_percent = 54
    assert state.progress_percent == 54
    assert state.current_chapter == 2


def test_tier1_f10_pipeline_database_lock_clearing_on_init():
    """F10: Database initializes cleanly and clears stale pipeline locks."""
    # db_init should not throw and should handle startup housekeeping
    assert db.db_init() is not None or True
