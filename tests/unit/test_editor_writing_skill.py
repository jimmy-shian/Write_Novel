"""Tests for the project-level Editor writing skill integration."""

from unittest.mock import patch

from backend.agents.editor.prompts import build_editor_agent_messages
from backend.services import narrative_memory
from backend.services.context.editor_writing_skill import (
    format_editor_writing_skill_context,
    load_editor_writing_skill,
)


def test_editor_writing_skill_is_project_owned_and_scoped():
    skill = load_editor_writing_skill()
    formatted = format_editor_writing_skill_context()

    assert "自然的敘事語言" in skill
    assert "保留原文的核心劇情" in skill
    assert "Story Canon" in skill
    assert formatted.startswith("【Editor 寫作 Skill：自然小說編修】")
    assert "時間線" in formatted


def test_editor_context_packet_includes_writing_skill():
    fake_outline = {
        "title": "第 3 章",
        "scene_goal": "讓角色作出選擇",
        "scene_beats": ["爭執", "沉默"],
        "characters_active": ["林羽"],
    }

    with patch("backend.services.narrative_memory.get_chapter_outline", return_value=fake_outline), \
         patch("backend.persistence.get_terms", return_value=[]):
        packet = narrative_memory.build_editor_context_packet(
            "novel_editor_skill", 3, "林羽沒有回答。"
        )

    assert "editor_writing_skill" in packet
    context = narrative_memory.memory_context_text(packet)
    assert "Editor 寫作 Skill：自然小說編修" in context
    assert "不要連續堆疊近義詞" in context


def test_editor_prompt_receives_skill_without_replacing_hard_contracts():
    context = format_editor_writing_skill_context()
    messages = build_editor_agent_messages(
        chapter_index=3,
        edit_instructions="改善對話節奏",
        original_prose="林羽沒有回答。",
        editor_context=context,
    )

    user_prompt = messages[1]["content"]
    assert "Editor 寫作 Skill：自然小說編修" in user_prompt
    assert "Story Canon" in user_prompt
    assert "直接輸出完整正文" in user_prompt
