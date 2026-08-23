# -*- coding: utf-8 -*-
"""
Unit tests for WriterContextBuilder
"""

import pytest
from backend.services.context.writer_context_builder import (
    WriterContextBuilder,
    build_writer_scene_context,
)


def test_build_scene_contract_defaults():
    builder = WriterContextBuilder()
    outline = {
        "chapter_index": 1,
        "chapter_summary": "林澤進入失控的研究所，尋求失蹤導師的最後日誌。",
        "characters_active": ["林澤", "警衛A"],
        "scene_goal": "取得備份日誌",
        "scene_conflict": "巡邏防衛系統即將重置",
        "scene_turn": "日誌已被提前刪除",
        "scene_outcome": "觸發警報，但發現隱藏的暗號",
    }
    characters = [
        {"name": "林澤", "role": "主角", "faction": "調查會"},
        {"name": "警衛A", "role": "阻礙者", "faction": "研究所保全"},
    ]

    contract = builder.build_scene_contract(outline, characters, chapter_index=1)
    assert contract["pov_character"] == "林澤"
    assert contract["narrative_mode"] == "third_person_limited"
    assert contract["narrative_distance"] == "close"
    assert contract["thought_mode"] == "free_indirect"
    assert contract["scene_goal"] == "取得備份日誌"
    assert contract["conflict"] == "巡邏防衛系統即將重置"
    assert contract["turn"] == "日誌已被提前刪除"
    assert contract["outcome"] == "觸發警報，但發現隱藏的暗號"


def test_build_character_states_speech_profile_and_knowledge():
    builder = WriterContextBuilder()
    outline = {
        "characters_active": ["林澤", "陸沉"],
    }
    bible = {
        "characters": [
            {
                "name": "林澤",
                "role": "主角",
                "want": "查清真相",
                "speech_profile": {
                    "default_register": "冷靜正式",
                    "sentence_length": "偏短簡練",
                    "under_pressure": "語調冷酷且極其精確",
                },
                "initial_knowledge_scope": ["導師曾留下加密硬碟", "自身身份受通緝"],
            },
            {
                "name": "陸沉",
                "role": "反派博弈者",
                "want": "回收所有禁忌晶片",
                "speech_style": "迂迴試探，常以反問回應",
                "initial_knowledge_scope": ["硬碟密碼由三部分組成"],
            },
            {
                "name": "無關配角",
                "role": "路人",
                "want": "活命",
            }
        ]
    }

    states = builder.build_character_states(outline, bible, pov_character="林澤")
    # 只有活躍角色林澤與陸沉
    assert len(states) == 2
    names = [s["name"] for s in states]
    assert "林澤" in names
    assert "陸沉" in names
    assert "無關配角" not in names

    lin_state = next(s for s in states if s["name"] == "林澤")
    assert lin_state["is_pov"] is True
    assert "導師曾留下加密硬碟" in lin_state["knowledge_scope"]
    assert "冷靜正式" in lin_state["speech_profile_summary"]


def test_build_scene_beats_expansion():
    builder = WriterContextBuilder()
    outline_beats = {
        "scene_beats": [
            {"beat_index": 1, "beat_type": "setup", "description": "潛入地下冷卻層"},
            {"beat_index": 2, "beat_type": "escalation", "description": "發現冷卻液洩漏"},
            {"beat_index": 3, "beat_type": "turn", "description": "警報聲突然轉為倒數"},
            {"beat_index": 4, "beat_type": "outcome", "description": "冒險帶出核心單元"},
        ]
    }
    beats = builder.build_scene_beats(outline_beats)
    assert len(beats) == 4
    assert "[setup] 潛入地下冷卻層" in beats[0]
    assert "[turn] 警報聲突然轉為倒數" in beats[2]


def test_format_writer_prompt_context_no_json_dump():
    builder = WriterContextBuilder()
    outline = {
        "chapter_index": 2,
        "chapter_summary": "調查深入，暗流湧動。",
        "characters_active": ["林澤"],
        "scene_beats": [
            {"beat_index": 1, "beat_type": "setup", "description": "到達舊城碼頭"}
        ]
    }
    bible = {
        "characters": [
            {"name": "林澤", "role": "主角", "want": "尋找線人", "initial_knowledge_scope": ["線人代號為海燕"]}
        ]
    }

    context_str = builder.format_writer_prompt_context(
        novel_id="test_novel_01",
        worldview_text="蒸汽與符文共存的世界。",
        characters_bible=bible,
        current_outline=outline,
        surrounding_plot="",
        vol_outline_context="",
        clue_payoff_details="注意埋設海燕的暗號",
        custom_style="洗鍊寫實",
        chapter_index=2,
        user_prompt="加強碼頭雨夜的陰冷氣氛",
        narrative_memory_context="前情提要：林澤剛逃離審訊。",
    )

    # 驗證格式乾淨，不包含原始 JSON 字典大括號
    assert "### 🎬【場景契約 (Scene Contract) - 第 2 章】" in context_str
    assert "**POV 視角人物**：林澤" in context_str
    assert "### ⚡【本章結構化推進拍點 (Scene Beats)】" in context_str
    assert "### 👥【出場角色即時狀態與語言傾向】" in context_str
    assert "線人代號為海燕" in context_str
    assert "加強碼頭雨夜的陰冷氣氛" in context_str
