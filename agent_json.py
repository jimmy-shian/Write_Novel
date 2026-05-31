# -*- coding: utf-8 -*-
"""
AI 小說工廠流程 JSON Schema 定義

可直接引用使用的各流程 JSON 格式模組
"""

# =============================================================================
# 1. worldview (世界觀架構師 Story Architect Agent)
# =============================================================================

WORLDVIEW_SCHEMA = {
    "theme": "",
    "main_conflict": "",
    "worldview": "",
    "macro_outline": "",
    "multi_act_structure": [
        {"title": "第一幕 (Setup)", "content": ""},
        {"title": "第二幕 (Confrontation)", "content": ""},
        {"title": "第三幕 (Resolution)", "content": ""}
    ],
    "progressive_character_plan": [
        {"title": "第一波開篇 (Wave 1)", "content": ""},
        {"title": "第二波發展 (Wave 2)", "content": ""},
        {"title": "第三波高潮 (Wave 3)", "content": ""}
    ],
    "foreshadowing_seeds": [],
    "key_turning_points": []
}

WORLDVIEW_CHAPTER_PATCH = {
    "category": "",
    "details": "",
    "source_chapter": 0,
    "created_at": ""
}

# 世界觀通過標準（總監評判用）
WORLDVIEW_APPROVAL_CRITERIA = {
    "name": "worldview",
    "display_name": "世界觀架構師",
    "criteria": {
        "structure": {
            "required_fields": ["theme", "main_conflict", "worldview", "macro_outline", "multi_act_structure", "progressive_character_plan", "foreshadowing_seeds", "key_turning_points"],
            "description": "所有必填欄位必須完整填寫，不得為空"
        },
        "theme": {
            "min_length": 50,
            "max_length": 500,
            "description": "核心主題需具備深度與哲學命題"
        },
        "main_conflict": {
            "min_length": 100,
            "max_length": 800,
            "description": "核心衝突需明確描述多陣營張力"
        },
        "worldview": {
            "min_length": 300,
            "description": "世界觀需包含地理、力量體系、社會結構、氛圍等要素"
        },
        "macro_outline": {
            "min_length": 200,
            "description": "宏觀大綱需完整描述故事走向"
        },
        "multi_act_structure": {
            "min_acts": 5,
            "max_acts": 10,
            "description": "多幕結構需5-10幕，每幕需有明確的起承轉合功能與內容描述"
        },
        "progressive_character_plan": {
            "min_waves": 5,
            "description": "角色漸進規劃需5波以上，反映角色的階段性登場與成長"
        },
        "foreshadowing_seeds": {
            "min_count": 30,
            "description": "伏筆種子需至少30個，每個需標明早期埋設點、中期干擾、后期收束"
        },
        "key_turning_points": {
            "min_count": 40,
            "description": "關鍵轉折點需至少40個，每個需標明觸發條件與全局影響"
        },
        "consistency": {
            "description": "各欄位間需邏輯一致，伏筆與轉折點需相互呼應"
        }
    },
    "auto_regenerate_hint": "請根據使用者提供的劇情設定，重新生成完整的世界觀架構。"
}


# =============================================================================
# 2. characters (角色設計師 Character Designer Agent)
# =============================================================================

CHARACTER_SCHEMA = {
    "name": "",
    "role": "",
    "entry_phase": "",
    "personality": [],
    "want": "",
    "need": "",
    "fatal_flaw": "",
    "motivation": "",
    "arc": "",
    "speech_style": "",
    "appearance": "",
    "background": "",
    "relationships": []
}

CHARACTER_RELATIONSHIP_SCHEMA = {
    "with": "",
    "type": "",
    "evolution": ""
}

CHARACTERS_ROOT_SCHEMA = {
    "characters": []
}

# 角色通過標準（總監評判用）
CHARACTER_APPROVAL_CRITERIA = {
    "name": "characters",
    "display_name": "角色設計師",
    "criteria": {
        "required_fields": {
            "per_character": ["name", "role", "entry_phase", "personality", "want", "need", "fatal_flaw", "motivation", "arc", "speech_style", "background", "relationships"],
            "description": "每個角色必填欄位必須完整，不得為空或佔位符"
        },
        "name_validity": {
            "description": "name 欄位必須是角色的具體姓名/代號，絕對禁止使用組織職位或社會身份作為姓名"
        },
        "character_count": {
            "min_protagonist": 1,
            "min_antagonist": 1,
            "min_total": 5,
            "description": "至少需要1位主角、1位反派/宿敵、總計5位以上角色"
        },
        "psychological_depth": {
            "want_min_length": 20,
            "need_min_length": 20,
            "fatal_flaw_min_length": 15,
            "description": "每個角色需具備完整的外在目標(Want)、內在需求(Need)、致命缺陷(Fatal Flaw)"
        },
        "character_arc": {
            "min_length": 30,
            "description": "成長弧線(Arc)需清晰描述角色的變化軌跡"
        },
        "speech_style": {
            "min_length": 15,
            "description": "說話風格需具體描述口頭禪、語氣特徵"
        },
        "relationships": {
            "min_relationships": 2,
            "description": "每位角色需至少有2段明確的關係設定，含type與evolution"
        },
        "entry_phases": {
            "description": "角色登場階段需明確標註，分布需配合multi_act_structure的波次安排"
        },
        "consistency": {
            "description": "角色設定需與世界觀保持一致，關係網需邏輯連貫"
        }
    },
    "auto_regenerate_hint": "請根據世界觀與角色清單，生成/擴充完整的角色設計。",
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
            "min_count": 10,
            "max_count": 15,
            "description": "卷數建議10-15卷，需與世界觀的多幕結構呼應"
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
            "min_per_volume": 50,
            "max_per_volume": 200,
            "description": "每卷章節數需50-200章，保持容量得當"
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
    "auto_regenerate_hint": "請根據世界觀設定與角色清單，生成全書的篇卷結構，包括卷數（建議 10-15 卷）、每卷標題、概要，以及各卷的關鍵事件轉折與主要角色登場安排。",
    "patch_hint": "請只生成第 {idx} 卷的內容，傳入 hint 指示。"
}


# =============================================================================
# 4. volume_skeleton (篇卷骨架規劃師 Volume Skeleton Planner)
# =============================================================================

CHAPTER_SKELETON_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": ""
}

CHAPTER_SKELETON_WITH_ALLOC_SCHEMA = {
    "chapter_index": 1,
    "chapter_title": "",
    "chapter_summary": "",
    "volume_index": 1,
    "volume_title": "",
    "allocated_tasks": {
        "foreshadowing_plants": [],
        "foreshadowing_payoffs": [],
        "turning_points": []
    }
}

VOLUME_SKELETON_LIST_SCHEMA = []

# 骨架通過標準（總監評判用）
SKELETON_APPROVAL_CRITERIA = {
    "name": "volume_skeleton",
    "display_name": "篇卷骨架規劃師",
    "criteria": {
        "chapter_completeness": {
            "description": "該卷所有章節骨架必須完整生成，不可缺漏任何一章"
        },
        "chapter_title": {
            "min_length": 3,
            "description": "每章標題需精煉且富有文采"
        },
        "chapter_summary": {
            "min_length": 50,
            "max_length": 100,
            "description": "每章摘要需描述本章核心情節里程碑"
        },
        "foreshadowing_allocation": {
            "min_plants": 1,
            "description": "每章需合理分配伏筆埋設任務，新卷需有伏筆種植"
        },
        "turning_point_placement": {
            "description": "關鍵轉折點需在適當位置，卷尾/高潮章需有轉折安排"
        },
        "chapter_sequence": {
            "description": "章節序號需連續，不可中斷或跳號"
        },
        "allocated_tasks_structure": {
            "foreshadowing_plants": "array of strings",
            "foreshadowing_payoffs": "array of strings",
            "turning_points": "array of strings",
            "description": "每章的allocated_tasks三個陣列需存在，可為空陣列"
        },
        "character_exclusion": {
            "description": "【骨架極簡原則】骨架階段只需專注於基本劇情走向與里程碑進展，絕對不需要管角色登場、角色活躍或人物分配等細節。這些人設細節應留到詳細大綱階段處理。"
        }
    },
    "auto_regenerate_hint": "請根據世界觀與 前後各1卷的大綱，重新生成完整的當前卷骨架。"
}


# =============================================================================
# 5. plot (大綱規劃師 Plot Planner Agent)
# =============================================================================

PLOT_CHAPTER_SCHEMA = {
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

PLOT_SCENE_SCHEMA = {
    "scene_index": 1,
    "location": "",
    "characters": [],
    "content": ""
}

PLOT_ROOT_SCHEMA = {
    "chapters": []
}

# 大綱通過標準（總監評判用）
PLOT_APPROVAL_CRITERIA = {
    "name": "plot",
    "display_name": "大綱規劃師",
    "criteria": {
        "chapter_completeness": {
            "description": "所有章節大綱必須完整生成，不可缺漏"
        },
        "chapter_structure": {
            "required_fields": ["chapter_index", "title", "chapter_summary", "events", "foreshadowing_plant", "foreshadowing_payoff", "turning_points", "characters_active", "emotional_tone", "cliffhanger"],
            "description": "每章需具備完整結構，所有欄位不可為空"
        },
        "time_setting": {
            "description": "每章需有清晰的時間設定與與前章的時間跨度"
        },
        "events": {
            "min_scenes": 0,
            "max_scenes": 4,
            "description": "每章需包含0-4個具體場景事件，描述動作衝突與後果"
        },
        "foreshadowing_sync": {
            "description": "伏筆種植(foreshadowing_plant)與回收(foreshadowing_payoff)需與骨架分配的allocated_tasks一致"
        },
        "turning_points_alignment": {
            "description": "turning_points需與世界觀設定的key_turning_points呼應"
        },
        "cliffhanger": {
            "description": "章末需有懸念鉤子(Cliffhanger)，確保閱讀張力"
        },
        "character_consistency": {
            "description": "活躍角色需符合角色聖經設定，不可出現角色行為衝突"
        },
        "plot_drive": {
            "description": "每章需有明確的敘事目的，拒絕流水帳"
        },
        "character_presence": {
            "description": "【角色出場深度規劃】詳細大綱階段必須詳細規劃並產生詳細內容，且要確實安排角色活躍場景以滿足全局人設分佈（例如：確保核心主角與關鍵配角活躍於適當的篇卷與情節，在情節中明確展示角色出場與重要戲劇張力）。"
        }
    },
    "auto_regenerate_hint": "請根據世界觀與 前後各1章的骨架大綱，重新生成完整的當前大綱。"
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
    "auto_regenerate_hint": "請根據世界觀與 前後各1卷的詳細大綱，以及後三章即將收回的伏筆內容，重新生成正文。"
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
    "auto_regenerate_hint": "請根據編輯指示，重新潤色本章正文。"
}


# =============================================================================
# 統一通過標準查詢介面
# =============================================================================

APPROVAL_CRITERIA_REGISTRY = {
    "worldview": WORLDVIEW_APPROVAL_CRITERIA,
    "characters": CHARACTER_APPROVAL_CRITERIA,
    "volumes": VOLUME_APPROVAL_CRITERIA,
    "volume_skeleton": SKELETON_APPROVAL_CRITERIA,
    "plot": PLOT_APPROVAL_CRITERIA,
    "writer": WRITER_APPROVAL_CRITERIA,
    "editor": EDITOR_APPROVAL_CRITERIA,
}


def get_approval_criteria(stage_name):
    """
    取得指定階段的通過標準
    
    Args:
        stage_name: 階段名稱 (worldview, characters, volumes, volume_skeleton, plot, writer, editor)
    
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
        f"\n## 【{criteria['display_name']} 通過標準】",
        f"### 必檢查項目：\n"
    ]
    
    for key, value in criteria["criteria"].items():
        if isinstance(value, dict):
            lines.append(f"- **{key}**: {value.get('description', '')}")
        else:
            lines.append(f"- **{key}**: {value}")
    
    if "auto_regenerate_hint" in criteria:
        lines.append(f"\n### 重新生成提示：")
        lines.append(f"{criteria['auto_regenerate_hint']}")
    
    return "\n".join(lines)


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


def get_plot_chapter_default(chapter_index=1):
    """取得大綱章節預設結構"""
    ch = PLOT_CHAPTER_SCHEMA.copy()
    ch["chapter_index"] = chapter_index
    return ch


def create_plot_structure(chapters_list):
    """建立大綱結構"""
    return {"chapters": chapters_list}


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