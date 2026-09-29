# -*- coding: utf-8 -*-
"""
Unit tests for GoldRulesManager and Governance
"""

import os
import tempfile
import pytest
from backend.services.gold_rules.gold_rules_manager import (
    GoldRule,
    GoldRulesManager,
)


def test_gold_rule_serialization():
    rule = GoldRule(
        rule_id="GR-TEST-001",
        scope=["chapter_writer", "editor"],
        category="dialogue",
        strength="soft",
        rule="避免機械式句尾口頭禪",
        condition="角色交談時",
        source="human_review",
        confidence=0.95,
        version=2,
        status="approved",
    )
    d = rule.to_dict()
    assert d["rule_id"] == "GR-TEST-001"
    assert d["confidence"] == 0.95

    reconstructed = GoldRule.from_dict(d)
    assert reconstructed.rule_id == "GR-TEST-001"
    assert reconstructed.scope == ["chapter_writer", "editor"]
    assert reconstructed.version == 2


def test_gold_rules_query_and_scope_filtering():
    mgr = GoldRulesManager()
    rules = [
        GoldRule(
            rule_id="GR-001",
            scope=["chapter_writer"],
            category="pov",
            strength="hard",
            rule="嚴格鎖定 POV 視角",
            confidence=1.0,
            status="approved",
        ),
        GoldRule(
            rule_id="GR-002",
            scope=["editor"],
            category="editing",
            strength="hard",
            rule="只修訂標記之瑕疵段落",
            confidence=0.9,
            status="approved",
        ),
        GoldRule(
            rule_id="GR-003",
            scope=["chapter_writer"],
            category="dialogue",
            strength="soft",
            rule="對話體現受壓反應",
            confidence=0.8,
            status="draft",
        ),
    ]

    novel_id = "test_novel_governance"
    mgr.save_rules(novel_id, rules)

    writer_rules = mgr.query_rules(novel_id, agent_scope="chapter_writer", status="approved")
    assert len(writer_rules) == 1
    assert writer_rules[0].rule_id == "GR-001"

    editor_rules = mgr.query_rules(novel_id, agent_scope="editor", status="approved")
    assert len(editor_rules) == 1
    assert editor_rules[0].rule_id == "GR-002"


def test_gold_rules_formatting_prompt():
    mgr = GoldRulesManager()
    novel_id = "test_novel_prompt_format"
    rules = [
        GoldRule(
            rule_id="GR-010",
            scope=["chapter_writer"],
            category="exposition",
            strength="soft",
            rule="世界觀應化為眼前的阻礙，禁止設定集說明",
            condition="涉及背景時",
            confidence=0.95,
            status="approved",
        )
    ]
    mgr.save_rules(novel_id, rules)

    prompt_block = mgr.format_rules_for_prompt(novel_id, agent_scope="chapter_writer")
    assert "CHAPTER_WRITER 寫作策略與黃金指引 (Gold Rules)" in prompt_block
    assert "軟準則" in prompt_block
    assert "世界觀應化為眼前的阻礙" in prompt_block
