# -*- coding: utf-8 -*-
"""
早期規劃代理跨脈絡注入單元測試：
- volumes_planner 注入角色 + 伏筆
- character_designer 注入伏筆 + 篇卷
- foreshadowing_orchestrator 注入篇卷結構
- story_architect 在增量/修訂模式注入既有資產
"""
import json

from backend.agents.volumes_planner.prompts import build_volumes_planner_messages
from backend.agents.character_designer.prompts import build_character_designer_messages
from backend.agents.foreshadowing_orchestrator.prompts import build_foreshadowing_messages
from backend.agents.story_architect.prompts import (
    build_story_architect_messages,
    build_worldview_core_messages,
    build_multi_act_structure_messages,
    build_progressive_character_plan_messages,
)


def test_volumes_planner_messages_injects_characters_and_foreshadowing():
    """Verify that build_volumes_planner_messages includes character and foreshadowing context."""
    chars_summary = "- 【林羽】（陣營: 青雲門，定位: 主角，核心追求: 復仇）"
    foreshadow_summary = "- [seed_1] 破魂劍的詛咒（預計回收章: 45）"

    # 1. Batch generate mode
    msgs = build_volumes_planner_messages(
        worldview_text="修仙世界觀",
        existing_vols=[],
        user_prompt="規劃篇卷",
        hint=None,
        mode="generate",
        target_vol_idx=None,
        novel_id="test_novel_1",
        batch_info={"start_vol_idx": 1, "end_vol_idx": 3, "batch_count": 3, "total_target": 12},
        characters_summary=chars_summary,
        foreshadowing_summary=foreshadow_summary,
    )
    user_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    sys_text = "\n".join(m["content"] for m in msgs if m["role"] == "system")

    assert "已確立角色人物誌" in user_text
    assert "林羽" in user_text
    assert "全書伏筆網絡與關鍵轉折點" in user_text
    assert "破魂劍的詛咒" in user_text
    assert "角色弧線與矛盾焦點" in user_text
    assert "伏筆收束與轉折爆發" in user_text
    assert "核心角色名冊" in sys_text

    # 2. Patch mode
    patch_msgs = build_volumes_planner_messages(
        worldview_text="修仙世界觀",
        existing_vols=[{"volume_index": 1, "title": "初出茅廬", "summary": "開端"}],
        user_prompt="修補第 1 卷",
        hint="加強衝突",
        mode="patch",
        target_vol_idx=1,
        characters_summary=chars_summary,
        foreshadowing_summary=foreshadow_summary,
    )
    patch_user_text = "\n".join(m["content"] for m in patch_msgs if m["role"] == "user")
    assert "已確立角色人物誌" in patch_user_text
    assert "全書伏筆網絡與關鍵轉折點" in patch_user_text


def test_character_designer_messages_injects_foreshadowing_and_volumes():
    """Verify that build_character_designer_messages includes foreshadowing and volumes context."""
    fs_reqs = "- 【seed_1】破魂劍的詛咒（關聯角色需求: 林羽）"
    vols_overview = "- 第 1 卷《初出茅廬》：踏入黑市遭遇伏擊"

    # 1. Generate mode
    gen_msgs = build_character_designer_messages(
        worldview_text="世界觀",
        existing_chars_json='{"characters": []}',
        user_prompt="生成角色",
        hint=None,
        mode="generate",
        target_char_index=None,
        faction_info={"name": "青雲門", "position": "正道領袖", "resources": "靈石", "relationship_to_protagonist": "同盟"},
        tier=1,
        foreshadowing_requirements=fs_reqs,
        volumes_overview=vols_overview,
    )
    gen_user = "\n".join(m["content"] for m in gen_msgs if m["role"] == "user")
    gen_sys = "\n".join(m["content"] for m in gen_msgs if m["role"] == "system")
    assert "全書伏筆網絡與秘密承載需求" in gen_user
    assert "破魂劍的詛咒" in gen_user
    assert "全書分卷結構概覽" in gen_user
    assert "初出茅廬" in gen_user
    assert "伏筆承載需求" in gen_sys

    # 2. Expand mode
    exp_msgs = build_character_designer_messages(
        worldview_text="世界觀",
        existing_chars_json='{"characters": [{"name": "林羽"}]}',
        user_prompt="追加角色",
        hint="補足黑市管事",
        mode="expand",
        target_char_index=None,
        foreshadowing_requirements=fs_reqs,
        volumes_overview=vols_overview,
    )
    exp_user = "\n".join(m["content"] for m in exp_msgs if m["role"] == "user")
    assert "全書伏筆網絡與秘密承載需求" in exp_user
    assert "全書分卷結構概覽" in exp_user


def test_foreshadowing_messages_injects_volumes_structure():
    """Verify that build_foreshadowing_messages includes volumes structure alignment."""
    vols_struct = "- 第 1 卷《初出茅廬》（第 1-45 章，45 章）：主角走出新手村"

    # 1. Seeds mode
    seed_msgs = build_foreshadowing_messages(
        worldview_text="世界觀",
        characters_json='{"characters": [{"name": "林羽"}]}',
        user_prompt="設計伏筆",
        target_field="foreshadowing_seeds",
        volumes_structure=vols_struct,
    )
    seed_user = "\n".join(m["content"] for m in seed_msgs if m["role"] == "user")
    seed_sys = "\n".join(m["content"] for m in seed_msgs if m["role"] == "system")
    assert "全書篇卷架構與章節區間" in seed_user
    assert "第 1-45 章" in seed_user
    assert "篇卷結構對齊要求" in seed_sys or "篇卷結構對齊要求" in seed_user
    assert "payoff_deadline_chapter" in seed_sys or "payoff_deadline_chapter" in seed_user

    # 2. Turning points mode
    turn_msgs = build_foreshadowing_messages(
        worldview_text="世界觀",
        characters_json='{"characters": [{"name": "林羽"}]}',
        user_prompt="設計轉折",
        target_field="key_turning_points",
        volumes_structure=vols_struct,
    )
    turn_user = "\n".join(m["content"] for m in turn_msgs if m["role"] == "user")
    assert "全書篇卷架構與章節區間" in turn_user


def test_story_architect_messages_injects_existing_assets_context():
    """Verify that story_architect message builders inject existing asset summaries when revising."""
    assets_summary = "- 已確立核心角色: 林羽（主角）, 周煞（宿敵）\n- 已確立篇卷: 第 1 卷《初出茅廬》"

    # 1. Core messages
    core_msgs = build_worldview_core_messages(
        genre="修仙",
        style="古典仙俠",
        user_prompt="修訂世界觀",
        existing_assets_context=assets_summary,
    )
    core_user = "\n".join(m["content"] for m in core_msgs if m["role"] == "user")
    assert "已確立之既有設定資產" in core_user
    assert "林羽" in core_user

    # 2. Multi-act messages
    act_msgs = build_multi_act_structure_messages(
        worldview_core_json='{"theme": "修仙"}',
        user_prompt="規劃多幕",
        existing_assets_context=assets_summary,
    )
    act_user = "\n".join(m["content"] for m in act_msgs if m["role"] == "user")
    assert "已確立之既有設定資產" in act_user

    # 3. Progressive character plan messages
    plan_msgs = build_progressive_character_plan_messages(
        worldview_core_json='{"theme": "修仙"}',
        multi_act_json='{"multi_act_structure": []}',
        user_prompt="規劃登場",
        existing_assets_context=assets_summary,
    )
    plan_user = "\n".join(m["content"] for m in plan_msgs if m["role"] == "user")
    assert "已確立之既有設定資產" in plan_user
