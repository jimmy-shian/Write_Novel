"""Tests for the project-level Writer writing skill integration."""

from backend.agents.chapter_writer.prompts import build_chapter_writer_messages
from backend.services.context.writer_writing_skill import (
    format_writer_writing_skill_context,
    load_writer_writing_skill,
)


def test_writer_writing_skill_is_project_owned_and_scoped():
    skill = load_writer_writing_skill()
    formatted = format_writer_writing_skill_context()

    assert "僅輸出小說正文" in skill
    assert "禁止將章節編號與事件、時間或場景描述拼接成敘事句子" in skill
    assert formatted.startswith("【Writer 寫作 Skill：小說正文輸出規範】")
    assert "Story Canon" in formatted


def test_writer_prompt_receives_writing_skill_and_forbids_story_meta():
    messages = build_chapter_writer_messages(
        worldview_text="地下黑市存在於城市下層。",
        characters_bible=[],
        current_outline={"chapter_title": "突破後的傍晚", "scene_beats": []},
        surrounding_plot="角色剛完成突破。",
        vol_outline_context="",
        clue_payoff_details="",
        custom_style="",
        chapter_index=10,
    )

    system_prompt = messages[0]["content"]
    assert "Writer 寫作 Skill：小說正文輸出規範" in system_prompt
    assert "不得輸出 `[正文開始]`" in system_prompt
    assert "第十章突破後的傍晚" in system_prompt
    assert "直接輸出小說正文" in system_prompt
