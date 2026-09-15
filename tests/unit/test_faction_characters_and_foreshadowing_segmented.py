# -*- coding: utf-8 -*-
import json
import uuid
import pytest

from backend import persistence as db
from backend.agents.foreshadowing_orchestrator.prompts import build_foreshadowing_messages
from backend.agents.character_designer.prompts import build_character_designer_messages
from backend.services.autonomous_pipeline import (
    _are_characters_ready,
    _are_seeds_ready,
    _are_turning_points_ready,
)


def test_foreshadowing_established_seeds_injection():
    """驗證在生成 key_turning_points 時，系統主動注入已確立之伏筆種子網絡並要求因果聯動"""
    seeds = [
        {
            "id": 1,
            "name": "專利局隱秘印記",
            "related_characters": ["林夜", "雷蒙審查官"],
            "payoff_hint": "於第25章由林夜暗中引爆，揭發專利局偽造法術產權",
            "description": "法杖末端刻有專利局查抄黑市時留下的隱蔽魔紋",
        },
        {
            "id": 2,
            "name": "拜星教暗殺名單",
            "related_characters": ["蘇雪", "教團狂信徒"],
            "payoff_hint": "名單上的血印在月圓之夜會發出共鳴警報",
            "description": "羊皮紙夾層中的密文",
        }
    ]

    messages = build_foreshadowing_messages(
        worldview_text="世界觀設定...",
        characters_json='{"characters": [{"name": "林夜"}]}',
        user_prompt="請規劃關鍵轉折點",
        target_field="key_turning_points",
        batch_size=15,
        existing_items=[],
        start_id=1,
        established_seeds=seeds,
    )

    system_content = messages[0]["content"]
    # 驗證 prompt 中包含伏筆聯動要求與種子網絡內容
    assert "伏筆與轉折組合聯動要求" in system_content
    assert "專利局隱秘印記" in system_content
    assert "拜星教暗殺名單" in system_content
    assert "雷蒙審查官" in system_content


def test_faction_tiered_character_prompts():
    """驗證角色設計師的陣營梯隊分段提示詞生成"""
    faction = {
        "name": "奧術專利局與執法司",
        "position": "壟斷高階法術產權，壓制平民與底層法師",
        "resources": "帝國法權、制式審判軍團、專利監察使",
        "relationship_to_protagonist": "正面體制宿敵與階級剝削者",
    }

    # 第一梯隊：高層核心
    messages_t1 = build_character_designer_messages(
        worldview_text="世界觀...",
        existing_chars_json='{"characters": []}',
        user_prompt="設計角色",
        hint="",
        mode="generate",
        target_char_index=None,
        novel_id="test_novel",
        faction_info=faction,
        tier=1,
        target_batch_count=4,
    )
    user_content_t1 = messages_t1[1]["content"]
    assert "奧術專利局與執法司" in user_content_t1
    assert "第一梯隊" in user_content_t1
    assert "wound_origin" in user_content_t1
    assert "false_belief" in user_content_t1
    assert "belief_collapse_3beats" in user_content_t1

    # 第二梯隊：中堅骨幹與內部異見者
    existing_t1_chars = json.dumps({
        "characters": [
            {"name": "雷蒙局長", "faction": "奧術專利局與執法司", "role": "最高審查官"}
        ]
    }, ensure_ascii=False)
    messages_t2 = build_character_designer_messages(
        worldview_text="世界觀...",
        existing_chars_json=existing_t1_chars,
        user_prompt="設計角色",
        hint="",
        mode="generate",
        target_char_index=None,
        novel_id="test_novel",
        faction_info=faction,
        tier=2,
        target_batch_count=4,
    )
    user_content_t2 = messages_t2[1]["content"]
    assert "奧術專利局與執法司" in user_content_t2
    assert "第二梯隊" in user_content_t2
    assert "雷蒙局長" in user_content_t2
    assert "independent_arc" in user_content_t2
    assert "off_screen_goal" in user_content_t2


def test_merge_two_characters_backend_preserves_rich_attributes():
    """驗證去重合併時完整保留 faction, wound_origin, false_belief 等所有豐富欄位"""
    c1 = {
        "name": "雷蒙 (奧術專利局)",
        "role": "首席審判使",
        "faction": "奧術專利局",
        "wound_origin": "家族曾因無專利被剝奪貴族頭銜",
        "false_belief": "專利壟斷是維繫文明秩序的唯一基石",
        "belief_collapse_3beats": ["審判失手", "高層背叛", "真相揭曉"],
        "want": "晉升執政官",
        "personality": ["冷酷", "嚴謹"],
    }
    c2 = {
        "name": "雷蒙",  # 同一核心名
        "speech_profile": {
            "default_register": "冷靜正式",
            "directness": "直截了當",
        },
        "off_screen_goal": "暗中資助生病的妹妹",
        "personality": ["嚴謹", "追求完美"],
    }

    cleaned = db.clean_and_deduplicate_characters([c1, c2])
    assert len(cleaned) == 1
    merged = cleaned[0]
    assert merged["name"] == "雷蒙"
    assert merged["faction"] == "奧術專利局"
    assert merged["wound_origin"] == "家族曾因無專利被剝奪貴族頭銜"
    assert merged["false_belief"] == "專利壟斷是維繫文明秩序的唯一基石"
    assert len(merged["belief_collapse_3beats"]) == 3
    assert merged["off_screen_goal"] == "暗中資助生病的妹妹"
    assert merged["speech_profile"]["default_register"] == "冷靜正式"


def test_pipeline_scale_thresholds():
    """驗證自主流水線對伏筆/轉折 (50+) 與角色規模 (15+) 的檢驗能力"""
    novel_id = f"test_scale_{uuid.uuid4()}"
    db.create_novel(novel_id, "規模檢驗小說", "奇幻", "史詩")
    try:
        # 1. 角色規模檢驗
        # 只有 3 位角色時，min_count=15 應判定為尚未就緒
        three_chars = {
            "characters": [
                {"name": "林夜", "role": "主角", "faction": "市井同盟"},
                {"name": "蘇雪", "role": "女主角", "faction": "市井同盟"},
                {"name": "老黑", "role": "工坊掌櫃", "faction": "市井同盟"},
            ]
        }
        db.save_characters(novel_id, json.dumps(three_chars, ensure_ascii=False))
        assert _are_characters_ready(novel_id, min_count=15) is False
        # 默認 min_count=2 保持向後相容通過
        assert _are_characters_ready(novel_id) is True

        # 寫入 16 位角色時，min_count=15 應判定為就緒
        distinct_names = [
            "林夜", "蘇雪", "老黑", "雷蒙審查官", "奧古斯都局長", "卡特隊長",
            "幽冥祭司", "赤血狂徒", "黑袍長老", "艾爾登副院長", "薇薇安首席",
            "莫里亞掌櫃", "灰狐掮客", "毒蠍刺客", "銀翼信使", "鐵壁守衛"
        ]
        sixteen_chars = {
            "characters": [
                {"name": name, "role": "配角", "faction": f"陣營_{i % 4}"}
                for i, name in enumerate(distinct_names)
            ]
        }
        db.save_characters(novel_id, json.dumps(sixteen_chars, ensure_ascii=False))
        assert _are_characters_ready(novel_id, min_count=15) is True

        # 2. 伏筆種子檢驗 (目標 50+)
        wb_dict = {
            "theme": "測試主題",
            "main_conflict": "核心矛盾",
            "worldview": "世界觀",
            "macro_outline": "大綱",
            "foreshadowing_seeds": [{"id": i, "name": f"種子_{i}"} for i in range(1, 20)],
            "key_turning_points": [{"id": i, "name": f"轉折_{i}"} for i in range(1, 20)],
        }
        db.save_worldbuilding(novel_id, json.dumps(wb_dict, ensure_ascii=False))
        # 僅 19 條時，min_count=50 應判定為 False
        assert _are_seeds_ready(novel_id, min_count=50) is False
        assert _are_turning_points_ready(novel_id, min_count=50) is False

        # 擴充至 52 條時，min_count=50 判定為 True
        wb_dict["foreshadowing_seeds"] = [{"id": i, "name": f"種子_{i}"} for i in range(1, 53)]
        wb_dict["key_turning_points"] = [{"id": i, "name": f"轉折_{i}"} for i in range(1, 53)]
        db.save_worldbuilding(novel_id, json.dumps(wb_dict, ensure_ascii=False))
        assert _are_seeds_ready(novel_id, min_count=50) is True
        assert _are_turning_points_ready(novel_id, min_count=50) is True

    finally:
        db.delete_novel(novel_id)
