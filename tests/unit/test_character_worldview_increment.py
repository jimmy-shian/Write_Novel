# -*- coding: utf-8 -*-
"""
角色 / 世界觀 / 篇卷增量合併單元測試：
- append_or_merge_characters：新增與既有角色合併
- append_or_merge_volume_settings：法則與勢力去重合併
- 骨架增量處理含 Fail-Safe 自動立卡
"""
import json

from backend import persistence as db
from backend.agents.volume_skeleton.runner import process_and_persist_skeleton_increments


def test_append_or_merge_characters(novel_factory):
    novel_id = novel_factory(title="增量測試小說", genre="奇幻", style="史詩")

    # 1. 建立初始角色
    initial_chars = [
        {"name": "林澤", "role": "主角", "personality": ["果斷", "冷靜"], "want": "尋找失蹤導師"},
        {"name": "蘇曉", "role": "盟友", "personality": ["敏銳"], "want": "守護家族"},
    ]
    db.save_characters(novel_id, {"characters": initial_chars})

    # 2. 增量加入新角色與更新既有角色
    increments = [
        {
            "name": "夜梟",
            "role": "主要反派",
            "faction": "暗月教團",
            "personality": "陰沉殘忍，善於偽裝",
            "motivation": "奪取古老源石",
            "first_appearance_chapter": 5,
        },
        {
            "name": "林澤",  # 既有角色，應進行合併而不是重複建立
            "speech_style": "簡潔沉穩",
            "personality": ["果斷", "富有洞察力"],
        },
    ]
    added_names = db.append_or_merge_characters(novel_id, increments)
    assert "夜梟" in added_names

    # 3. 檢查最終角色庫
    latest = db.get_latest_characters(novel_id)
    assert latest and latest.get("parsed_data")
    chars = latest["parsed_data"]["characters"]
    char_names = [c["name"] for c in chars]

    # 角色數量應為 3（林澤、蘇曉、夜梟）
    assert len(chars) == 3
    assert "夜梟" in char_names
    assert "林澤" in char_names
    assert "蘇曉" in char_names

    # 驗證夜梟的屬性是否齊全
    yexiao = next(c for c in chars if c["name"] == "夜梟")
    assert yexiao["role"] == "主要反派"
    assert "暗月教團" in yexiao["background"]
    assert yexiao["want"] == "奪取古老源石"
    assert yexiao["entry_phase"] == "第 5 章"

    # 驗證林澤的屬性已融合，且未被抹除
    linze = next(c for c in chars if c["name"] == "林澤")
    assert linze["role"] == "主角"
    assert "果斷" in linze["personality"]
    assert linze["want"] == "尋找失蹤導師"
    assert linze["speech_style"] == "簡潔沉穩"


def test_append_or_merge_volume_settings(novel_factory):
    novel_id = novel_factory(title="篇卷設定測試小說", genre="玄幻", style="熱血")

    # 建立一卷
    db.save_volumes(novel_id, [
        {
            "volume_index": 1,
            "title": "第 1 卷 風起",
            "summary": "第一卷概述",
            "factions": json.dumps([{"name": "青雲門", "alignment": "正道"}], ensure_ascii=False),
            "applicable_rules": json.dumps([{"name": "靈氣潮汐", "description": "每月十五靈氣暴漲"}], ensure_ascii=False),
        }
    ])

    # 增量寫入新法則與新勢力
    new_rules = [
        {"name": "禁魔領域", "scope": "本卷專屬", "description": "特定地宮內法術無效"},
        {"name": "靈氣潮汐", "description": "重複的法則應被去重"},
    ]
    new_factions = [
        {"name": "萬毒門", "alignment": "邪道", "summary": "擅長使毒與刺殺"},
    ]
    res = db.append_or_merge_volume_settings(novel_id, 1, new_rules=new_rules, new_factions=new_factions)

    assert len(res["rules"]) == 1
    assert res["rules"][0]["name"] == "禁魔領域"
    assert len(res["factions"]) == 1
    assert res["factions"][0]["name"] == "萬毒門"

    # 驗證資料庫中的最新狀態
    vols = db.get_volumes(novel_id)
    v1 = vols[0]
    rules = v1.get("parsed_applicable_rules") or []
    factions = v1.get("parsed_factions") or []

    rule_names = [r.get("name") for r in rules if isinstance(r, dict)]
    faction_names = [f.get("name") for f in factions if isinstance(f, dict)]

    assert "靈氣潮汐" in rule_names
    assert "禁魔領域" in rule_names
    assert "青雲門" in faction_names
    assert "萬毒門" in faction_names


def test_process_and_persist_skeleton_increments_with_failsafe(novel_factory):
    novel_id = novel_factory(title="骨架增量與防呆測試", genre="科幻", style="懸疑")

    # 初始角色只有主角
    db.save_characters(novel_id, {"characters": [{"name": "陸行", "role": "主角"}]})
    db.save_volumes(novel_id, [{"volume_index": 1, "title": "第 1 卷 啟航", "summary": "概述"}])

    # 模擬 LLM 回傳的骨架 JSON
    parsed_skeleton = {
        "volume_index": 1,
        "new_characters": [
            {
                "name": "艾拉",
                "role": "艦隊領航員",
                "faction": "深空探測會",
                "personality": "理性冷靜，數據至上",
                "motivation": "尋求第十號信標",
                "first_appearance_chapter": 1,
            }
        ],
        "new_world_rules": [
            {"name": "曲率航行過載律", "scope": "本卷專屬", "description": "連續躍遷三次需冷卻八小時"}
        ],
        "new_factions": [
            {"name": "深空探測會", "alignment": "中立探索", "summary": "致力於未知星區拓荒"}
        ],
    }

    # 模擬章節骨架：characters_active 中出現了艾拉（已有宣告）以及「雷蒙艦長」（LLM 漏未在 new_characters 宣告！）
    chapters_skeleton = [
        {
            "chapter_index": 1,
            "chapter_title": "星港起航",
            "characters_active": ["陸行", "艾拉", "雷蒙艦長", "守衛"],
        }
    ]

    result = process_and_persist_skeleton_increments(
        novel_id=novel_id,
        volume_index=1,
        parsed_skeleton=parsed_skeleton,
        chapters_skeleton=chapters_skeleton,
        start_chapter=1,
    )

    # 驗證增量結果
    added = result["added_characters"]
    assert "艾拉" in added
    # Fail-Safe 應偵測到「雷蒙艦長」並自動立卡，而「守衛」被通用詞過濾
    assert "雷蒙艦長" in added
    assert "守衛" not in added

    # 驗證角色庫
    latest_chars = db.get_latest_characters(novel_id)["parsed_data"]["characters"]
    names = [c["name"] for c in latest_chars]
    assert "陸行" in names
    assert "艾拉" in names
    assert "雷蒙艦長" in names

    # 驗證世界觀補丁
    patches = db.get_worldview_patches(novel_id)
    patch_categories = [p.get("category") for p in patches]
    assert any("世界法則" in cat for cat in patch_categories)
    assert any("勢力" in cat for cat in patch_categories)

    # 驗證篇卷設定
    vols = db.get_volumes(novel_id)
    assert any("曲率航行過載律" in str(r) for r in vols[0].get("parsed_applicable_rules", []))
    assert any("深空探測會" in str(f) for f in vols[0].get("parsed_factions", []))