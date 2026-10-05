# -*- coding: utf-8 -*-
from unittest.mock import patch
from backend.services.narrative.narrative_auditor import NarrativeAuditor


def test_invalid_from_chapter_none_no_none_string():
    """invalid_from_chapter=None 時，不得格式化成『第 None 章』"""
    fake_facts = [
        {
            "fact_id": "f1",
            "fact_statement": "長老楚風在十萬大山戰死身亡。",
            "valid_from_chapter": 87,
            "invalid_from_chapter": None,
        }
    ]
    with patch("backend.persistence.get_all_facts", return_value=fake_facts):
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=88,
            prose_text="楚風笑著站了起來，喝道：『爾等受死！』",
        )
        assert finding is not None
        assert "None" not in finding["evidence"]
        assert "None" not in finding["recommendation"]
        assert "第 87 章" in finding["evidence"]
        assert "楚風" in finding["evidence"]


def test_death_in_ch87_mention_in_ch86_not_resurrection():
    """死亡於第 87 章，第 86 章提及或角色行動，不應判定復活"""
    fake_facts = [
        {
            "fact_id": "f1",
            "fact_statement": "楚風在黑風谷被殺身亡。",
            "valid_from_chapter": 87,
            "invalid_from_chapter": None,
        }
    ]
    with patch("backend.persistence.get_all_facts", return_value=fake_facts):
        # 第 86 章中楚風還活著，說話行動是正常的
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=86,
            prose_text="楚風笑著拔出佩劍，向前方走去。",
        )
        assert finding is None


def test_death_in_ch87_action_in_ch88_violates():
    """死亡於第 87 章，第 88 章角色再次說話/行動，應判定違規"""
    fake_facts = [
        {
            "fact_id": "f1",
            "fact_statement": "楚風戰死身亡。",
            "valid_from_chapter": 87,
            "invalid_from_chapter": None,
        }
    ]
    with patch("backend.persistence.get_all_facts", return_value=fake_facts):
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=88,
            prose_text="楚風冷笑一聲，大喊道：『休想得逞！』",
        )
        assert finding is not None
        assert finding["severity"] == "critical"
        assert "已於第 87 章" in finding["evidence"]
        assert "楚風" in finding["evidence"]


def test_memory_of_deceased_character_not_considered_action():
    """回憶、傳聞、悼念提及死亡角色，不應視為當前角色行動"""
    fake_facts = [
        {
            "fact_id": "f1",
            "fact_statement": "楚風戰死身亡。",
            "valid_from_chapter": 87,
            "invalid_from_chapter": None,
        }
    ]
    with patch("backend.persistence.get_all_facts", return_value=fake_facts):
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=88,
            prose_text="他想起楚風生前曾微笑著對他說過這番話，心中頓時無限感慨。如今墓前草已長青。",
        )
        assert finding is None


def test_unrelated_name_not_falsely_flagged():
    """同名或包含子串的無關文字不應被誤判"""
    fake_facts = [
        {
            "fact_id": "f1",
            "fact_statement": "白髮老者楚風戰死身亡。",
            "valid_from_chapter": 87,
            "invalid_from_chapter": None,
        }
    ]
    with patch("backend.persistence.get_all_facts", return_value=fake_facts):
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=88,
            prose_text="清晨的微風拂過竹林，林清雪拔劍走入深山。",
        )
        assert finding is None
