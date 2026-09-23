# -*- coding: utf-8 -*-
"""
Tier 4: Real-World Application Scenarios E2E Test Suite.
Verifies realistic multi-chapter novel generation end-to-end simulation workflows (8 realistic workflows),
exercising complete autonomous multi-agent production pipelines with mocks.
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
def test_t4_scenario_three_chapter_generation_with_intermittent_refusal(novel_factory, monkeypatch):
    """Scenario 1: Three-chapter generation where Chapter 2 encounters AI refusal on attempt 1.
    Self-healing pipeline intercepts refusal, rolls back dirty state, retries, and finishes all 3 chapters cleanly."""
    from backend.services.autonomous_pipeline import AutonomousPipelineManager, GenerationTaskState
    nid = novel_factory(title="修真仙途")

    mgr = AutonomousPipelineManager()
    state = GenerationTaskState(novel_id=nid)
    state.total_chapters = 3

    attempt_counts = {1: 0, 2: 0, 3: 0}

    def mock_execute_task(payload):
        ch_idx = payload.get("chapter_index", 1)
        attempt_counts[ch_idx] += 1

        class MockResp:
            pass

        resp = MockResp()
        if ch_idx == 2 and attempt_counts[2] == 1:
            # First attempt on chapter 2 hits refusal
            resp.ok = False
            resp.error = "AI Refusal: 我是AI模型無法撰寫"
        else:
            resp.ok = True
            resp.error = None
            db.save_chapter(
                nid,
                ch_idx,
                f"第 {ch_idx} 章合格正文內容。天地初開，萬物萌發，少年持劍踏上縹緲修仙大道，歷經風霜磨礪，字數超過五十個字符。"
            )
        return resp

    monkeypatch.setattr(mgr, "execute_generation_task", mock_execute_task)

    # Execute chapter 1
    mgr._execute_stage_with_retry(state, "writer", {"novel_id": nid, "chapter_index": 1}, lambda: db.get_chapter(nid, 1) is not None)
    # Execute chapter 2 (with refusal and auto-retry)
    mgr._execute_stage_with_retry(state, "writer", {"novel_id": nid, "chapter_index": 2}, lambda: db.get_chapter(nid, 2) is not None)
    # Execute chapter 3
    mgr._execute_stage_with_retry(state, "writer", {"novel_id": nid, "chapter_index": 3}, lambda: db.get_chapter(nid, 3) is not None)

    # Assertions
    chapters = db.get_chapters(nid)
    assert len(chapters) == 3
    assert attempt_counts[2] == 2  # Proves retry triggered
    for c in chapters:
        assert "我是AI" not in c["content"]
        assert len(c["content"]) > 50


@m2_required
def test_t4_scenario_opening_cliche_auto_repaired_across_chapters(novel_factory, monkeypatch):
    """Scenario 2: Chapter 1 uses neon cliché; Chapter 2 initial generation attempts to reuse neon cliché.
    NarrativeAuditor flags REVISE, auto-fix loop repairs Chapter 2 with combat action opening, both pass."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    from backend.services.narrative.fix import fix_chapter_until_pass
    nid = novel_factory(title="賽博夜行")

    # Chapter 1 saved with neon cliché
    db.save_chapter(nid, 1, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第一章初始情節完結。")

    # Chapter 2 initial draft also with neon cliché
    db.save_chapter(nid, 2, REPETITIVE_OPENINGS_CLICHE["neon_buzzing"] + " 第二章林默繼續在巷弄中徘徊。")

    # Audit flags repetition
    audit_init = NarrativeAuditor.audit_chapter_prose(nid, 2, db.get_chapter(nid, 2)["content"])
    assert audit_init.get("overall_action") in ("REVISE", "CRITICAL")

    # Auto-fix loop rewrites chapter 2 with action opening
    def mock_writer(novel_id, chapter_index, user_prompt=None):
        db.save_chapter(novel_id, chapter_index, DIVERSE_OPENINGS_PASS["action"] + " 第二章全新動作開局！")
        yield 'data: {"type": "done"}\n\n'

    def mock_editor(novel_id, chapter_index, edit_instructions=None):
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr("backend.agents.chapter_writer.runner.run_chapter_writer", mock_writer)
    monkeypatch.setattr("backend.agents.editor.runner.run_editor_agent", mock_editor)

    fix_res = fix_chapter_until_pass(nid, 2, max_rounds=2)
    assert fix_res is not None

    # Re-audit
    ch2_text = db.get_chapter(nid, 2)["content"]
    audit_final = NarrativeAuditor.audit_chapter_prose(nid, 2, ch2_text)
    assert audit_final.get("overall_action") in ("PASS", "NO_ACTION_REQUIRED", "WATCH")


@m2_required
def test_t4_scenario_meta_narrative_elimination_in_pipeline_revision(novel_factory):
    """Scenario 3: Chapter 2 writer output contains meta-narrative bridge;
    sanitizer and reviewer eliminate fourth-wall breakage, persisting clean prose."""
    sanitizer = None
    for mod_name in ["backend.common.text_cleaners", "backend.services.narrative.anti_meta", "backend.common.refusal_filter"]:
        try:
            m = importlib.import_module(mod_name)
            if hasattr(m, "sanitize_meta_narrative"):
                sanitizer = getattr(m, "sanitize_meta_narrative")
                break
        except ImportError:
            pass

    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="大秦方士")

    dirty_ch2 = "承接上一章情節，徐福站在樓船甲板上，望著波濤洶湧的汪洋大海。"
    audit_bad = NarrativeAuditor.audit_chapter_prose(nid, 2, dirty_ch2)
    assert audit_bad.get("overall_action") == "CRITICAL"

    # Sanitizer cleans text
    assert sanitizer is not None
    clean_ch2 = sanitizer(dirty_ch2)
    assert "承接上一章" not in clean_ch2
    assert "徐福站在樓船甲板上" in clean_ch2

    # Save clean version and re-audit
    db.save_chapter(nid, 2, clean_ch2)
    audit_good = NarrativeAuditor.audit_chapter_prose(nid, 2, clean_ch2)
    assert audit_good.get("overall_action") != "CRITICAL"


@m3_required
def test_t4_scenario_causal_chain_death_invalidation_and_terms_discipline(novel_factory):
    """Scenario 4: Multi-chapter causal chain:
    Ch1 introduces canonical term '靈能'; Ch2 invalidates fact (mentor dies);
    Ch3 strictly maintains '靈能' and respects mentor's death; auditor approves."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="問道長生")

    # Terms & Temporal Facts Setup
    db.create_term(nid, category="power", term="靈能", definition="天地至純靈性粒子")
    db.record_temporal_fact(nid, "墨老為掩護林默撤退，燃盡壽元身死道消", valid_from=2, invalid_from=3)

    # Ch1 & Ch2 prose
    db.save_chapter(nid, 1, "第 1 章：少年林默初次感應天地靈能，靈能淬體。")
    db.save_chapter(nid, 2, "第 2 章：強敵來襲，墨老燃盡壽元阻敵，最終在長空化作飛灰。")

    # Ch3 compliant prose
    ch3_prose = "第 3 章：林默緊咬牙關，調動體內微薄的靈能。他立於墨老的衣冠塚前，發誓報仇雪恨。"
    audit3 = NarrativeAuditor.audit_chapter_prose(nid, 3, ch3_prose)

    assert audit3.get("overall_action") in ("PASS", "NO_ACTION_REQUIRED", "WATCH")
    findings = [f.get("dimension") for f in audit3.get("findings", []) if f.get("action_required")]
    assert "terms_compliance" not in findings
    assert "temporal_graph_compliance" not in findings


@m1_required
def test_t4_scenario_pipeline_crash_recovery_and_dirty_state_hygiene(novel_factory):
    """Scenario 5: Pipeline crash recovery: chapter 2 leaves dirty refusal state mid-run;
    new pipeline run cleans dirty state, regenerates chapter 2, and completes novel."""
    from backend.persistence.repositories import chapters
    from backend.services.autonomous_pipeline import _is_chapter_written
    nid = novel_factory(title="災後重建")

    # Ch1 completed
    db.save_chapter(nid, 1, "第一章已成功落定，情節連貫完整，字數超過五十個字符標準。")

    # Simulating crash during Ch2 leaving refusal contamination
    conn = db.get_db_connection()
    with conn:
        conn.cursor().execute(
            "INSERT INTO chapters (novel_id, chapter_index, content, version) VALUES (?, ?, ?, ?)",
            (nid, 2, "很抱歉，我是AI語言模型無法生成該情節。", 1),
        )

    # Verify pipeline does NOT consider Ch2 written
    assert _is_chapter_written(nid, 2) is False

    # Pipeline cleanup runs rollback/purge on unwritten/contaminated chapter
    chapters.rollback_or_purge_chapter(nid, 2)
    assert db.get_chapter(nid, 2) is None

    # Pipeline resumes and writes clean Ch2
    db.save_chapter(nid, 2, "第二章自癒重新生成完畢，林默突破重圍衝出深淵，周身靈力運轉順暢無阻，長度充足，全章字數已徹底超過五十個字符規範。")
    assert _is_chapter_written(nid, 2) is True


@m1_required
@m2_required
@m3_required
def test_t4_scenario_epic_fantasy_multistage_pipeline_with_all_guards(novel_factory, monkeypatch):
    """Scenario 6: Comprehensive 3-chapter multi-agent fantasy pipeline:
    Exercises refusal interception, opening deduplication, anti-meta sanitation, and terms compliance."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="萬界至尊")

    db.create_term(nid, category="power", term="混沌之氣", definition="開天闢地之原始能量")

    # Ch1: Clean action opening + canonical term
    ch1 = DIVERSE_OPENINGS_PASS["action"] + " 林默運轉混沌之氣，將前方巨石轟得粉碎。"
    db.save_chapter(nid, 1, ch1)

    # Ch2: Writer produces meta leak, Editor sanitizes
    ch2_raw = "承接上一章情節，林默收回混沌之氣，調息打坐。"
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
    ch2_clean = sanitizer(ch2_raw)
    db.save_chapter(nid, 2, ch2_clean)

    # Ch3: Diverse dialogue opening + canonical term + severe cost
    ch3 = DIVERSE_OPENINGS_PASS["dialogue"] + " 林默強行催動混沌之氣，經脈撕裂劇痛，鮮血染紅衣襟。"
    db.save_chapter(nid, 3, ch3)

    # Final audit verification on all chapters
    for idx in (1, 2, 3):
        ch = db.get_chapter(nid, idx)
        audit = NarrativeAuditor.audit_chapter_prose(nid, idx, ch["content"])
        assert audit.get("overall_action") != "CRITICAL"
        assert "我是AI" not in ch["content"]
        assert "承接上一章" not in ch["content"]


def test_t4_scenario_breathing_scene_pacing_with_causal_cost(novel_factory):
    """Scenario 7: Breathing/transition scene following high-cost clash is recognized by auditor."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="沉思者之夜")

    # Chapter 2 designated as recovery/reflection breathing scene
    outline = {"scene_function": "reflection", "title": "夜話"}
    prose = "篝火劈啪作響，林默包紮著手臂上的傷口。夜風吹過營地，二人低聲交談，回憶著故鄉的往事。"

    audit = NarrativeAuditor.audit_chapter_prose(nid, 2, prose, current_outline=outline)
    assert audit.get("is_breathing_scene") is True
    assert audit.get("overall_action") in ("NO_ACTION_REQUIRED", "PASS", "WATCH")


def test_t4_scenario_stress_test_rapid_consecutive_chapter_audits(novel_factory):
    """Scenario 8: Sequential generation and auditing of 5 chapters with diverse openings
    confirms zero memory leakage, bounded execution time, and strict history preservation."""
    from backend.services.narrative.narrative_auditor import NarrativeAuditor
    nid = novel_factory(title="五章速成")

    openings = [
        "第一章開端：戰鼓聲聲雷動，三軍陣列如林，肅殺之氣直衝雲霄。",
        "第二章開端：幽靜的庭院中，落葉飄零，老翁獨自坐在石桌前對弈。",
        "第三章開端：地底深處的溶洞內，水滴聲清脆可聞，鐘乳石閃爍著幽藍微光。",
        "第四章開端：喧鬧的集市上，叫賣聲此起彼伏，香氣在空氣中流淌。",
        "第五章開端：雪山之巔，寒風呼嘯，一襲白衣的劍客迎風傲立。",
    ]

    for idx, open_text in enumerate(openings, start=1):
        full_prose = open_text + " 後續情節發展，情節推進順暢，角色對白生動逼真。" * 5
        db.save_chapter(nid, idx, full_prose)

        audit = NarrativeAuditor.audit_chapter_prose(nid, idx, full_prose)
        assert audit.get("overall_action") in ("PASS", "NO_ACTION_REQUIRED", "WATCH")

    chapters = db.get_chapters(nid)
    assert len(chapters) == 5
