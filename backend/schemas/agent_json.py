# -*- coding: utf-8 -*-
"""
AI 小說工廠流程 JSON Schema 定義

可直接引用使用的各流程 JSON 格式模組
"""

import json

# =============================================================================
# 1. worldview (世界觀架構師 Story Architect Agent)
# =============================================================================

WORLDVIEW_SCHEMA = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "setting": "",
    "power_system": "",
    "rules": [],
    "factions": [
        {
            "name": "勢力/組織名稱",
            "position": "立場與利益",
            "resources": "掌握資源或制度權力",
            "relationship_to_protagonist": "與主角/核心衝突的關係"
        }
    ],
    "locations": [],
    "timeline": [],
    "macro_outline": "",
    "multi_act_structure": [
        {"title": "第一幕 破局啟程", "content": "本幕核心推動力、主要衝突與幕尾懸念"},
        {"title": "第二幕 矛盾激化", "content": "危機升級、各方陣營博弈與人物代價"},
        {"title": "第三幕 終局對決", "content": "終極高潮爆發與命運走向"}
    ],
    "progressive_character_plan": [
        {"title": "第一波 核心主角與初期同盟", "content": "登場人物、功能定位與引導作用"},
        {"title": "第二波 執法宿敵與多方勢力", "content": "矛盾升級後的對立陣營骨幹"},
        {"title": "第三波 幕後黑手與終極反派", "content": "引爆終局危機的關鍵人物"}
    ]
}

WORLDVIEW_REQUIRED_FIELDS = ["theme", "main_conflict", "worldview", "macro_outline"]
WORLDVIEW_RECOMMENDED_FIELDS = ["setting", "power_system", "rules", "factions", "locations", "timeline", "multi_act_structure", "progressive_character_plan"]

WORLDVIEW_CHAPTER_PATCH = {
    "category": "",
    "details": "",
    "source_chapter": 0,
    "created_at": ""
}
FORESHADOWING_OUTPUT_SCHEMA = {
    "foreshadowing_seeds": [
        {
            "id": 1,
            "name": "伏筆名稱（文字，不含 FS/Seed 標號）",
            "method": "action | dialogue | carrier_object | environment | omission | relationship_shift",
            "description": "伏筆內容與表層偽裝（文字）",
            "setup_hint": "適合埋設時機或敘事載體（文字）",
            "subtlety": "high | medium | low",
            "expected_payoff_window": "預期回收篇卷或章節範圍（文字）",
            "payoff_deadline_chapter": 0,
            "integration_group": "懸念合流歸納分組標籤（如：外域氏族幕後資助拜星教）",
            "payoff_hint": "未來回收方式與反轉效果（文字）",
            "related_characters": ["角色名"],
            "thematic_link": "與主題或核心衝突的連結（文字）"
        }
    ],
    "key_turning_points": [
        {
            "id": 1,
            "turning_point_name": "轉折名稱（文字，不含 TP/Turn 標號）",
            "description": "轉折事件與角色動機衝突（文字）",
            "trigger_condition": "觸發條件或引爆事件（文字）",
            "structural_impact": "對陣營、關係或主線局勢的實質改變（文字）",
            "emotional_stakes": "情感張力與角色代價（文字）",
            "related_characters": ["角色名"]
        }
    ]
}

# 伏筆與轉折通過標準（總監評判用）
FORESHADOWING_APPROVAL_CRITERIA = {
    "name": "foreshadowing",
    "display_name": "伏筆與轉折編織師",
    "criteria": {
        "required_top_level_keys": {
            "description": "輸出必須包含 foreshadowing_seeds 與 key_turning_points；分批生成時只能輸出本批指定的其中一個頂層鍵"
        },
        "foreshadowing_seed_count": {
            "description": "foreshadowing_seeds 數量依題材與篇幅合理規劃；id 必須是從 1 開始連續的 JSON number / integer"
        },
        "turning_point_count": {
            "description": "key_turning_points 數量依題材與篇幅合理規劃；id 必須是從 1 開始連續的 JSON number / integer"
        },
        "foreshadowing_seed_fields": {
            "required_fields": ["id", "name", "description", "setup_hint", "payoff_hint", "related_characters", "thematic_link"],
            "description": "每個伏筆種子可採用實物、行為、對話、環境或遺漏等多元載體，具備表層偽裝、埋設提示、回收方向、關聯角色與主題連結"
        },
        "turning_point_fields": {
            "required_fields": ["id", "turning_point_name", "description", "trigger_condition", "structural_impact", "emotional_stakes", "related_characters"],
            "description": "每個關鍵轉折點必須有觸發條件、結構性影響、情感代價與關聯角色"
        },
        "content_quality": {
            "description": "伏筆不能只是抽象概念或同義改寫湊數；轉折點必須造成局勢、關係或角色弧線的實質改變"
        },
    },
}

# 世界觀通過標準（總監評判用）
WORLDVIEW_APPROVAL_CRITERIA = {
    "name": "worldview",
    "display_name": "世界觀架構師",
    "criteria": {
        "structure": {
            "required_fields": ["theme", "main_conflict", "worldview", "macro_outline"],
            "description": "必須完整包含 theme, main_conflict, worldview, macro_outline 四大核心欄位"
        },
        "theme": {
            "description": "深入剖析核心價值觀衝突與哲學命題，篇幅 50 至 500 字"
        },
        "main_conflict": {
            "description": "精準刻劃多方陣營情節張力網與生死利益博弈，篇幅 100 至 800 字"
        },
        "worldview": {
            "description": "詳盡確立地理舞台、超自然或技術力量法則與社會權力階層，篇幅 300 字以上"
        },
        "macro_outline": {
            "description": "明確勾勒全書開端、矛盾激化、全局逆轉與終局高潮之宏觀骨架"
        },
        "factions": {
            "description": "勢力設定必須包含主要陣營、立場、利益訴求與敵友關係"
        },
        "multi_act_structure": {
            "description": "幕次標題採用中文數字依序編排並結合主旨命名，各幕起承轉合功能清晰，層層遞進"
        },
        "progressive_character_plan": {
            "description": "波次標題採用中文數字依序編排並概括角色定位，與多幕結構起伏緊密對齊"
        },
        "consistency": {
            "description": "各欄位設定高度自洽互鎖，緊扣故事核心原案基石"
        }
    },
}

WORLDVIEW_CORE_APPROVAL_CRITERIA = {
    "name": "worldview_core",
    "display_name": "核心世界觀架構師",
    "criteria": {
        "structure": {
            "required_fields": ["theme", "main_conflict", "worldview", "macro_outline"],
            "description": "完整包含 theme, main_conflict, worldview, macro_outline 四大核心欄位"
        },
        "theme": {
            "description": "深入剖析核心價值觀衝突與哲學命題，篇幅 50 至 500 字"
        },
        "main_conflict": {
            "description": "精準刻劃多方陣營情節張力網與利益博弈，篇幅 100 至 800 字"
        },
        "worldview": {
            "description": "確立地理舞台、超自然或技術力量法則與社會階層，篇幅 300 字以上"
        },
        "macro_outline": {
            "description": "明確勾勒全書開端、矛盾激化、全局逆轉與終局高潮之宏觀骨架"
        },
        "consistency": {
            "description": "各欄位設定高度自洽互鎖，緊扣故事核心原案基石"
        }
    },
}

MULTI_ACT_STRUCTURE_APPROVAL_CRITERIA = {
    "name": "multi_act_structure",
    "display_name": "多幕式結構師",
    "criteria": {
        "multi_act_structure": {
            "description": "幕次標題採用中文數字依序編排並結合該幕主旨命名，起承轉合功能清晰，層層遞進"
        }
    },
}

PROGRESSIVE_CHARACTER_PLAN_APPROVAL_CRITERIA = {
    "name": "progressive_character_plan",
    "display_name": "角色登場策略規劃師",
    "criteria": {
        "progressive_character_plan": {
            "description": "波次標題採用中文數字依序編排並概括角色功能，與各幕起伏對齊，展現群像登場與成長"
        }
    },
}



# =============================================================================
# 2. characters (角色設計師 Character Designer Agent)
# =============================================================================

CHARACTER_SCHEMA = {
    "name": "",
    "role": "",
    "entry_phase": "",
    "faction": "",
    "affiliation": "",
    "personality": [],
    "want": "",
    "need": "",
    "fatal_flaw": "",
    "want_need_conflict": "", # want 與 need 的內心衝突與靈魂拉扯
    "secret": "", # 角色的不可告人秘密 (用來做為伏筆)
    "wound_origin": "", # 創傷原點（反派或核心轉變角色必填）
    "false_belief": "", # 核心認知偏見或執念
    "belief_collapse_3beats": [], # 三階動態信念崩塌節奏（認知初裂 -> 體制反噬 -> 致命真相）
    "independent_arc": {}, # 配角三階段獨立成長線（phase_1, phase_2, phase_3）
    "off_screen_goal": "", # 配角場外個人追求（如開店、考取資格、保護家族）
    "independent_goal": "", # Story Engine 2.0: 配角在主角之外獨立追求之具體目標
    "current_problem": "", # Story Engine 2.0: 當前正面臨之具體問題/危機
    "personal_stake": "", # Story Engine 2.0: 該角色自身的利害代價
    "relationship_dependency": "", # Story Engine 2.0: 與主角/他人的情感或利益依賴
    "capability_constraints": [], # Story Engine 2.0: 主角/強者的能力邊界、適用限制、暴露風險與不可逆代價
    "decision_model": {}, # Story Engine 2.0: 反派決策模型 (goal, perceived_threat, resource, constraint, red_line, preferred_method)
    "motivation": "",
    "arc": "",
    "speech_style": "", # 兼容舊版：說話風格概述
    "speech_profile": {
        "default_register": "冷靜正式 | 溫和儒雅 | 市井隨性 | 諷刺自嘲 | 孤僻寡言",
        "sentence_length": "偏短簡練 | 中等流暢 | 繁複長句 | 破碎斷續",
        "directness": "直截了當 | 迂迴含蓄 | 官僚推託 | 試探防禦",
        "emotional_leak": "極少外露 | 受壓時語調冷酷 | 容易激動",
        "power_behavior": "面對上位者迂迴防備，面對同儕隨和，面對弱者果斷",
        "under_pressure": "句子明顯縮短、用詞轉為精確冷冽",
        "taboo_topics": []
    },
    "initial_knowledge_scope": [], # 角色開篇時已知情報與秘密範圍
    "appearance": "",
    "background": "",
    "relationships": [],
    "relationship_matrix": [] # 精細的角色關係網說明
}

CHARACTER_RELATIONSHIP_SCHEMA = {
    "with": "",
    "type": "",
    "evolution": ""
}

CHARACTERS_ROOT_SCHEMA = {
    "characters": []
}

# --- 寫作 agent 角色設定傳遞過濾清單 ---
# 用於 writer agent 章節寫作時，extract_character_basic() 保留這些欄位
# 也供 diagnostics.py 等模組統一引用，避免各處硬編碼
CHARACTER_BASIC_FIELDS = [
    "name",
    "role",
    "entry_phase",
    "faction",
    "affiliation",
    "personality",
    "want",
    "need",
    "fatal_flaw",
    "want_need_conflict",
    "secret",
    "wound_origin",
    "false_belief",
    "belief_collapse_3beats",
    "independent_arc",
    "off_screen_goal",
    "independent_goal",
    "current_problem",
    "personal_stake",
    "relationship_dependency",
    "capability_constraints",
    "decision_model",
    "speech_style",
    "speech_profile",
    "initial_knowledge_scope",
    "appearance",
    "motivation",
    "arc",
    "background",
    "relationships",
    "relationship_matrix"
]

# 角色通過標準（總監評判用）
CHARACTER_APPROVAL_CRITERIA = {
    "name": "characters",
    "display_name": "角色設計師",
    "criteria": {
        "required_fields": {
            "per_character": ["name", "role", "entry_phase", "personality", "want", "need", "fatal_flaw", "want_need_conflict", "secret", "motivation", "arc", "background", "relationships", "relationship_matrix"],
            "description": "每個角色必填欄位必須完整，不得為空或佔位符"
        },
        "name_validity": {
            "description": "name 欄位為角色的具體姓名，身分與組織職位請填入 role 欄位"
        },
        "character_count": {
            "description": "需要主角、反派/宿敵、以及多個以上的角色"
        },
        "psychological_depth": {
            "want_min_length": 20,
            "need_min_length": 20,
            "fatal_flaw_min_length": 15,
            "want_need_conflict_min_length": 30,
            "secret_min_length": 20,
            "description": "每個角色需具備完整的外在目標(Want)、內在需求(Need)、致命缺陷(Fatal Flaw)、Want/Need拉扯以及隱藏祕密"
        },
        "character_arc": {
            "min_length": 30,
            "description": "成長弧線(Arc)需清晰描述角色的變化軌跡"
        },
        "speech_profile": {
            "description": "建議定義 speech_profile（語域、句長、受壓行為與禁忌話題），禁止機械式字尾口頭禪"
        },
        "relationships": {
            "description": "每位角色需有多段明確的關係設定，含type與evolution"
        },
        "entry_phases": {
            "description": "角色登場階段需明確標註，分布需配合multi_act_structure的波次安排"
        },
        "faction_alignment": {
            "description": "主要角色需能對應世界觀 factions / 勢力設定，標明 faction 或 affiliation，並在關係網中呈現勢力利益衝突"
        },
        "consistency": {
            "description": "角色設定需與世界觀保持一致，關係網需邏輯連貫"
        }
    },
    "incremental_hint": "請根據 hint 內容，新增或修改指定的角色。",
    "modify_with_full_content_hint": "請根據 hint 內容，並傳入該角色的完整內容，進行局部修改。"
}


# =============================================================================
# 3. volumes (篇卷規劃師 Volumes Planner Agent)
# =============================================================================

VOLUME_SCHEMA = {
    "volume_index": 1,
    "title": "",
    "summary": "",
    "factions": [],
    "chapter_count": 50,
    "time_timeline": "",
    "sequence_context": "",
    "applicable_rules": []
}

VOLUMES_LIST_SCHEMA = []

# 卷通過標準（總監評判用）
VOLUME_APPROVAL_CRITERIA = {
    "name": "volumes",
    "display_name": "篇卷規劃師",
    "criteria": {
        "volume_count": {
            "description": "整部小說必須規劃 10 至 20 卷（含 10 與 20）"
        },
        "required_fields": {
            "per_volume": ["volume_index", "title", "summary", "chapter_count", "factions", "time_timeline", "sequence_context", "applicable_rules"],
            "description": "每卷必填欄位必須完整，不得為空"
        },
        "title": {
            "min_length": 3,
            "description": "每卷標題需精煉且富有文采"
        },
        "summary": {
            "min_length": 200,
            "max_length": 300,
            "description": "每卷概要需描述核心情節與高潮點"
        },
        "chapter_count": {
            "description": "每卷章節數量（chapter_count）必須落在 40 至 50 章之間"
        },
        "structure_coherence": {
            "description": "卷順序需連續，不可遺漏或斷檔；相鄰卷間需有情節銜接"
        },
        "character_progression": {
            "description": "需配合角色登場階段(Progressive Character Plan)，合理安排角色在不同卷的活躍度"
        },
        "turning_points_distribution": {
            "description": "需安排關鍵轉折點在適當卷位，確保張力均勻分布"
        },
        "volume_function": {
            "description": "每卷需有明確功能定位（起、承、轉、合），卷尾需有適當的高潮或懸念"
        }
    },
    "patch_hint": "請只生成第 {idx} 卷的內容，傳入 hint 指示。"
}


# =============================================================================
# 4. volume_skeleton (篇卷骨架規劃師 Volume Skeleton Planner)
# =============================================================================

CHAPTER_SKELETON_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "scene_function": "setup | escalation | confrontation | discovery | decision | consequence | recovery | transition | payoff", # Story Engine 2.0 場景功能
    "time_setting": "",
    "scene_setting": "",
    "scene_goal": "", # 本章核心戲劇目標
    "scene_conflict": "", # 本章核心衝突阻礙
    "story_state_before": "", # Story Engine 2.0: 本章開始前之故事狀態（資訊/資源/關係/風險）
    "story_state_after": "", # Story Engine 2.0: 本章完成後之實質狀態位移
    "setting_usage": [], # Story Engine 2.0: 本章涉及或運作之世界觀設定名稱
    "conflict_signature_hint": {}, # Story Engine 2.0: 衝突模式特徵 (pressure_type, protagonist_strategy, outcome)
    "scene_beats": [ # 結構化推進拍點（建議 3-5 個）
        {
            "beat_index": 1,
            "beat_type": "setup | escalation | turn | outcome",
            "description": "具體行動與推進行動",
            "involved_characters": []
        }
    ],
    "events": [ # 相容舊版欄位
        {
            "scene_index": 1,
            "location": "",
            "characters": [],
            "content": ""
        }
    ],
    "characters_active": [],
    "emotional_tone": "",
    "scene_turn": "", # 本章認知或情勢轉折
    "scene_outcome": "", # 本章結束狀態與代價
    "cliffhanger": ""
}

CHAPTER_SKELETON_WITH_ALLOC_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "time_setting": "",
    "scene_setting": "",
    "scene_goal": "",
    "scene_conflict": "",
    "scene_beats": [
        {
            "beat_index": 1,
            "beat_type": "setup | escalation | turn | outcome",
            "description": "具體行動與推進行動",
            "involved_characters": []
        }
    ],
    "events": [
        {
            "scene_index": 1,
            "location": "",
            "characters": [],
            "content": ""
        }
    ],
    "characters_active": [],
    "emotional_tone": "",
    "scene_turn": "",
    "scene_outcome": "",
    "cliffhanger": "",
    "volume_index": 1,
    "volume_title": "",
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

VOLUME_SKELETON_OUTPUT_SCHEMA = {
    "volume_index": 1,
    "chapters_skeleton": [CHAPTER_SKELETON_WITH_ALLOC_SCHEMA],
    "new_characters": [
        {
            "name": "角色姓名",
            "role": "正派盟友 / 主要反派 / 導師 / 灰色中立 / 地方頭目",
            "faction": "所屬勢力或門派",
            "personality": "核心性格特徵、言行語氣風格",
            "motivation": "主要訴求、核心利益或潛在衝突",
            "first_appearance_chapter": 1
        }
    ],
    "new_world_rules": [
        {
            "name": "法則或制度名稱",
            "scope": "本卷專屬 / 全域通用",
            "description": "具體規則運作邏輯、代價或約束"
        }
    ],
    "new_factions": [
        {
            "name": "勢力名稱",
            "alignment": "敵對 / 友好 / 中立利益導向",
            "summary": "勢力背景與在當前卷的影響力"
        }
    ]
}

# 場景寫作契約 Schema（由 WriterContextBuilder 動態組裝給 Writer）
SCENE_CONTRACT_SCHEMA = {
    "chapter_index": 1,
    "pov_character": "林澤",
    "narrative_mode": "third_person_limited", # third_person_limited | first_person | third_person_omniscient
    "narrative_distance": "close", # close | medium | far
    "thought_mode": "free_indirect", # free_indirect | sensory_only | direct_internal
    "scene_goal": "",
    "conflict": "",
    "turn": "",
    "outcome": "",
    "knowledge_scope": ["當前 POV 角色能感知、記憶或推論的情報範圍"]
}

# 編輯評審診斷報告 Schema (Reviewer Output)
EDITOR_REVIEW_REPORT_SCHEMA = {
    "chapter_index": 1,
    "pov_violations": [
        # {"snippet": "違規原文片段", "issue": "說明為何越界或非授權視角切換", "suggestion": "修正建議"}
    ],
    "knowledge_leaks": [
        # {"snippet": "違規原文片段", "issue": "角色說出或知道尚未得知的秘密", "suggestion": "修正建議"}
    ],
    "info_dump_sections": [
        # {"snippet": "設定集傾倒片段", "issue": "抽離故事的設定說明", "suggestion": "改為融入動作或環境"}
    ],
    "dialogue_issues": [
        # {"speaker": "角色名", "snippet": "生硬對話片段", "issue": "機械口癖/無潛台詞/不符語音人設", "suggestion": "修正建議"}
    ],
    "repetition_flags": [
        # {"snippet": "AI模板詞/重複句式", "issue": "過度使用顫抖/凝固/命運重量等套路詞"}
    ],
    "template_repetition_flag": {
        "is_repetitive": False,
        "issue": ""
    },
    "info_density_score": 8.5,
    "scene_compression_candidates": [
        # {"section": "片段描述", "issue": "拖沓或資訊稀釋", "suggested_compression_ratio": "40%-50%"}
    ],
    "scene_goal_completed": True,
    "foreshadow_tasks_completed": [],
    "style_consistency_score": 8.5,
    "revision_required": False,
    "target_revision_instructions": ""
}

VOLUME_SKELETON_LIST_SCHEMA = []

# 骨架通過標準（總監評判用）
SKELETON_APPROVAL_CRITERIA = {
    "name": "volume_skeleton",
    "display_name": "篇卷骨架規劃師",
    "criteria": {
        "chapter_completeness": {
            "description": "確保規劃篇卷的章節骨架完整就緒，若尚有篇卷未完成骨架，請繼續進行骨架補充。"
        },
        "chapter_structure": {
            "required_fields": ["chapter_index", "chapter_title", "chapter_summary", "time_setting", "scene_setting", "characters_active", "emotional_tone", "cliffhanger", "allocated_tasks"],
            "description": "每章需具備輕量骨架結構，可包含 scene_goal, scene_conflict 與 scene_beats（或 events），供 writer 承接"
        },
        "anti_repetition_and_diversity": {
            "description": "同卷內注重破局模式多樣化，避免連續過場空轉，重大轉折章前置具備動搖或懷疑拍點"
        },
        "time_setting": {
            "description": "每章需有清晰的時間設定與前章的時間跨度"
        },
        "scene_beats": {
            "description": "每章建議規劃 3-5 個輕量推進拍點（或 1-2 個核心事件），清晰描述行動與結果，不寫長段散文"
        },
        "foreshadowing_sync": {
            "description": "伏筆種植(foreshadowing_plants)與回收(foreshadowing_payoffs)需與骨架分配的allocated_tasks一致"
        },
        "turning_points_alignment": {
            "description": "turning_points需與世界觀設定的key_turning_points呼應"
        },
        "cliffhanger": {
            "description": "章末需有短鉤子或下一章推進提示，不要求強行製造誇張懸念"
        },
        "character_consistency": {
            "description": "活躍角色需符合角色聖經設定，不可出現角色行為衝突"
        },
        "plot_drive": {
            "description": "每章需有明確的敘事目的，拒絕流水帳"
        },
        "character_presence": {
            "description": "【角色出場輕量規劃】骨架階段只需列出本章真正活躍角色，並保持與角色 Bible 相容；角色戲劇細節由 writer 展開。"
        }
    },
}



# =============================================================================
# 6. writer (正文寫作作家 Chapter Writer Agent)
# =============================================================================

WRITER_OUTPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": "",
    "thinking": ""
}

WRITER_INPUT_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "scenes": [],
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

# 寫作通過標準（總監評判用）
WRITER_APPROVAL_CRITERIA = {
    "name": "writer",
    "display_name": "正文寫作作家",
    "criteria": {
        "content_length": {
            "min_words": 1500,
            "max_words": 2000,
            "description": "每章正文需確保足夠的敘事深度"
        },
        "structure_compliance": {
            "description": "正文需嚴格按照大綱的時間設定、場景、伏筆順序展開"
        },
        "show_dont_tell": {
            "description": "需透過環境渲染、肢體動作、台詞、心理描寫展現情節，避免純敘述"
        },
        "character_consistency": {
            "description": "角色台詞、語氣、動作、神態需符合角色聖經"
        },
        "foreshadowing_execution": {
            "description": "伏筆需自然融入敘事，回收時需營造驚喜與合理性"
        },
        "turning_point_execution": {
            "description": "轉折點需有足夠的鋪陳與衝擊力"
        },
        "prose_quality": {
            "description": "文筆需流暢優雅，符合指定文風"
        },
        "cliffhanger_effectiveness": {
            "description": "章末懸念需有效鉤住讀者"
        }
    },
}


# =============================================================================
# 7. editor (編輯姬 Editor Agent)
# =============================================================================

EDITOR_INPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": ""
}

EDITOR_OUTPUT_SCHEMA = {
    "novel_id": "",
    "chapter_index": 1,
    "content": "",
    "synopsis": ""
}

# 編輯通過標準（總監評判用）
EDITOR_APPROVAL_CRITERIA = {
    "name": "editor",
    "display_name": "編輯姬",
    "criteria": {
        "content_quality_improvement": {
            "description": "潤色後內容需比原版有明顯提升，包括文筆、流暢度、節奏"
        },
        "character_consistency_preserved": {
            "description": "潤色不可改變角色聖經定義的人設，不可造成角色行為衝突"
        },
        "plot_integrity": {
            "description": "不可改變大綱既定的情節走向與關鍵事件"
        },
        "foreshadowing_integrity": {
            "description": "不可刪除或錯誤修改已埋下的伏筆內容"
        },
        "synopsis_accuracy": {
            "description": "更新後的synopsis需準確反映本章內容"
        },
        "polish_level": {
            "description": "需修正語法錯誤、改善句式多樣性、消除冗詞"
        }
    },
}


# =============================================================================
# 統一通過標準查詢介面
# =============================================================================

APPROVAL_CRITERIA_REGISTRY = {
    "worldview": WORLDVIEW_APPROVAL_CRITERIA,
    "worldview_core": WORLDVIEW_CORE_APPROVAL_CRITERIA,
    "multi_act_structure": MULTI_ACT_STRUCTURE_APPROVAL_CRITERIA,
    "progressive_character_plan": PROGRESSIVE_CHARACTER_PLAN_APPROVAL_CRITERIA,
    "foreshadowing": FORESHADOWING_APPROVAL_CRITERIA,
    "characters": CHARACTER_APPROVAL_CRITERIA,
    "volumes": VOLUME_APPROVAL_CRITERIA,
    "volume_skeleton": SKELETON_APPROVAL_CRITERIA,
    "writer": WRITER_APPROVAL_CRITERIA,
    "editor": EDITOR_APPROVAL_CRITERIA,
}


OUTPUT_SCHEMA_REGISTRY = {
    "worldview": WORLDVIEW_SCHEMA,
    "worldview_core": {
        "theme": "核心主題，深入且具哲學命題（50-500字）",
        "main_conflict": "核心衝突與多陣營拉扯情節張力網（100-800字）",
        "worldview": "世界觀核心設定，包含力量體系、地理、社會結構（300字以上）",
        "macro_outline": "全書宏觀整體大綱，支撐百萬字長篇",
    },
    "multi_act_structure": {"multi_act_structure": WORLDVIEW_SCHEMA["multi_act_structure"]},
    "progressive_character_plan": {"progressive_character_plan": WORLDVIEW_SCHEMA["progressive_character_plan"]},
    "foreshadowing": FORESHADOWING_OUTPUT_SCHEMA,
    "characters": {"characters": [CHARACTER_SCHEMA]},
    "volumes": {"volumes": [VOLUME_SCHEMA]},
    "volume_skeleton": VOLUME_SKELETON_OUTPUT_SCHEMA,
    "skeleton": VOLUME_SKELETON_OUTPUT_SCHEMA,
    "scene_contract": SCENE_CONTRACT_SCHEMA,
    "editor_review": EDITOR_REVIEW_REPORT_SCHEMA,
    "writer": WRITER_OUTPUT_SCHEMA,
    "editor": EDITOR_OUTPUT_SCHEMA,
}


def get_approval_criteria(stage_name):
    """
    取得指定階段的通過標準
    
    Args:
        stage_name: 階段名稱 (worldview, characters, volumes, volume_skeleton, writer, editor)
    
    Returns:
        通過標準dict，若無對應階段則返回None
    """
    return APPROVAL_CRITERIA_REGISTRY.get(stage_name)


def format_criteria_for_prompt(stage_name):
    """
    格式化通過標準為可供LLM閱讀的提示詞格式
    
    Args:
        stage_name: 階段名稱
    
    Returns:
        格式化後的字串
    """
    criteria = get_approval_criteria(stage_name)
    if not criteria:
        return ""
    
    lines = [
        f"\n【{criteria['display_name']} 創作重點參考】",
    ]
    
    for key, value in criteria["criteria"].items():
        if isinstance(value, dict):
            lines.append(f"- **{key}**: {value.get('description', '')}")
        else:
            lines.append(f"- **{key}**: {value}")
    
    return "\n".join(lines)


def get_output_schema(stage_name):
    """Return the canonical output schema/example for a generation stage."""
    return OUTPUT_SCHEMA_REGISTRY.get(stage_name)


def format_output_schema_for_prompt(stage_name, *, label=None):
    """Format the canonical schema/example from this module for agent system prompts."""
    schema = get_output_schema(stage_name)
    if schema is None:
        return ""
    heading = label or stage_name
    return (
        f"\n【{heading} 資料結構範例】\n"
        "請參考下列結構整理資料，以標準英文欄位名組織，內容則用生動流暢的繁體中文書寫，只輸出純 JSON：\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n"
    )


# =============================================================================
# 輔助函數
# =============================================================================

def get_worldview_default():
    """取得世界觀預設結構"""
    return WORLDVIEW_SCHEMA.copy()


def get_character_default():
    """取得角色預設結構"""
    return CHARACTER_SCHEMA.copy()


def get_volume_default(volume_index=1):
    """取得篇卷預設結構"""
    vol = VOLUME_SCHEMA.copy()
    vol["volume_index"] = volume_index
    vol["title"] = f"第 {volume_index} 卷"
    return vol


def get_chapter_skeleton_default(chapter_index=1):
    """取得章節骨架預設結構"""
    skel = CHAPTER_SKELETON_SCHEMA.copy()
    skel["chapter_index"] = chapter_index
    return skel



def create_characters_structure(characters_list):
    """建立角色結構"""
    return {"characters": characters_list}


def create_volume_list(volumes_list):
    """建立篇卷列表"""
    return volumes_list


def create_skeleton_list(skeletons_list):
    """建立骨架列表"""
    return skeletons_list


def create_foreshadowing_allocations(allocations_list):
    """建立伏筆分配列表"""
    return allocations_list


# =============================================================================
# 8. Story Engine 2.0: Setting System & Narrative Reasoning Schemas
# =============================================================================

SETTING_SYSTEM_SCHEMA = {
    "name": "設定系統名稱（如：專利魔網、靈氣潮汐律、宗門貢獻點體制）",
    "type": "power_mechanism | political_institution | economic_rule | ecological_law | social_taboo",
    "mechanism": "該設定如何具體運作，其底層因果規律是什麼",
    "cost": "使用、獲取或維護該機制需要付出之代價（物質/壽元/社會代價）",
    "boundary": "該設定絕對無法做到什麼，其作用範圍的物理或邏輯極限",
    "failure_condition": "在何種極端情境下該系統會失效、崩潰或產生反噬",
    "stakeholder": "主要受益者、維護者與受壓迫群體",
    "social_effect": "該設定對凡人/底層大眾日常生活與心理習慣的具體塑造",
    "theme_link": "該設定如何呼應作品的核心主題或哲學悖論",
    "current_state": "active | stressed | compromised | collapsed"
}

CONFLICT_SIGNATURE_SCHEMA = {
    "chapter_start": 1,
    "chapter_end": 1,
    "initiator": "發起衝突之人物或勢力",
    "antagonist_goal": "對手具體想掠奪、壓迫或達成的目的",
    "pressure_type": "economic_blockade | legal_trap | direct_violence | hostage_threat | technological_monopoly | psychological_deception | structural_purge",
    "protagonist_strategy": "asymmetric_wit | rules_loophole | sacrifice_escape | direct_clash | undercover_infiltration | third_party_leverage",
    "power_used": "主角動用之核心能力或道具",
    "twist_mechanism": "反轉或破局的具體關鍵因果",
    "outcome": "protagonist_flawless_win | costly_escape | partial_loss | strategic_stalemate | pyrrhic_victory",
    "cost": "主角或陣營付出的代價（資源/傷勢/人際/秘密暴露）",
    "emotional_effect": "對在場人物心理之實質改變",
    "setting_used": "本衝突涉及運作之設定系統名稱"
}

NARRATIVE_PROFILE_SCHEMA = {
    "commercial_positioning": "商業長篇小說",
    "dominant_appeal": "升級智鬥與爽感反轉",
    "tone": "熱血、微諷、懸疑沉浸",
    "humor_level": "low | medium | high",
    "power_fantasy_level": "grounded | medium | high | absolute",
    "emotional_intensity": "light | medium | heavy",
    "pacing_preference": "緊湊推進、有張有弛",
    "narrative_complexity": "single_line | dual_track | multi_faction"
}

ANTAGONIST_DECISION_MODEL_SCHEMA = {
    "goal": "反派具體之生存或利益訴求",
    "perceived_threat": "反派眼中主角帶來的實際威脅評估",
    "resource": "反派掌握之制度、武力或人脈資源",
    "constraint": "反派行動受限之規章、法規或外部監視",
    "red_line": "反派絕不退讓或不可觸碰之底線",
    "preferred_method": "習慣採用之手段（行政陷阱、暗殺、經濟斷供等）"
}

CAPABILITY_CONSTRAINT_MODEL_SCHEMA = {
    "power_name": "能力或金手指名稱",
    "applicable_scope": "精確適用情境與對象",
    "blind_spots": "此能力完全無法解決的問題類型（如人心、生物本能、複雜博弈）",
    "exposure_risk": "過度使用時引來之官方追查或天敵窺伺風險",
    "social_moral_cost": "使用該力量帶來的社會疑慮或道德壓力",
    "irreversible_consequence": "是否會產生不可逆之後果或環境破壞"
}

SETTING_AUDIT_SCHEMA = {
    "audit_type": "worldview_establishment | skeleton_usage | chapter_evolution",
    "passed": True,
    "setting_health_score": 85,
    "operating_mechanisms_count": 5,
    "issues_detected": [
        {
            "setting_name": "設定名稱",
            "issue_type": "lacks_cost | lacks_boundary | cosmetic_only | contradiction | stale_unused",
            "description": "具體問題說明",
            "remediation_hint": "改善指引"
        }
    ],
    "recommendations": []
}
