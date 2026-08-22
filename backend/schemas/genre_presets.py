# -*- coding: utf-8 -*-
"""
小說題材架構預設 (Genre Presets)
為不同題材類型（玄幻、奇幻、懸疑、都市、科幻、大眾小說）提供結構、勢力密度、伏筆與節奏的合理預設。
避免將百萬字群像小說的「15-24 幕、6 勢力、3 主軸、50 伏筆」寫死為所有小說的通用規則。
"""

from typing import Dict, Any

GENRE_PRESETS: Dict[str, Dict[str, Any]] = {
    "epic_fantasy": {
        "name": "epic_fantasy",
        "display_name": "史詩奇幻 / 西幻大長篇",
        "preferred_main_arcs": "3-5 條交織長線主軸",
        "min_factions": 4,
        "max_factions": 8,
        "multi_act_count_range": (12, 24),
        "target_volume_count_range": (8, 16),
        "target_chapters_per_volume": (35, 50),
        "foreshadowing_density": "high",
        "recommended_min_seeds": 30,
        "recommended_min_turns": 25,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "medium",
        "show_tell_balance_hint": "宏觀陣營局勢與地理過場允許 Summary/Tell；核心戰役、魔法探索與角色背叛必須全力 Scene/Show。",
    },
    "xianxia": {
        "name": "xianxia",
        "display_name": "古典修仙 / 東方玄幻",
        "preferred_main_arcs": "3-4 條因果與道心主線",
        "min_factions": 4,
        "max_factions": 7,
        "multi_act_count_range": (10, 20),
        "target_volume_count_range": (6, 15),
        "target_chapters_per_volume": (30, 50),
        "foreshadowing_density": "high",
        "recommended_min_seeds": 25,
        "recommended_min_turns": 25,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "close",
        "show_tell_balance_hint": "修煉閉關、境界說明與時光流逝使用精練 Summary；生死鬥法、道心叩問與秘境奪寶全力 Scene/Show。",
    },
    "mystery_suspense": {
        "name": "mystery_suspense",
        "display_name": "懸疑推理 / 驚悚解謎",
        "preferred_main_arcs": "1-3 條緊湊線索與真相調查主線",
        "min_factions": 2,
        "max_factions": 4,
        "multi_act_count_range": (6, 12),
        "target_volume_count_range": (3, 8),
        "target_chapters_per_volume": (20, 35),
        "foreshadowing_density": "very_high",
        "recommended_min_seeds": 20,
        "recommended_min_turns": 20,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "close",
        "knowledge_control_priority": "very_high",
        "show_tell_balance_hint": "線索發現、審訊心理戰、證物鑑定必須細膩 Scene/Show；日常交通與例行公務簡潔 Summary。",
    },
    "romance_urban": {
        "name": "romance_urban",
        "display_name": "都市情感 / 戀愛生活",
        "preferred_main_arcs": "1-2 條核心情感關係與個人成長弧線",
        "min_factions": 1,
        "max_factions": 3,
        "multi_act_count_range": (4, 8),
        "target_volume_count_range": (2, 6),
        "target_chapters_per_volume": (20, 40),
        "foreshadowing_density": "medium",
        "recommended_min_seeds": 10,
        "recommended_min_turns": 10,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "close",
        "thought_mode": "free_indirect",
        "show_tell_balance_hint": "日常瑣事與工作通勤乾淨 Summary；情感試探、心動瞬間、價值觀衝突與告白全力 Scene/Show。",
    },
    "sci_fi": {
        "name": "sci_fi",
        "display_name": "硬派科幻 / 太空歌劇 / 賽博龐克",
        "preferred_main_arcs": "2-4 條科技倫理、陣營博弈與文明存亡主線",
        "min_factions": 3,
        "max_factions": 6,
        "multi_act_count_range": (8, 16),
        "target_volume_count_range": (4, 10),
        "target_chapters_per_volume": (25, 45),
        "foreshadowing_density": "high",
        "recommended_min_seeds": 20,
        "recommended_min_turns": 20,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "medium",
        "show_tell_balance_hint": "技術規格與背景歷史以環境細節與操作界面呈現，避免教科書式說明；核心抉擇與危機爆發全力 Scene/Show。",
    },
    "general_fiction": {
        "name": "general_fiction",
        "display_name": "大眾小說 / 冒險傳奇",
        "preferred_main_arcs": "2-3 條清晰主線",
        "min_factions": 2,
        "max_factions": 5,
        "multi_act_count_range": (6, 14),
        "target_volume_count_range": (3, 10),
        "target_chapters_per_volume": (25, 45),
        "foreshadowing_density": "medium",
        "recommended_min_seeds": 15,
        "recommended_min_turns": 15,
        "narrative_mode": "third_person_limited",
        "narrative_distance": "close",
        "show_tell_balance_hint": "轉場過渡適度 Summary；關鍵行動、衝突高潮與重要對話深度 Scene/Show。",
    }
}

DEFAULT_GENRE = "general_fiction"


def get_genre_preset(genre_key: str = None) -> Dict[str, Any]:
    """取得指定題材或預設題材的架構配置。"""
    if not genre_key:
        return GENRE_PRESETS[DEFAULT_GENRE].copy()
    key = genre_key.strip().lower()
    return GENRE_PRESETS.get(key, GENRE_PRESETS[DEFAULT_GENRE]).copy()
