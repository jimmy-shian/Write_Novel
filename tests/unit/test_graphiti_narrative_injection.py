# -*- coding: utf-8 -*-
"""
Graphiti 時序圖譜事實與敘事引擎注入單元測試：
- Editor context packet 注入時序事實 / 衝突防重複 / 設定邊界
- 注入服務故障時優雅降級
- 總監 writer/editor 審查脈絡注入
- Editor 提示詞整合注入指引
"""
import json
from unittest.mock import patch

from backend.services import narrative_memory
from backend.services.director.context import (
    build_writer_review_context,
    build_editor_review_context,
)
from backend.agents.editor.prompts import (
    build_editor_agent_messages,
    build_reviewer_agent_messages,
    build_targeted_rewriter_messages,
)


def test_build_editor_context_packet_injects_graph_and_narrative():
    fake_outline = {
        "chapter_index": 5,
        "title": "第 5 章 決裂",
        "scene_goal": "林羽與宿敵對峙",
        "characters_active": ["林羽", "周煞"],
        "scene_beats": ["對質", "動手"],
    }
    fake_prev = {"content": "前一章的結尾內容。"}
    fake_terms = [{"term": "煞氣", "category": "能量", "definition": "侵蝕靈脈之氣"}]

    with patch("backend.services.narrative_memory.get_chapter_outline", return_value=fake_outline), \
         patch("backend.persistence.get_latest_chapter", return_value=fake_prev), \
         patch("backend.persistence.get_terms", return_value=fake_terms), \
         patch("backend.services.graphiti.TemporalGraphService.build_narrative_context", return_value="[時序事實] 林羽持有破魂劍；周煞重傷遁逃。") as mock_graph, \
         patch("backend.services.narrative.ConflictLedger.build_anti_repetition_prompt_snippet", return_value="[防撞車摘要] 近期已使用背叛解局。") as mock_conflict, \
         patch("backend.services.narrative.SettingRegistry.get_scoped_context_for_writer", return_value="[設定邊界] 煞氣不得被瞬息淨化。") as mock_setting:

        packet = narrative_memory.build_editor_context_packet("novel_test_1", 5, "林羽手握長劍冷冷看著周煞。")

        mock_graph.assert_called_once_with(
            novel_id="novel_test_1",
            at_chapter=5,
            active_characters=["林羽", "周煞"],
            max_facts=12,
        )
        mock_conflict.assert_called_once_with("novel_test_1", 5)

        assert "temporal_graph_facts" in packet
        assert packet["temporal_graph_facts"] == "[時序事實] 林羽持有破魂劍；周煞重傷遁逃。"
        assert "conflict_novelty_guard" in packet
        assert packet["conflict_novelty_guard"] == "[防撞車摘要] 近期已使用背叛解局。"
        assert "setting_boundaries" in packet
        assert packet["setting_boundaries"] == "[設定邊界] 煞氣不得被瞬息淨化。"


def test_build_editor_context_packet_handles_failures_gracefully():
    fake_outline = {"chapter_index": 1, "title": "第 1 章", "characters_active": []}

    with patch("backend.services.narrative_memory.get_chapter_outline", return_value=fake_outline), \
         patch("backend.persistence.get_latest_chapter", return_value=None), \
         patch("backend.persistence.get_terms", return_value=[]), \
         patch("backend.services.graphiti.TemporalGraphService.build_narrative_context", side_effect=RuntimeError("Graph DB offline")), \
         patch("backend.services.narrative.ConflictLedger.build_anti_repetition_prompt_snippet", side_effect=Exception("Ledger error")), \
         patch("backend.services.narrative.SettingRegistry.get_scoped_context_for_writer", side_effect=Exception("Registry error")):

        packet = narrative_memory.build_editor_context_packet("novel_test_2", 1, "開端。")

        assert packet.get("temporal_graph_facts") == ""
        assert packet.get("conflict_novelty_guard") == ""
        assert packet.get("setting_boundaries") == ""


def test_director_writer_review_context_injection():
    fake_outline = {
        "chapter_index": 7,
        "title": "第 7 章 斬妖",
        "characters_active": ["林羽"],
    }
    fake_findings = [
        {"chapter_index": 7, "dimension": "causality", "severity": "major", "recommendation": "應扣減體力代價"}
    ]

    with patch("backend.persistence.get_stitched_plot", return_value={"chapters": [fake_outline]}), \
         patch("backend.persistence.get_latest_chapter", return_value={"content": "林羽斬殺妖獸，耗盡靈力。"}), \
         patch("backend.services.graphiti.TemporalGraphService.build_narrative_context", return_value="[時序] 林羽此時修為在凝氣三層。"), \
         patch("backend.services.narrative.ConflictLedger.build_anti_repetition_prompt_snippet", return_value="[衝突防重複] 最近兩章均為強行突破。"), \
         patch("backend.services.narrative.SettingRegistry.get_scoped_context_for_writer", return_value="[設定邊界] 凝氣層級無法御劍飛行。"), \
         patch("backend.persistence.get_narrative_audits", return_value=fake_findings):

        raw_context, _ = build_writer_review_context("novel_test_3", 7, "林羽")
        parsed = json.loads(raw_context)

        assert parsed.get("temporal_graph_facts") == "[時序] 林羽此時修為在凝氣三層。"
        assert parsed.get("conflict_novelty_context") == "[衝突防重複] 最近兩章均為強行突破。"
        assert parsed.get("setting_boundaries_context") == "[設定邊界] 凝氣層級無法御劍飛行。"
        assert len(parsed.get("unresolved_narrative_audits", [])) == 1
        assert parsed["unresolved_narrative_audits"][0]["dimension"] == "causality"


def test_director_editor_review_context_injection():
    fake_outline = {
        "chapter_index": 8,
        "title": "第 8 章 暗湧",
        "characters_active": ["林羽", "沈清"],
    }
    fake_versions = [
        {"version_index": 2, "content": "潤色後正文。"},
        {"version_index": 1, "content": "潤色前初稿。"},
    ]

    with patch("backend.persistence.get_stitched_plot", return_value={"chapters": [fake_outline]}), \
         patch("backend.services.director.context._chapter_versions", return_value=fake_versions), \
         patch("backend.services.graphiti.TemporalGraphService.build_narrative_context", return_value="[時序] 沈清持有密函。"), \
         patch("backend.services.narrative.ConflictLedger.build_anti_repetition_prompt_snippet", return_value="[衝突防重複] 避免密室交涉連續發生。"), \
         patch("backend.services.narrative.SettingRegistry.get_scoped_context_for_writer", return_value="[設定邊界] 密函具備傳音印記。"), \
         patch("backend.persistence.get_narrative_audits", return_value=[]):

        raw_context, _ = build_editor_review_context("novel_test_4", 8, "林羽, 沈清")
        parsed = json.loads(raw_context)

        assert parsed.get("temporal_graph_facts") == "[時序] 沈清持有密函。"
        assert parsed.get("conflict_novelty_context") == "[衝突防重複] 避免密室交涉連續發生。"
        assert parsed.get("setting_boundaries_context") == "[設定邊界] 密函具備傳音印記。"
        assert parsed.get("unresolved_narrative_audits") == []


def test_editor_prompts_incorporate_injected_guidance():
    # 1. Editor agent prompt
    editor_msgs = build_editor_agent_messages(
        chapter_index=1,
        edit_instructions="優化描寫",
        original_prose="正文草稿",
        editor_context="[時序事實] 周煞已死\n[設定邊界] 不可死而復生",
    )
    combined_editor = "\n".join(m["content"] for m in editor_msgs)
    assert "動態世界線事實" in combined_editor or "時序動態事實" in combined_editor
    assert "周煞已死" in combined_editor
    assert "不可死而復生" in combined_editor

    # 2. Targeted rewriter prompt
    rewriter_msgs = build_targeted_rewriter_messages(
        chapter_index=1,
        original_prose="原段落",
        diagnostic_report={"issues": []},
        edit_instructions="加強壓迫感",
        editor_context="[時序事實] 靈石耗盡",
    )
    rewriter_text = "\n".join(m["content"] for m in rewriter_msgs)
    assert "時序動態事實" in rewriter_text
    assert "靈石耗盡" in rewriter_text

    # 3. Reviewer prompt
    reviewer_msgs = build_reviewer_agent_messages(
        chapter_index=1,
        original_prose="待檢視正文",
        editor_context="[設定邊界] 法陣有冷卻時間",
    )
    reviewer_text = "\n".join(m["content"] for m in reviewer_msgs)
    assert "時序事實一致性" in reviewer_text or "設定邊界" in reviewer_text
    assert "法陣有冷卻時間" in reviewer_text
