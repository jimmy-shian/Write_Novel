# -*- coding: utf-8 -*-
from unittest.mock import patch
from backend.services.narrative.narrative_auditor import NarrativeAuditor


def test_invalid_from_chapter_none_no_none_string():
    """僅有觀測 fact 時，不得把任意文字升格為命運違規。"""
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
        assert finding is None


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
    """觀測 fact 不得單獨決定角色生死；命運檢查由 Story Canon 負責。"""
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
        assert finding is None


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


def test_canonical_life_contract_is_the_temporal_audit_source():
    issue = {
        "severity": "critical",
        "evidence": "楚風未經授權再次行動。",
        "recommendation": "請依章節契約修正。",
    }
    with patch(
        "backend.services.narrative.story_canon.validate_life_contract",
        return_value=[issue],
    ) as validate:
        finding = NarrativeAuditor._check_temporal_fact_compliance(
            novel_id="test_novel",
            chapter_index=88,
            prose_text="楚風冷笑一聲。",
            outline={"planned_events": []},
        )
    validate.assert_called_once_with("test_novel", 88, {"planned_events": []}, "楚風冷笑一聲。")
    assert finding["severity"] == "critical"
    assert finding["evidence"] == issue["evidence"]
