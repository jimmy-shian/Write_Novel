# -*- coding: utf-8 -*-
"""
上下文架構邊界與防護單元測試：
- compact_json_data 的 NEVER_COMPACT_KEYS 保護
- format_novel_core_context 依階段（writer/editor）遮蔽全域 pipeline_prompt
- Editor context packet 衛生（無截斷片段、無 context request 迴圈）
- Chapter Writer 缺 canonical outline 時 fail-closed
"""
from unittest.mock import patch

import pytest

from backend.prompts.common.context import (
    compact_json_data,
    format_novel_core_context,
)
from backend.agents.editor.prompts import (
    build_editor_agent_messages,
    build_targeted_rewriter_messages,
)
from backend.services import narrative_memory
from backend.agents.chapter_writer.runner import run_chapter_writer


def test_never_compact_keys_protection():
    """關鍵規劃鍵不得被壓縮為摘要佔位符。"""
    raw_data = {
        "allocated_tasks": {
            "foreshadowing_plants": [{"id": f"plant_{i}", "content": f"detail_{i}"} for i in range(20)],
            "foreshadowing_payoffs": [{"id": f"payoff_{i}", "target": f"target_{i}"} for i in range(20)],
        },
        "scene_beats": [f"Beat {i}: major event description" for i in range(15)],
        "chapter_plan": {"events": [f"Event {i}" for i in range(10)]},
        "progressive_character_plan": [
            {"name": f"Char_{i}", "intro_phase": f"Phase {i}"} for i in range(12)
        ],
        "non_critical_list": [f"Item {i}" for i in range(20)],
    }

    compacted = compact_json_data(raw_data, max_list_items=5)

    # 受保護鍵應完整保留
    assert len(compacted["allocated_tasks"]["foreshadowing_plants"]) == 20
    assert len(compacted["allocated_tasks"]["foreshadowing_payoffs"]) == 20
    assert len(compacted["scene_beats"]) == 15
    assert len(compacted["chapter_plan"]["events"]) == 10
    assert len(compacted["progressive_character_plan"]) == 12

    # 非保護清單應被收合
    assert len(compacted["non_critical_list"]) <= 6
    assert any(
        "...摘要..." in item if isinstance(item, dict) else "...摘要..." in str(item)
        for item in compacted["non_critical_list"]
    )


def test_format_novel_core_context_stage_scoping():
    """writer/editor 階段必須遮蔽 pipeline_prompt，防止後續劇透外洩。"""
    fake_novel = {
        "title": "測試修仙傳",
        "genre": "仙俠",
        "style": "古典仙俠",
        "target_audience": "大眾",
        "pipeline_prompt": "主角最終會弒神並推翻整個天道，大結局是歸隱田園。",
        "current_state": "進行中",
    }

    with patch("backend.persistence.get_novel", return_value=fake_novel):
        # 預設 / 規劃階段：包含 pipeline_prompt
        global_ctx = format_novel_core_context("novel_123")
        assert "主角最終會弒神" in global_ctx

        # writer 階段：剝除 pipeline_prompt
        writer_ctx = format_novel_core_context("novel_123", for_stage="writer")
        assert "主角最終會弒神" not in writer_ctx
        assert "測試修仙傳" in writer_ctx

        # editor 階段：剝除 pipeline_prompt
        editor_ctx = format_novel_core_context("novel_123", for_stage="editor")
        assert "主角最終會弒神" not in editor_ctx
        assert "測試修仙傳" in editor_ctx


def test_build_editor_context_packet_hygiene():
    """build_editor_context_packet 應產出乾淨、未截斷的封包。"""
    fake_outline = {
        "title": "第 23 章 驚變",
        "scene_goal": "揭露黑市幕後指使者",
        "scene_beats": ["進入黑市", "遭遇伏擊", "逼問活口"],
        "characters_active": ["林羽", "黑市管事"],
    }
    fake_prev = {"content": "前一章結尾的完整正文段落。" * 20}
    fake_terms = [
        {"term": "黑市", "category": "地點", "definition": "隱秘交易場所"},
        {"term": "靈石", "category": "道具", "definition": "修仙貨幣"},
        {"term": "九幽神雷", "category": "功法", "definition": "高階功法"},
    ]

    with patch("backend.services.narrative_memory.get_chapter_outline", return_value=fake_outline), \
         patch("backend.persistence.get_latest_chapter", return_value=fake_prev), \
         patch("backend.persistence.get_terms", return_value=fake_terms):

        packet = narrative_memory.build_editor_context_packet("novel_123", 23, "林羽踏入黑市。")

        # 不得包含截斷片段或原始記憶傾印
        assert "prose_excerpt" not in packet
        assert "edit_target_excerpt" not in packet
        assert "recent_chapter_memories" not in packet
        assert "current_chapter_memory" not in packet

        # 應包含場景目標、前章結尾、範圍內術語與政策
        assert packet["scene_goals"]["chapter_title"] == "第 23 章 驚變"
        assert len(packet["previous_chapter_tail"]) > 0
        assert "editor_policy" in packet
        terms = packet["story_terms"]
        assert any(t["term"] == "黑市" for t in terms)


def test_editor_prompts_have_no_context_request_rule():
    """Editor 提示詞不得包含 CONTEXT_REQUEST_RULE 或鼓勵 _needs_director_context。"""
    messages = build_editor_agent_messages(
        chapter_index=23,
        edit_instructions="優化修辭與文筆",
        original_prose="這是需要潤色的正文片段。",
        editor_context="scene goals",
    )

    full_system = messages[0]["content"]
    assert "_needs_director_context" not in full_system
    assert "context_request" not in full_system
    assert "Context Request Rule" not in full_system

    targeted_messages = build_targeted_rewriter_messages(
        chapter_index=23,
        original_prose="原始正文",
        diagnostic_report={"issues": []},
        edit_instructions="修改說明",
        editor_context="上下文",
    )
    assert "_needs_director_context" not in targeted_messages[0]["content"]


def test_chapter_writer_fails_closed_when_outline_missing():
    """缺 canonical chapter_plan 時 run_chapter_writer 必須嚴格 fail-closed。"""
    with patch("backend.persistence.get_latest_worldbuilding", return_value=None), \
         patch("backend.persistence.get_latest_characters", return_value=None), \
         patch("backend.persistence.get_volumes", return_value=[]), \
         patch("backend.persistence.get_stitched_plot", return_value={"chapters": []}):

        with pytest.raises(ValueError, match="缺少 canonical chapter_plan"):
            gen = run_chapter_writer("novel_123", 23)
            next(gen, None)  # 觸發產生器執行